-- ============================================================
-- 마중ON Care — 휠체어 하드 제약 (v3.1)
--
-- Supabase 대시보드 > SQL Editor 에 통째로 붙여넣고 실행하세요.
-- 여러 번 실행해도 안전합니다.
--
-- 이 SQL 을 실행한 뒤에 백엔드를 배포하세요.
--
-- 무엇이 달라지나
--   지금까지 '휠체어 이용' 표시는 화면에 배지로만 떴고 엔진은 보지 않았습니다.
--   리프트 없는 차에 휠체어 어르신이 배정돼도 아무 말이 없었습니다.
--
--   이제 차량마다 휠체어 고정석이 몇 자리인지 받아, 그 수를 넘겨 태우지
--   못하게 합니다. 0 이면 휠체어 어르신이 아예 배정되지 않습니다.
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- 1) 차량의 휠체어 고정석 수
--
-- 일반 정원(capacity)과 별개입니다. 어르신이 휠체어에서 내려 일반 좌석에
-- 앉는 경우도 있고 휠체어째 리프트석에 고정하는 경우도 있어서, 두 가지를
-- 한 숫자로 뭉뚱그리면 어느 쪽도 맞지 않습니다.
--
-- 기본값 0 = 리프트 없음. 이미 등록된 차량은 전부 '리프트 없음'이 됩니다.
-- 안전한 쪽으로 기울인 기본값입니다. 리프트가 있는데 0으로 두면 그 차를
-- 못 쓸 뿐이지만, 없는데 1로 두면 못 태울 분을 태우라고 지시하게 됩니다.
-- ────────────────────────────────────────────────────────────
alter table public.vehicles
  add column if not exists wheelchair_capacity integer not null default 0;

alter table public.vehicles
  drop constraint if exists vehicles_wheelchair_capacity_check;
alter table public.vehicles
  add constraint vehicles_wheelchair_capacity_check
  check (wheelchair_capacity >= 0 and wheelchair_capacity <= capacity);

comment on column public.vehicles.wheelchair_capacity is
  '휠체어 고정석 수. 0 이면 리프트 없는 차량이라 휠체어 어르신을 배정하지 않는다.';


-- ────────────────────────────────────────────────────────────
-- 2) 확인 — 아래 결과가 나오면 성공입니다.
-- ────────────────────────────────────────────────────────────
select '1. wheelchair_capacity 칸' as 항목,
       case when exists (
              select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'vehicles'
                 and column_name = 'wheelchair_capacity')
            then '있음' else '없음 (실패)' end as 값
union all
select '2. 기본값',
       coalesce((select column_default from information_schema.columns
                  where table_schema = 'public' and table_name = 'vehicles'
                    and column_name = 'wheelchair_capacity'), '없음 (실패)')
union all
select '3. 정원 초과 방지 검사',
       case when exists (
              select 1 from pg_constraint
               where conname = 'vehicles_wheelchair_capacity_check')
            then '있음' else '없음 (실패)' end
union all
select '4. 기존 차량',
       coalesce(count(*)::text || '대 (전부 리프트 없음 0 으로 시작)', '0대')
  from public.vehicles;
