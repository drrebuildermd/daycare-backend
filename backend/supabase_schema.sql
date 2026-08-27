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
-- 4. 배차표 확인 (기사 -> 관리자 양방향 소통)
-- ---------------------------------------------------------------------------
-- 기사님이 오늘 배차표를 봤다는 것을 관리자 화면에서 알 수 있어야
-- "못 봤다 / 전달했다" 하는 현장 소통 오류가 줄어든다.
create table if not exists public.dispatch_acks (
  id              bigserial primary key,
  service_date    date        not null,
  vehicle_id      text        not null,
  vehicle_label   text        not null,
  driver_name     text,
  acknowledged_at timestamptz not null,
  created_at      timestamptz not null default now(),
  -- 같은 날 같은 차량은 한 줄만. 다시 눌러도 시각만 갱신된다.
  constraint dispatch_acks_day_vehicle_key unique (service_date, vehicle_id)
);

create index if not exists idx_dispatch_acks_date
  on public.dispatch_acks (service_date);

-- ---------------------------------------------------------------------------
-- 5. 차량 백업 (자차 송영 출발지 포함)
-- ---------------------------------------------------------------------------
-- 차량은 관리자 앱의 로컬 저장소가 원본이고, 배차할 때마다 여기에 백업된다.
-- 관리자 폰을 잃어버려도 어떤 차량이 어떤 출발지로 운행했는지 남는다.
create table if not exists public.vehicles (
  id              bigserial primary key,
  vehicle_id      text        not null,
  vehicle_type    text        not null,
  plate_number    text        not null,
  driver_name     text,
  capacity        integer     not null,
  -- 'center' 면 센터에서, 'custom' 이면 아래 주소에서 1회차를 시작한다.
  start_type      text        not null default 'center'
                    check (start_type in ('center', 'custom')),
  start_address   text,
  start_latitude  double precision,
  start_longitude double precision,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint vehicles_vehicle_id_key unique (vehicle_id)
);

-- 이미 테이블이 있는 경우를 대비해 컬럼만 따로 보강한다.
alter table public.vehicles add column if not exists start_type text default 'center';
alter table public.vehicles add column if not exists start_address text;
alter table public.vehicles add column if not exists start_latitude double precision;
alter table public.vehicles add column if not exists start_longitude double precision;

-- ---------------------------------------------------------------------------
-- 6. 어르신 명단 백업 (기존 테이블에 누락 컬럼 보강)
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
-- 7. 보안 (RLS) - 순서를 반드시 지키세요
-- ===========================================================================
--
-- 이 테이블들에는 어르신 성함, 자택 주소, 보호자 연락처가 들어갑니다.
-- RLS 를 켜지 않으면 공개용 키만으로 외부에서 전량 조회가 가능합니다.
-- 그 키는 앱 번들에 박혀 배포되므로, 앱을 받은 사람은 누구나 꺼낼 수 있습니다.
--
-- 그런데 RLS 를 먼저 켜면 서비스가 즉시 멈춥니다.
-- 공개용 키도 RLS 의 적용을 받기 때문에, 백엔드가 공개용 키를 쓰는 동안에는
-- 테이블에 접근하지 못하고 서버가 기동조차 하지 못합니다.
--
-- 아래 순서를 그대로 따르세요.
--
--   1) Supabase > Project Settings > API Keys 에서 secret 키를 발급합니다.
--      (sb_secret_... 로 시작. 구형 프로젝트는 service_role 키)
--      이 키는 RLS 를 우회합니다. 절대 프론트엔드나 저장소에 넣지 마세요.
--
--   2) backend/.env 와 Render 대시보드 Environment 의 SUPABASE_KEY 를
--      그 secret 키로 교체하고 재배포합니다.
--
--   3) 교체가 반영됐는지 확인합니다. 'secret' 이 나와야 합니다.
--      curl -s https://daycare-routing-api.onrender.com/api/health
--      -> {"supabase_key_kind":"secret", ...}
--
--      'publishable' 이 나오면 4번을 실행하지 마세요. 서버가 죽습니다.
--
--   4) 아래 SQL 을 실행합니다.

-- alter table public.ride_completions enable row level security;
-- alter table public.dispatches        enable row level security;
-- alter table public.driver_devices    enable row level security;
-- alter table public.passengers        enable row level security;
-- alter table public.vehicles          enable row level security;
-- alter table public.dispatch_acks     enable row level security;

--
--   5) 다시 /api/health 가 200 인지, 배차와 탑승완료가 동작하는지 확인합니다.
--
-- 참고: 정책(policy)을 만들지 않으면 공개용 키로는 아무것도 읽지 못합니다.
-- 이는 의도된 것입니다. 백엔드만 secret 키로 접근하면 됩니다.
--
-- 다만 앱의 '실시간 갱신'(수파베이스 직접 구독)은 공개용 키를 쓰므로 함께 멈춥니다.
-- 이 앱에는 로그인이 없어 "우리 앱만 허용"하는 정책을 만들 수 없습니다.
-- anon 에게 SELECT 를 열면 곧 전체 공개와 같습니다.
-- 실시간이 필요하면 백엔드 경유 방식으로 다시 만들거나 Supabase Auth 를 붙이세요.
