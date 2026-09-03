-- ============================================================
-- 마중ON Care — 대안 분석 결과 보존 (v3.2)
--
-- Supabase 대시보드 > SQL Editor 에 통째로 붙여넣고 실행하세요.
-- 여러 번 실행해도 안전합니다.
--
-- 무엇을 위한 것인가
--   배차가 안 됐을 때 무엇을 제안했는지 남긴다.
--
--   제안만 남기는 것이 목적이 아니다. 같은 날 다음 계산에서 그 어르신의
--   희망 시각이 실제로 바뀌었는지 보면, 원장님이 그 제안을 받아들였는지
--   알 수 있다. 수용률이 낮으면 제안이 현장과 맞지 않는다는 뜻이고,
--   그게 다음 개선의 근거가 된다.
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- 1) 제안 내용
--
-- run 한 줄에 제안 하나. 분석을 안 돌린 계산은 null 로 남는다.
-- ────────────────────────────────────────────────────────────
alter table public.optimization_runs
  add column if not exists recommendation jsonb;

comment on column public.optimization_runs.recommendation is
  '배차 불가 시 제시한 대안. verdict/options/actions 구조. 분석을 부르지 않았으면 null.';

-- 어떤 판정이 얼마나 나왔는지 세는 데 쓴다. jsonb 전체를 훑지 않도록 한다.
create index if not exists optimization_runs_verdict_idx
  on public.optimization_runs ((recommendation ->> 'verdict'))
  where recommendation is not null;


-- ────────────────────────────────────────────────────────────
-- 2) 스냅샷 정리에 제안도 함께 태운다
--
-- 제안 안에는 어르신 이름이 들어 있다(화면에 "김OO 어르신을 30분" 이라고
-- 띄워야 하므로). 그래서 스냅샷과 같은 기간만 두고 함께 비운다.
-- 판정(verdict) 만 남기면 수용률 통계는 계속 낼 수 있다.
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
         result_snapshot = null,
         -- 이름이 든 actions 만 덜어내고 판정은 남긴다.
         recommendation = case
           when r.recommendation is null then null
           else jsonb_build_object(
                  'verdict', r.recommendation -> 'verdict',
                  'unassigned_count', r.recommendation -> 'unassigned_count',
                  'pruned', to_jsonb(true))
         end
   where (r.input_snapshot is not null
          or r.result_snapshot is not null
          or (r.recommendation is not null
              and not coalesce((r.recommendation ->> 'pruned')::boolean, false)))
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


-- ────────────────────────────────────────────────────────────
-- 3) 확인 — 아래 결과가 나오면 성공입니다.
-- ────────────────────────────────────────────────────────────
select '1. recommendation 칸' as 항목,
       case when exists (
              select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'optimization_runs'
                 and column_name = 'recommendation')
            then '있음' else '없음 (실패)' end as 값
union all
select '2. 판정 인덱스',
       case when exists (
              select 1 from pg_indexes
               where schemaname = 'public'
                 and indexname = 'optimization_runs_verdict_idx')
            then '있음' else '없음 (실패)' end
union all
select '3. 정리 함수 갱신',
       case when to_regprocedure('public.prune_optimization_snapshots()') is null
            then '없음 (실패)' else '있음' end
union all
select '4. 기존 이력',
       count(*)::text || '건 (recommendation 은 null 로 시작)'
  from public.optimization_runs;
