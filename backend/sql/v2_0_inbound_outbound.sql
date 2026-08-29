-- ============================================================
-- 마중ON Care v2.0 — 등원/하원 분리
--
-- Supabase 대시보드 > SQL Editor 에 통째로 붙여넣고 실행하세요.
-- 여러 번 실행해도 안전합니다.
--
-- 이 SQL 을 실행한 뒤에 백엔드를 배포해야 합니다. 순서가 바뀌면
-- 새 백엔드가 없는 컬럼에 쓰려다 저장에 실패합니다.
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- 1) passengers 정리
--
-- 지금 251행이 들어 있는데 고유 인원은 36명입니다. 배차를 계산할 때마다
-- 명단 전체가 새 줄로 쌓였기 때문입니다(insert 만 하고 키가 없었음).
-- 원본 명단은 원장님 앱에 있으므로 여기 것은 지우고 다시 채웁니다.
-- 다음 배차 계산 때 앱이 보내는 명단으로 자동 복구됩니다.
-- ────────────────────────────────────────────────────────────
delete from public.passengers;

-- 어르신을 가리키는 키. 앱이 만드는 'passenger-...' 값을 그대로 씁니다.
alter table public.passengers add column if not exists passenger_id text;

-- 하원 희망 시각. 비어 있으면 서버가 센터 공통 기본값으로 채웁니다.
alter table public.passengers add column if not exists dropoff_start text;
alter table public.passengers add column if not exists dropoff_end   text;

-- 등원과 하원의 탑승 여부는 다를 수 있습니다.
-- (아침엔 보호자가 모셔오고 오후엔 센터 차를 타는 경우)
alter table public.passengers
  add column if not exists is_attending_inbound  boolean not null default true;
alter table public.passengers
  add column if not exists is_attending_outbound boolean not null default true;

alter table public.passengers
  add column if not exists updated_at timestamptz not null default now();

-- 위에서 비웠으므로 바로 not null 과 unique 를 걸 수 있습니다.
alter table public.passengers alter column passenger_id set not null;
alter table public.passengers drop constraint if exists passengers_passenger_id_key;
alter table public.passengers add constraint passengers_passenger_id_key
  unique (passenger_id);


-- ────────────────────────────────────────────────────────────
-- 2) 등원/하원 구분 칸
--
-- 지금까지 쌓인 기록은 전부 등원입니다. 기본값을 inbound 로 두면
-- 기존 행과 아직 업데이트하지 않은 구형 앱이 그대로 동작합니다.
-- ────────────────────────────────────────────────────────────
alter table public.ride_completions
  add column if not exists trip_type text not null default 'inbound';
alter table public.dispatches
  add column if not exists trip_type text not null default 'inbound';
alter table public.dispatch_acks
  add column if not exists trip_type text not null default 'inbound';
alter table public.driver_dispatch_sms
  add column if not exists trip_type text not null default 'inbound';

alter table public.ride_completions drop constraint if exists ride_completions_trip_type_check;
alter table public.ride_completions add constraint ride_completions_trip_type_check
  check (trip_type in ('inbound', 'outbound'));

alter table public.dispatches drop constraint if exists dispatches_trip_type_check;
alter table public.dispatches add constraint dispatches_trip_type_check
  check (trip_type in ('inbound', 'outbound'));

alter table public.dispatch_acks drop constraint if exists dispatch_acks_trip_type_check;
alter table public.dispatch_acks add constraint dispatch_acks_trip_type_check
  check (trip_type in ('inbound', 'outbound'));

alter table public.driver_dispatch_sms drop constraint if exists driver_dispatch_sms_trip_type_check;
alter table public.driver_dispatch_sms add constraint driver_dispatch_sms_trip_type_check
  check (trip_type in ('inbound', 'outbound'));


-- ────────────────────────────────────────────────────────────
-- 3) 유일키 교체  ★ 이번 개편에서 가장 중요한 부분 ★
--
-- 지금 ride_completions 는 (운행일, 어르신) 으로 잠겨 있습니다.
-- 이대로 하원을 붙이면 오후 하차 기록이 오전 탑승 기록을 덮어써서
-- 송영 일지에서 오전 시각이 사라집니다.
-- dispatches / dispatch_acks / driver_dispatch_sms 도 같은 문제입니다.
-- ────────────────────────────────────────────────────────────
alter table public.ride_completions
  drop constraint if exists ride_completions_day_passenger_key;
alter table public.ride_completions
  add constraint ride_completions_day_passenger_trip_key
  unique (service_date, passenger_id, trip_type);

alter table public.dispatches
  drop constraint if exists dispatches_service_date_key;
alter table public.dispatches
  add constraint dispatches_date_trip_key
  unique (service_date, trip_type);

alter table public.dispatch_acks
  drop constraint if exists dispatch_acks_day_vehicle_key;
alter table public.dispatch_acks
  add constraint dispatch_acks_day_vehicle_trip_key
  unique (service_date, vehicle_id, trip_type);

alter table public.driver_dispatch_sms
  drop constraint if exists driver_dispatch_sms_date_vehicle_key;
alter table public.driver_dispatch_sms
  add constraint driver_dispatch_sms_date_vehicle_trip_key
  unique (service_date, vehicle_id, trip_type);


-- ────────────────────────────────────────────────────────────
-- 4) 확인
-- ────────────────────────────────────────────────────────────
select 'passengers 남은 행수' as 항목, count(*)::text as 값 from public.passengers
union all
select 'ride_completions 유일키',
       string_agg(a.attname, ', ' order by a.attnum)
  from pg_constraint c
  join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey)
 where c.conname = 'ride_completions_day_passenger_trip_key'
union all
select 'dispatches 유일키',
       string_agg(a.attname, ', ' order by a.attnum)
  from pg_constraint c
  join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey)
 where c.conname = 'dispatches_date_trip_key';
