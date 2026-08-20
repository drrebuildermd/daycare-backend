-- 송영 최적화 - Supabase 스키마
--
-- 실행 방법: Supabase 대시보드 > SQL Editor > New query 에 붙여넣고 Run.
-- 전부 IF NOT EXISTS 라서 여러 번 실행해도 안전합니다.

-- ---------------------------------------------------------------------------
-- 1. 송영 완료 기록 (기존 SQLite ride_completions 이관)
-- ---------------------------------------------------------------------------
create table if not exists public.ride_completions (
  id                   bigserial primary key,
  -- 운행일은 KST 기준 날짜다. 서버가 UTC로 돌아도 한국 날짜로 묶이도록
  -- 애플리케이션에서 계산해 넣는다.
  service_date         date        not null,
  passenger_id         text        not null,
  passenger_name       text        not null,
  vehicle_id           text        not null,
  vehicle_type         text        not null,
  vehicle_plate_number text        not null,
  trip_round           smallint    not null check (trip_round in (1, 2)),
  scheduled_pickup     text        not null,
  completed_at         timestamptz not null,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  -- 같은 날 같은 어르신은 한 줄만. 재탭 시 갱신되도록 upsert 키로 쓴다.
  constraint ride_completions_day_passenger_key unique (service_date, passenger_id)
);

create index if not exists idx_ride_completions_date_time
  on public.ride_completions (service_date, completed_at);

-- ---------------------------------------------------------------------------
-- 2. 기사님 기기 토큰 (3번 과제: Expo 푸시 알림 대비)
-- ---------------------------------------------------------------------------
create table if not exists public.driver_devices (
  id              bigserial primary key,
  driver_name     text        not null,
  -- Expo가 기기마다 발급하는 값. 같은 토큰이 여러 기사에게 붙으면 안 되므로 유니크.
  expo_push_token text        not null,
  -- "갤럭시 S23", "업무용 태블릿" 처럼 기사님이 기기를 구분하는 이름.
  device_label    text,
  -- 기기를 반납/교체해도 이력은 남기고 발송 대상에서만 뺀다.
  is_active       boolean     not null default true,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint driver_devices_token_key unique (expo_push_token)
);

create index if not exists idx_driver_devices_driver
  on public.driver_devices (driver_name) where is_active;

-- ---------------------------------------------------------------------------
-- 3. 오늘의 배차 결과 (기사님 폰이 내려받아 지도를 그린다)
-- ---------------------------------------------------------------------------
-- 푸시 알림 본문에는 경로를 다 담을 수 없다(Expo 페이로드 4KB 제한).
-- 알림에는 vehicle_id만 넣고, 실제 경로는 앱이 여기서 받아간다.
create table if not exists public.dispatches (
  id           bigserial primary key,
  service_date date        not null,
  payload      jsonb       not null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint dispatches_service_date_key unique (service_date)
);

-- ---------------------------------------------------------------------------
-- 4. 어르신 명단 백업 (기존 테이블에 누락 컬럼 보강)
-- ---------------------------------------------------------------------------
create table if not exists public.passengers (
  id             bigserial primary key,
  name           text not null,
  address        text,
  detail_address text,
  latitude       double precision,
  longitude      double precision,
  pickup_start   text,
  pickup_end     text,
  is_wheelchair  boolean default false,
  created_at     timestamptz not null default now()
);

-- 이미 테이블이 있는 경우를 대비해 컬럼만 따로 보강한다.
alter table public.passengers add column if not exists detail_address text;


-- ===========================================================================
-- 5. 보안 (RLS) - 아래는 별도로 확인하고 실행하세요
-- ===========================================================================
--
-- 이 테이블들에는 어르신 성함과 자택 주소가 들어갑니다.
-- Supabase 테이블은 RLS를 켜지 않으면 anon 키만으로 외부에서 전량 조회가 가능합니다.
-- anon 키는 앱에 노출되는 공개 키이므로, 아래 두 가지를 반드시 함께 적용하세요.
--
--   (1) 백엔드 .env 의 SUPABASE_KEY 를 'service_role' 키로 교체
--       (service_role 키는 RLS를 우회합니다. 절대 프론트엔드에 넣지 마세요.)
--   (2) 아래 SQL 실행
--
-- 정책을 만들지 않고 RLS만 켜면 anon 키로는 아무것도 못 읽습니다.
-- 백엔드는 service_role 키를 쓰므로 정상 동작합니다.
--
-- alter table public.ride_completions enable row level security;
-- alter table public.dispatches        enable row level security;
-- alter table public.driver_devices    enable row level security;
-- alter table public.passengers        enable row level security;
