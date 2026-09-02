-- ============================================================
-- 마중ON Care — 최적화 이력 보존 (Phase 2 / P0·P1)
--
-- Supabase 대시보드 > SQL Editor 에 통째로 붙여넣고 실행하세요.
-- 여러 번 실행해도 안전합니다.
--
-- 이 SQL 을 실행한 뒤에 백엔드를 배포해야 합니다. 순서가 바뀌면 새 백엔드가
-- 없는 표에 쓰려다 실패합니다. (실패해도 배차는 그대로 돌도록 감싸 뒀습니다)
--
-- 왜 필요한가
--   지금은 배차를 계산해도 그 원안이 어디에도 남지 않습니다. [배차 전송] 을
--   눌러야만 마지막 하나가 dispatches 에 들어가고, 같은 날 다시 전송하면
--   그것마저 덮어씁니다. 실제로 7건 중 4건이 이미 덮어써졌습니다.
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- 1) 최적화 실행 이력
--
-- 배차를 계산할 때마다 한 줄. 절대 덮어쓰지 않습니다.
-- 원장님이 조건을 바꿔가며 여러 번 계산하면 그 횟수만큼 쌓이고,
-- 그 자체가 '앞선 결과를 받아들이지 않았다' 는 신호가 됩니다.
-- ────────────────────────────────────────────────────────────
create table if not exists public.optimization_runs (
  id                  uuid        primary key default gen_random_uuid(),

  -- 센터 격리. 지금은 값이 하나뿐이지만, 나중에 넣으면 과거 데이터에
  -- 소급할 수 없어 지금부터 채웁니다.
  center_id           text        not null default 'default',

  service_date        date        not null,
  trip_type           text        not null default 'inbound'
                        check (trip_type in ('inbound', 'outbound')),
  -- 같은 날 같은 구분으로 몇 번째 계산인지. 2 이상이면 앞선 결과를 다시 짠 것입니다.
  run_sequence        integer     not null default 1,
  run_at              timestamptz not null default now(),

  -- 어떤 판으로 풀었는지. 나중에 'V1.2 가 V1.1 보다 나았나' 를 묻기 위한 것입니다.
  engine_version      text        not null,
  constraint_version  text        not null,
  objective_version   text        not null,
  config              jsonb       not null default '{}'::jsonb,

  -- 솔버가 어떻게 끝났는지
  solver_status       text,
  solve_seconds       numeric,

  -- 요약 지표. 이 값들만으로 대부분의 KPI 를 계산할 수 있어 영구 보존합니다.
  passenger_count     integer     not null default 0,
  vehicle_count       integer     not null default 0,
  assigned_count      integer     not null default 0,
  unassigned_count    integer     not null default 0,
  total_distance_m    integer     not null default 0,
  objective_breakdown jsonb,

  -- 당시 상태를 되짚기 위한 것. 이름·연락처·상세주소는 담지 않습니다.
  -- TTL 이 지나면 이 두 칸만 비우고 위 요약은 남깁니다.
  input_snapshot      jsonb,
  result_snapshot     jsonb,

  created_at          timestamptz not null default now()
);

create index if not exists optimization_runs_lookup_idx
  on public.optimization_runs (center_id, service_date, trip_type, run_at desc);
create index if not exists optimization_runs_age_idx
  on public.optimization_runs (run_at);

alter table public.optimization_runs enable row level security;


-- ────────────────────────────────────────────────────────────
-- 2) 최종안이 어느 원안에서 나왔는지 (보완 원칙 5)
-- ────────────────────────────────────────────────────────────
alter table public.dispatches
  add column if not exists source_run_id uuid references public.optimization_runs(id);
alter table public.dispatches
  add column if not exists center_id text not null default 'default';

alter table public.ride_completions
  add column if not exists center_id text not null default 'default';

create index if not exists dispatches_source_run_idx
  on public.dispatches (source_run_id);


-- ────────────────────────────────────────────────────────────
-- 3) 보존 기간 (TTL)
--
--   요약 행            영구      — KPI 는 전부 이 값으로 계산됩니다 (행당 약 0.3KB)
--   일반 스냅샷        12개월    — '왜 이 배차가 나왔나' 는 대개 같은 시즌 안입니다
--   전송된 배차 스냅샷  36개월    — 실제 운행에 쓰인 것이라 분쟁·감사 대비로 더 둡니다
--
-- 행을 지우는 것이 아니라 무거운 두 칸만 비웁니다. 요약은 그대로 남습니다.
-- ────────────────────────────────────────────────────────────
create or replace function public.prune_optimization_snapshots()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  affected integer;
begin
  update public.optimization_runs r
     set input_snapshot = null,
         result_snapshot = null
   where (r.input_snapshot is not null or r.result_snapshot is not null)
     and r.run_at < now() - (
           case when exists (
                  select 1 from public.dispatches d where d.source_run_id = r.id
                )
                then interval '36 months'
                else interval '12 months'
           end
         );
  get diagnostics affected = row_count;
  return affected;
end;
$$;

-- pg_cron 이 있으면 매달 1일 새벽 3시에 돌립니다.
-- 없으면 이 블록은 조용히 넘어가고, 나중에 손으로 select prune_optimization_snapshots();
-- 를 실행해도 됩니다.
do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.unschedule('majungon-prune-snapshots')
      where exists (select 1 from cron.job where jobname = 'majungon-prune-snapshots');
    perform cron.schedule(
      'majungon-prune-snapshots', '0 3 1 * *',
      'select public.prune_optimization_snapshots();'
    );
    raise notice '스냅샷 정리 작업을 매달 1일 03:00 으로 예약했습니다.';
  else
    raise notice 'pg_cron 이 없습니다. 정리는 손으로 select public.prune_optimization_snapshots(); 를 실행하세요.';
  end if;
end
$$;


-- ────────────────────────────────────────────────────────────
-- 4) 확인 — 아래 결과가 나오면 성공입니다.
-- ────────────────────────────────────────────────────────────
select '1. optimization_runs 표' as 항목,
       case when to_regclass('public.optimization_runs') is null
            then '없음 (실패)' else '있음' end as 값
union all
select '2. dispatches 새 칸',
       coalesce(string_agg(column_name, ', ' order by column_name), '없음 (실패)')
  from information_schema.columns
 where table_schema = 'public' and table_name = 'dispatches'
   and column_name in ('source_run_id', 'center_id')
union all
select '3. ride_completions.center_id',
       case when exists (
              select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'ride_completions'
                 and column_name = 'center_id')
            then '있음' else '없음 (실패)' end
union all
select '4. 스냅샷 정리 함수',
       case when to_regprocedure('public.prune_optimization_snapshots()') is null
            then '없음 (실패)' else '있음' end
union all
select '5. RLS',
       case when relrowsecurity then '켜짐' else '꺼짐 (실패)' end
  from pg_class where oid = 'public.optimization_runs'::regclass;
