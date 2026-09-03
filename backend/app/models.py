from typing import Annotated, Literal

# 등원(inbound)은 어르신을 센터로 모셔오는 운행,
# 하원(outbound)은 댁으로 모셔다드리는 운행이다.
# 기본값을 등원으로 두면 이 값을 모르는 구형 앱이 그대로 동작한다.
TripType = Literal["inbound", "outbound"]

from pydantic import BaseModel, Field, field_validator, model_validator


Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


def parse_hhmm(value: str) -> int:
    try:
        hour_text, minute_text = value.strip().split(":", maxsplit=1)
        hour, minute = int(hour_text), int(minute_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("시간은 HH:MM 형식이어야 합니다.") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("시간은 00:00부터 23:59 사이여야 합니다.")
    return hour * 60 + minute


def shift_hhmm(value: str, minutes: int) -> str:
    """시각을 분 단위로 옮긴다. 자정을 넘기면 23:59 에서 멈춘다."""
    return format_hhmm(min(parse_hhmm(value) + minutes, 24 * 60 - 1))


def format_hhmm(minutes: int) -> str:
    minutes = max(0, int(minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class LocationInput(BaseModel):
    name: str = "주야간보호센터"
    address: str = Field(min_length=2)
    latitude: Latitude | None = None
    longitude: Longitude | None = None

    @model_validator(mode="after")
    def coordinates_are_a_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("위도와 경도는 함께 입력해야 합니다.")
        return self


class PassengerInput(LocationInput):
    name: str = Field(min_length=1)
    id: str | None = None
    # 동/호수. 지오코딩에는 쓰지 않고 기사님 화면 표시용으로만 전달한다.
    detail_address: str | None = Field(default=None, max_length=100)
    # 결석해도 명단에서 지우지 않는다. 배차 대상에서만 빠진다.
    # 아침엔 보호자가 모셔오고 오후엔 센터 차를 타는 분이 있어
    # 등원과 하원의 탑승 여부를 따로 둔다.
    attending: bool = True
    attending_outbound: bool = True
    pickup_start: str
    pickup_end: str
    # 하원 희망 시각. 비워두면 센터 공통 기본값을 서버가 채운다.
    dropoff_start: str | None = None
    dropoff_end: str | None = None
    wheelchair: bool = False
    # 장기요양 등급(1~5). 수가가 등급마다 달라 재무 비교에 쓴다.
    # 비워 두면 센터 기본 등급으로 본다.
    care_grade: int | None = Field(default=None, ge=1, le=5)
    # 센터가 계획하고 청구하는 이용시간. 비워 두면 센터 공통값(8시간)을 쓴다.
    planned_service_hours: float | None = Field(default=None, gt=0, le=24)
    guardian_phone: str | None = Field(default=None, max_length=20)
    # 어르신 본인 휴대폰. 대표 연락처를 '본인'으로 두면 여기로 전화한다.
    passenger_phone: str | None = Field(default=None, max_length=20)
    # 기사님 📞 버튼이 누구에게 걸지. 문자는 이 값과 무관하게 보호자에게 간다.
    primary_contact: Literal["guardian", "self"] = "guardian"
    # 알림을 원치 않는 보호자가 있다. 끄면 탑승 완료 문자를 보내지 않는다.
    sms_opt_in: bool = True

    @field_validator("pickup_start", "pickup_end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parse_hhmm(value)
        return value

    @field_validator("dropoff_start", "dropoff_end")
    @classmethod
    def validate_optional_time(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parse_hhmm(value)
        return value

    @model_validator(mode="after")
    def validate_window(self):
        if parse_hhmm(self.pickup_start) > parse_hhmm(self.pickup_end):
            raise ValueError("픽업 하한 시간은 상한 시간보다 늦을 수 없습니다.")
        if self.dropoff_start and self.dropoff_end:
            if parse_hhmm(self.dropoff_start) > parse_hhmm(self.dropoff_end):
                raise ValueError("하원 하한 시간은 상한 시간보다 늦을 수 없습니다.")
        return self

    def is_attending(self, trip_type: str) -> bool:
        return self.attending_outbound if trip_type == "outbound" else self.attending

    def window(self, trip_type: str, stay_minutes: int) -> tuple[str, str]:
        """이 어르신의 시간창.

        하원 시각을 따로 적었으면 그것을 쓴다. 비어 있으면 등원 시각에
        머무시는 시간을 더한다. 주야간보호는 어르신이 8시간을 채우셔야 하므로
        일찍 오신 분이 일찍 가시고 늦게 오신 분이 늦게 가신다.
        한 시각으로 묶으면 일찍 오신 분이 8시간을 넘겨 머물게 된다.

        하한과 상한을 따로 본다. 한쪽만 적어둔 경우에도 나머지가 채워진다.
        """
        if trip_type != "outbound":
            return (self.pickup_start, self.pickup_end)
        return (
            self.dropoff_start or shift_hhmm(self.pickup_start, stay_minutes),
            self.dropoff_end or shift_hhmm(self.pickup_end, stay_minutes),
        )


class VehicleInput(BaseModel):
    id: str | None = None
    vehicle_type: str = Field(min_length=1, max_length=50)
    plate_number: str = Field(min_length=1, max_length=30)
    driver_name: str | None = Field(default=None, max_length=30)
    # 배차가 확정되면 이 번호로 안내 문자를 보낸다.
    driver_phone: str | None = Field(default=None, max_length=20)
    capacity: int = Field(ge=1, le=100)
    # 휠체어 고정석 수. 일반 정원과 별개로 센다.
    # 어르신이 휠체어에서 내려 일반 좌석에 앉기도 하고 휠체어째 리프트석에
    # 고정하기도 해서, 한 숫자로 뭉뚱그리면 어느 쪽도 맞지 않는다.
    # 0 이면 리프트 없는 차량이고 휠체어 어르신이 배정되지 않는다.
    wheelchair_capacity: int = Field(default=0, ge=0, le=100)
    # 이 차량만의 하원 마감 시각. 비워 두면 센터 공통값을 쓴다.
    # 자차 기사님은 센터로 돌아오지 않으므로 조금 늦게 잡기도 한다.
    outbound_deadline: str | None = None
    # 자차 송영: 기사님이 센터가 아니라 자택 등에서 출발하는 경우.
    # 'center' 면 센터에서, 'custom' 이면 start_address 에서 출발한다.
    start_type: Literal["center", "custom"] = "center"
    start_address: str | None = Field(default=None, max_length=200)
    start_latitude: Latitude | None = None
    start_longitude: Longitude | None = None

    @field_validator("outbound_deadline")
    @classmethod
    def validate_deadline(cls, value: str | None) -> str | None:
        if value:
            parse_hhmm(value)
        return value

    @model_validator(mode="after")
    def wheelchair_seats_fit(self):
        # 휠체어석이 전체 정원보다 많을 수는 없다.
        if self.wheelchair_capacity > self.capacity:
            raise ValueError(
                f"{self.plate_number} 차량의 휠체어석({self.wheelchair_capacity}자리)이 "
                f"총 정원({self.capacity}명)보다 많습니다."
            )
        return self

    @model_validator(mode="after")
    def custom_start_needs_address(self):
        if self.start_type == "custom" and not (self.start_address or "").strip():
            raise ValueError(
                f"{self.plate_number} 차량은 자차 출발로 설정됐지만 출발지 주소가 없습니다."
            )
        if (self.start_latitude is None) != (self.start_longitude is None):
            raise ValueError("출발지 위도와 경도는 함께 입력해야 합니다.")
        return self

    def as_start_location(self) -> LocationInput | None:
        """지오코딩에 넘길 출발지. 센터 출발이면 None."""
        if self.start_type != "custom":
            return None
        return LocationInput(
            name=f"{self.plate_number} 출발지",
            address=(self.start_address or "").strip(),
            latitude=self.start_latitude,
            longitude=self.start_longitude,
        )


class PairRule(BaseModel):
    """어르신 두 분 사이의 동승 규칙."""

    passenger_ids: list[str] = Field(min_length=2, max_length=2)

    @field_validator("passenger_ids")
    @classmethod
    def two_distinct_ids(cls, value: list[str]) -> list[str]:
        if value[0] == value[1]:
            raise ValueError("같은 어르신끼리는 동승 규칙을 만들 수 없습니다.")
        return value

    @property
    def pair(self) -> tuple[str, str]:
        return (self.passenger_ids[0], self.passenger_ids[1])


class OptimizeRequest(BaseModel):
    # 이 배차가 등원인지 하원인지. 구형 앱은 보내지 않으므로 등원으로 본다.
    trip_type: TripType = "inbound"
    center: LocationInput
    vehicles: list[VehicleInput] = Field(min_length=1)
    passengers: list[PassengerInput] = Field(min_length=1)
    # 같은 차·같은 회차에 함께 태우면 안 되는 조합 (기피)
    forbidden_pairs: list[PairRule] = Field(default_factory=list)
    # 반드시 같은 차·같은 회차에 함께 태워야 하는 조합 (짝꿍)
    required_pairs: list[PairRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def pair_rules_reference_known_passengers(self):
        # 명단에 아예 없는 id 만 막는다. 오타나 지워진 어르신을 가리키는 규칙은
        # 데이터 오류라서 일찍 잡아야 한다.
        #
        # 탑승 여부는 여기서 보지 않는다. 등원만 타시는 분, 하원만 타시는 분이
        # 있어서 '타는가' 는 계산하는 방향마다 답이 다르기 때문이다. 예전에는
        # 여기서 등원 스위치만 보고 막는 바람에, 하원만 타시는 분이 낀 규칙
        # 하나 때문에 등원 배차 전체가 422 로 거절됐다.
        # 이번 방향에 안 타시는 분이 낀 규칙은 main.py 가 빼고 안내한다.
        known = {passenger.id for passenger in self.passengers if passenger.id}
        for label, rules in (("동승 불가", self.forbidden_pairs), ("필수 동승", self.required_pairs)):
            for rule in rules:
                unknown = [pid for pid in rule.passenger_ids if pid not in known]
                if unknown:
                    raise ValueError(
                        f"{label} 규칙이 명단에 없는 어르신을 가리킵니다: {', '.join(unknown)}"
                    )
        return self


class StopResult(BaseModel):
    sequence: int
    passenger_id: str
    name: str
    address: str
    detail_address: str | None = None
    # 기사님 폰에는 어르신 명단이 없다. 문자를 보낼 번호도, 전화를 걸 번호도,
    # 문자를 보낼지 말지도 모두 배차 결과에 실어 보내야 한다.
    guardian_phone: str | None = None
    passenger_phone: str | None = None
    primary_contact: Literal["guardian", "self"] = "guardian"
    sms_opt_in: bool = True
    latitude: float
    longitude: float
    wheelchair: bool
    requested_window: str
    estimated_pickup: str
    kakao_navi_url: str


class TripResult(BaseModel):
    # 이 회차가 실제로 어디서 떠나 어디서 끝나는지.
    # 하원 마지막 회차는 센터가 아니라 기사님 자택에서 끝난다.
    #
    # 앱이 '자차면 1회차는 자택 출발' 이라고 짐작하면 하원에서 틀린다.
    # 내비게이션 출발지도 여기서 가져가야 엉뚱한 곳에서 길을 잡지 않는다.
    origin_name: str | None = None
    origin_latitude: float | None = None
    origin_longitude: float | None = None
    destination_name: str | None = None
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    round: int
    used: bool
    passenger_count: int
    capacity: int
    departure_time: str | None = None
    return_time: str | None = None
    distance_km: float = 0
    stops: list[StopResult] = Field(default_factory=list)


class VehicleResult(BaseModel):
    vehicle_id: str
    vehicle_type: str
    plate_number: str
    driver_name: str | None = None
    driver_phone: str | None = None
    capacity: int
    # 1회차 출발지. 자차 송영이면 기사님 자택, 아니면 센터.
    # start_name 은 센터 출발이면 센터명(예: 수주간보호센터)이 들어간다.
    start_type: Literal["center", "custom"] = "center"
    start_name: str | None = None
    start_address: str | None = None
    start_latitude: float | None = None
    start_longitude: float | None = None
    trips: list[TripResult]


class CenterResult(BaseModel):
    name: str
    address: str
    latitude: float
    longitude: float


class ObjectiveBreakdown(BaseModel):
    """솔버가 무엇을 얼마나 비싸게 봤는지 항목별로 나눈 것.

    OR-Tools 는 총합만 돌려주고 항목별 기여도를 주지 않는다. 그래서 해를 받은 뒤
    같은 계수로 다시 계산한다. 값의 단위는 미터다. 거리 1m 가 1이다.

    나중에 '왜 경로 A 가 아니라 B 였나' 를 물으면 이 값들이 답이 된다.
    """

    distance_m: int = 0
    second_run_count: int = 0
    second_run_penalty: int = 0
    time_span_minutes: int = 0
    time_span_penalty: int = 0
    unassigned_count: int = 0
    unassigned_penalty: int = 0
    total: int = 0


class UnassignedPassenger(BaseModel):
    """배차에 넣지 못한 어르신.

    정원이 모자라거나 희망 시각을 지킬 방법이 없을 때 생긴다.
    전체를 실패로 돌리면 원장님은 무엇을 고쳐야 할지 알 수 없다.
    누가 왜 빠졌는지 알려주고 나머지는 그대로 쓰게 한다.
    """

    passenger_id: str
    name: str
    requested_window: str
    # 왜 빠졌는지. 원장님이 무엇을 고쳐야 할지 알아야 한다.
    #   capacity  - 정원이나 시간이 안 맞음
    #   wheelchair - 휠체어 고정석이 있는 차량이 모자람
    reason: Literal["capacity", "wheelchair"] = "capacity"
    # 휠체어를 쓰는 분인지. 화면에서 아이콘을 붙이는 데 쓴다.
    wheelchair: bool = False


class RecommendationAction(BaseModel):
    """원장님이 실제로 손볼 수 있는 한 가지 조치."""

    passenger_id: str
    name: str
    # 지금 설정된 희망 시각
    current_window: str
    # 이렇게 바꾸면 배차된다
    suggested_window: str
    delta_minutes: int
    # 완화한 판에서 실제로 몇 시에 도착하는지. 창을 넓히라고만 하면
    # 얼마나 넓혀야 하는지 감이 안 온다.
    scheduled_time: str | None = None


class RecommendationOption(BaseModel):
    """대안 하나. 우선순위가 낮을수록 먼저 시도한 것이다."""

    priority: int
    # time / rounds / structural
    kind: Literal["adjust_time", "add_round", "structural"]
    feasible: bool
    headline: str
    detail: str | None = None
    actions: list[RecommendationAction] = Field(default_factory=list)
    # 이 대안을 쓰면 몇 분이 더 타실 수 있는지
    resolves_count: int = 0


class RevenueLossEntry(BaseModel):
    """수가가 깎이는 어르신 한 분."""

    passenger_id: str
    name: str
    care_grade: int
    planned_hours: float
    actual_hours: float
    planned_band: str
    actual_band: str
    lost_won: int


class ScenarioCostView(BaseModel):
    """한 가지 운영 방식의 하루 비용."""

    label: str
    distance_km: float
    fuel_won: int = 0
    fixed_won: int = 0
    revenue_loss_won: int = 0
    total_won: int = 0
    revenue_loss_items: list[RevenueLossEntry] = Field(default_factory=list)


class FinancialComparison(BaseModel):
    """3회차로 버티는 것과 차를 늘리는 것 중 어느 쪽이 싼가.

    인건비는 넣지 않는다. 운전은 이미 급여가 나가는 요양보호사가 맡으므로
    3회차를 돌아도 연장수당이나 신규 고용이 생기지 않는다.
    """

    # 수가 감소를 비용에 넣고 계산했는가
    consider_revenue_loss: bool
    scenario_a: ScenarioCostView
    scenario_b: ScenarioCostView
    # 어느 쪽을 권하는가. 판단할 수 없으면 None.
    recommended: Literal["add_round", "add_vehicle"] | None = None
    difference_won: int = 0
    headline: str = ""
    # 수가표에 없는 조합이 있어 판정을 보류한 경우 등
    notes: list[str] = Field(default_factory=list)


class RecommendationReport(BaseModel):
    """배차가 안 된 이유와, 어떻게 하면 되는지.

    '휠체어석이 부족해서 N명 누락' 까지만 말하면 원장님은 그래서 무엇을
    해야 하는지 알 수 없다. 시간을 조절할지, 회차를 늘릴지, 차를 늘려야
    하는지까지 답해야 쓸모가 있다.
    """

    verdict: Literal[
        "all_assigned",      # 애초에 빠진 분이 없다
        "time_relaxable",    # 시간만 조절하면 된다
        "needs_extra_round", # 회차를 늘리면 된다
        "structural",        # 차가 모자란다
    ]
    unassigned_count: int = 0
    options: list[RecommendationOption] = Field(default_factory=list)
    analyzed_seconds: float = 0.0
    # 어느 계산에 대한 분석인지. 나중에 '제안을 받아들였나' 를 보려면 필요하다.
    optimization_run_id: str | None = None
    # 3회차와 증차 중 어느 쪽이 싼가. 회차 추가가 가능할 때만 채워진다.
    financials: FinancialComparison | None = None


class RecommendRequest(BaseModel):
    """대안 분석 요청.

    배차 계산과 같은 입력에, '누가 빠졌는지' 를 함께 받는다. 다시 풀어서
    찾을 수도 있지만 그러면 화면에 보이는 결과와 다른 답이 나올 수 있다.
    원장님이 보고 계신 그 결과를 그대로 분석해야 말이 맞는다.
    """

    request: OptimizeRequest
    unassigned_passenger_ids: list[str] = Field(default_factory=list)
    optimization_run_id: str | None = None
    # 조기 하원에 따른 수가 감소를 비용에 넣을지.
    # 기본은 넣는다. 조기 하원이 매출에 영향을 주는 것이 원칙이고,
    # 보수적인 쪽이 기본이어야 한다.
    consider_revenue_loss: bool = True


class OptimizeResponse(BaseModel):
    trip_type: TripType = "inbound"
    status: str
    center: CenterResult
    total_passengers: int
    total_distance_km: float
    solve_seconds: float
    vehicles: list[VehicleResult]
    notices: list[str] = Field(default_factory=list)
    # 물리적으로 태울 방법이 없어 빠진 어르신. 비어 있으면 전원 배차됐다는 뜻이다.
    unassigned_passengers: list[UnassignedPassenger] = Field(default_factory=list)
    # 이 계산이 남긴 이력의 식별자. 배차를 전송할 때 이 값을 함께 보내면
    # 최종안이 어느 원안에서 나왔는지 이어진다.
    optimization_run_id: str | None = None
    # 솔버가 무엇을 얼마나 비싸게 봤는지.
    objective_breakdown: ObjectiveBreakdown | None = None


class RideCompletionCreate(BaseModel):
    # 오전 탑승과 오후 하차는 따로 남아야 한다. 같은 키로 저장하면 덮어쓴다.
    trip_type: TripType = "inbound"
    passenger_id: str = Field(min_length=1, max_length=100)
    passenger_name: str = Field(min_length=1, max_length=100)
    vehicle_id: str = Field(min_length=1, max_length=100)
    vehicle_type: str = Field(min_length=1, max_length=50)
    vehicle_plate_number: str = Field(min_length=1, max_length=30)
    trip_round: int = Field(ge=1, le=2)
    scheduled_pickup: str
    center_name: str | None = None      # 🚨 [신규 장착] 발송용 센터명
    guardian_phone: str | None = None   # 🚨 [신규 장착] 발송용 보호자 번호
    # 보호자가 알림을 껐으면 문자를 보내지 않는다.
    sms_opt_in: bool = True

    @field_validator("scheduled_pickup")
    @classmethod
    def validate_scheduled_pickup(cls, value: str) -> str:
        parse_hhmm(value)
        return value


class RideCompletionRecord(RideCompletionCreate):
    service_date: str
    completed_at: str
    created_at: str
    updated_at: str
    # 문자 발송 결과. DB에 저장하지 않고 응답에만 실린다.
    # 이게 없으면 발송 실패가 서버 로그에만 남아 아무도 모른다.
    sms_sent: bool | None = None
    sms_message: str | None = None


class RideCompletionList(BaseModel):
    trip_type: TripType | None = None
    service_date: str
    records: list[RideCompletionRecord] = Field(default_factory=list)


class DriverDeviceCreate(BaseModel):
    driver_name: str = Field(min_length=1, max_length=30)
    expo_push_token: str = Field(min_length=1, max_length=200)
    device_label: str | None = Field(default=None, max_length=50)

    @field_validator("expo_push_token")
    @classmethod
    def looks_like_expo_token(cls, value: str) -> str:
        token = value.strip()
        if not (
            token.startswith(("ExponentPushToken[", "ExpoPushToken["))
            and token.endswith("]")
        ):
            raise ValueError(
                "Expo 푸시 토큰 형식이 아닙니다. ExponentPushToken[...] 형태여야 합니다."
            )
        return token


class DriverDeviceRecord(DriverDeviceCreate):
    id: int
    is_active: bool
    created_at: str
    updated_at: str


class DriverDeviceList(BaseModel):
    devices: list[DriverDeviceRecord] = Field(default_factory=list)


class DriverNotifyOutcome(BaseModel):
    vehicle_label: str
    driver_name: str | None = None
    sent: int = 0
    message: str


class DispatchNotifyResult(BaseModel):
    sent: int = 0
    failed: int = 0
    outcomes: list[DriverNotifyOutcome] = Field(default_factory=list)
    # 문자 발송 결과. 푸시(outcomes)와 경로가 달라 따로 담는다.
    sms_notices: list[str] = Field(default_factory=list)


class DispatchToday(BaseModel):
    trip_type: TripType = "inbound"
    service_date: str
    result: OptimizeResponse | None = None


class DispatchAckCreate(BaseModel):
    """기사님이 배차표를 확인했다는 신호."""

    trip_type: TripType = "inbound"
    vehicle_id: str = Field(min_length=1, max_length=100)
    vehicle_label: str = Field(min_length=1, max_length=100)
    driver_name: str | None = Field(default=None, max_length=30)


class DispatchAckRecord(DispatchAckCreate):
    service_date: str
    acknowledged_at: str


class DispatchAckList(BaseModel):
    trip_type: TripType = "inbound"
    service_date: str
    records: list[DispatchAckRecord] = Field(default_factory=list)