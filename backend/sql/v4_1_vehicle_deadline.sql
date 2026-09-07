-- ============================================================
-- 마중ON Care — 차량별 하원 마감 시각 백업 (v4.1)
--
-- Supabase 대시보드 > SQL Editor 에 붙여넣고 실행하세요.
-- 여러 번 실행해도 안전합니다.
--
-- 무엇을 위한 것인가
--   원장님이 차량마다 정한 하원 마감 시각이 지금은 앱 안에만 있습니다.
--   폰을 바꾸거나 앱을 지우면 사라집니다. 다른 설정처럼 함께 백업합니다.
--
--   이 칸이 없어도 배차는 정상 동작합니다. 차량 백업만 이 값을 빼고
--   저장될 뿐입니다. 그래서 급하게 실행하지 않으셔도 됩니다.
-- ============================================================

alter table public.vehicles
  add column if not exists outbound_deadline text;

comment on column public.vehicles.outbound_deadline is
  '이 차량만의 하원 마감 시각(HH:MM). 비어 있으면 센터 공통값을 쓴다.';


-- 확인
select '1. outbound_deadline 칸' as 항목,
       case when exists (
              select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'vehicles'
                 and column_name = 'outbound_deadline')
            then '있음' else '없음 (실패)' end as 값
union all
select '2. 등록 차량', count(*)::text || '대' from public.vehicles;
