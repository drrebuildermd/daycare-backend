-- ============================================================
-- vehicles 표 재생성
--
-- Supabase 대시보드 > SQL Editor 에 통째로 붙여넣고 실행하세요.
--
-- 왜 다시 만드는가
--   지금 DB 의 vehicles 표는 supabase_schema.sql 의 정의와 모양이 아예 다릅니다.
--   vehicle_id, plate_number, vehicle_type, driver_name, start_type 이 없고
--   name 같은 엉뚱한 칸이 들어 있습니다. 언제 만들어진 것인지 알 수 없습니다.
--
--   그래서 배차를 계산할 때마다 돌던 차량 백업이 계속 실패하고 있었습니다.
--   (실패해도 배차가 멈추지 않게 감싸 둬서 로그에만 남았습니다.)
--
-- 안전한가
--   실행 직전에 확인했을 때 이 표는 0행입니다. 지울 데이터가 없습니다.
--   차량 명단의 원본은 원장님 앱에 있고, 이 표는 백업일 뿐입니다.
--   다음 배차 계산 때 앱이 보내는 차량으로 자동으로 다시 채워집니다.
--
--   이 표를 읽는 코드는 없습니다. 쓰기만 합니다. (main.py 의 _archive_vehicles)
-- ============================================================

-- 혹시 모르니 먼저 눈으로 확인하세요. 0 이 나와야 합니다.
select count(*) as "지워질 행수" from public.vehicles;


-- ── 재생성 ────────────────────────────────────────────────────
drop table if exists public.vehicles;

create table public.vehicles (
  id              bigserial   primary key,
  -- 앱이 만드는 차량 식별자. 이 표는 날짜별 기록이 아니라 '지금 차량'의
  -- 거울이므로 한 대당 한 줄이면 된다. 이 키로 덮어쓴다.
  vehicle_id      text        not null,
  vehicle_type    text        not null,
  plate_number    text        not null,
  driver_name     text,
  -- 배차가 확정되면 이 번호로 안내 문자를 보낸다.
  driver_phone    text,
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

-- 다른 표와 같은 기준으로 잠근다. 서버는 secret 키로 접근하므로 영향이 없고,
-- 외부에서 공개 키로 들여다보는 것만 막힌다.
alter table public.vehicles enable row level security;


-- ── 확인 ─────────────────────────────────────────────────────
select '칸 목록' as 항목,
       string_agg(column_name, ', ' order by ordinal_position) as 값
  from information_schema.columns
 where table_schema = 'public' and table_name = 'vehicles'
union all
select '유일키',
       string_agg(a.attname, ', ' order by a.attnum)
  from pg_constraint c
  join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey)
 where c.conname = 'vehicles_vehicle_id_key'
union all
select 'RLS 켜짐',
       case when relrowsecurity then '예' else '아니오' end
  from pg_class where oid = 'public.vehicles'::regclass;
