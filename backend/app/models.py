from typing import Annotated

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
    attending: bool = True
    pickup_start: str
    pickup_end: str
    wheelchair: bool = False

    @field_validator("pickup_start", "pickup_end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parse_hhmm(value)
        return value

    @model_validator(mode="after")
    def validate_window(self):
        if parse_hhmm(self.pickup_start) > parse_hhmm(self.pickup_end):
            raise ValueError("픽업 하한 시간은 상한 시간보다 늦을 수 없습니다.")
        return self


class VehicleInput(BaseModel):
    id: str | None = None
    vehicle_type: str = Field(min_length=1, max_length=50)
    plate_number: str = Field(min_length=1, max_length=30)
    driver_name: str | None = Field(default=None, max_length=30)
    capacity: int = Field(ge=1, le=100)


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
    latitude: float
    longitude: float
    wheelchair: bool
    requested_window: str
    estimated_pickup: str
    kakao_navi_url: str


class TripResult(BaseModel):
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
    capacity: int
    trips: list[TripResult]


class CenterResult(BaseModel):
    name: str
    address: str
    latitude: float
    longitude: float


class OptimizeResponse(BaseModel):
    status: str
    center: CenterResult
    total_passengers: int
    total_distance_km: float
    solve_seconds: float
    vehicles: list[VehicleResult]
    notices: list[str] = Field(default_factory=list)


class RideCompletionCreate(BaseModel):
    passenger_id: str = Field(min_length=1, max_length=100)
    passenger_name: str = Field(min_length=1, max_length=100)
    vehicle_id: str = Field(min_length=1, max_length=100)
    vehicle_type: str = Field(min_length=1, max_length=50)
    vehicle_plate_number: str = Field(min_length=1, max_length=30)
    trip_round: int = Field(ge=1, le=2)
    scheduled_pickup: str

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


class RideCompletionList(BaseModel):
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
        # Expo가 발급하는 토큰은 ExponentPushToken[...] 또는 ExpoPushToken[...] 형태다.
        # 형식이 아니면 발송 시점에야 실패하므로 등록 단계에서 걸러낸다.
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
