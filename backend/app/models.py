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
    # 자차 송영: 기사님이 센터가 아니라 자택 등에서 출발하는 경우.
    # 'center' 면 센터에서, 'custom' 이면 start_address 에서 출발한다.
    start_type: Literal["center", "custom"] = "center"
    start_address: str | None = Field(default=None, max_length=200)
    start_latitude: Latitude | None = None
    start_longitude: Longitude | None = None

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
    def pair_rules_reference_attending_passengers(self):
        attending = {
            passenger.id for passenger in self.passengers
            if passenger.attending and passenger.id
        }
        for label, rules in (("동승 불가", self.forbidden_pairs), ("필수 동승", self.required_pairs)):
            for rule in rules:
                unknown = [pid for pid in rule.passenger_ids if pid not in attending]
                if unknown:
                    raise ValueError(
                        f"{label} 규칙이 출석 명단에 없는 어르신을 가리킵니다: {', '.join(unknown)}"
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
    origin_name: str | None = None
    destination_name: str | None = None
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


class OptimizeResponse(BaseModel):
    trip_type: TripType = "inbound"
    status: str
    center: CenterResult
    total_passengers: int
    total_distance_km: float
    solve_seconds: float
    vehicles: list[VehicleResult]
    notices: list[str] = Field(default_factory=list)


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