-- ============================================================
-- vehicles 표 재생성
--
-- ⚠️ 한 번에 다 실행하지 마세요. [1단계] 를 먼저 돌려 결과를 확인한 뒤
--    [2단계] 를 실행하세요. 이유는 아래에 적었습니다.
--
-- 왜 다시 만드는가
--   지금 DB 의 vehicles 표는 supabase_schema.sql 의 정의와 모양이 아예 다릅니다.
--   vehicle_id, plate_number, vehicle_type, driver_name, start_type 이 없습니다.
--   그래서 배차를 계산할 때마다 돌던 차량 백업이 계속 실패하고 있었습니다.
--   (실패해도 배차가 멈추지 않게 감싸 둬서 로그에만 남았습니다.)
--
-- 왜 CASCADE 를 쓰지 않는가
--   처음 시도에서 routes 라는 표가 vehicles 를 참조한다며 막혔습니다.
--   CASCADE 를 붙이면 뚫리기는 하지만, 제가 모르는 다른 것까지 함께 지워집니다.
--   무엇이 딸려 있는지 눈으로 보고 하나씩 지우는 편이 안전합니다.
-- ============================================================


-- ════════════════════════════════════════════════════════════
-- [1단계] 확인 — 이것부터 실행하고 결과를 보세요.
-- ════════════════════════════════════════════════════════════

-- (1) 이 프로젝트에 어떤 표들이 있는지. 우리가 쓰는 것은 7개입니다.
--     ride_completions, driver_devices, dispatches, dispatch_acks,
--     vehicles, passengers, driver_dispatch_sms
--     그 외에 나오는 이름은 예전에 만들어져 잊힌 것들입니다.
select
  table_name as "표 이름",
  (select count(*) from information_schema.columns c
    where c.table_schema = 'public' and c.table_name = t.table_name) as "칸 수"
from information_schema.tables t
where table_schema = 'public' and table_type = 'BASE TABLE'
order by table_name;

-- (2) vehicles 에 딸려 있는 것이 routes 말고 또 있는지.
select
  con.conname   as "제약 이름",
  src.relname   as "딸려 있는 표"
from pg_constraint con
join pg_class src on src.oid = con.conrelid
where con.confrelid = 'public.vehicles'::regclass;

-- (3) 지워질 데이터가 정말 없는지. 둘 다 0 이어야 합니다.
select 'vehicles' as "표", count(*) as "행수" from public.vehicles
union all
select 'routes', count(*) from public.routes;


-- ════════════════════════════════════════════════════════════
-- [2단계] 재생성 — 위 (2)에 routes 하나만 나오고 (3)이 둘 다 0 이면
--         아래를 실행하세요.
--
--         만약 (2)에 routes 말고 다른 표가 더 나왔다면 멈추고 알려주세요.
--         그 표가 무엇인지 보고 다시 판단해야 합니다.
-- ════════════════════════════════════════════════════════════

-- routes 는 우리 코드가 쓰지 않고 스키마 파일에도 없는 옛 흔적입니다.
-- 0행이므로 지웁니다. 남겨두고 제약만 푸는 것보다 깨끗합니다.
drop table if exists public.routes;

-- CASCADE 를 붙이지 않습니다. 아직 모르는 의존이 남아 있다면
-- 조용히 지워지는 대신 여기서 다시 막혀야 합니다.
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


-- ── 결과 확인 ────────────────────────────────────────────────
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
