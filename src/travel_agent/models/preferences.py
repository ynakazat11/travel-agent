from enum import Enum

from pydantic import BaseModel, computed_field


class PointsStrategy(str, Enum):
    points_only = "POINTS_ONLY"
    mixed_ok = "MIXED_OK"


class FlightTimePreference(str, Enum):
    morning = "morning"      # 06:00–12:00
    afternoon = "afternoon"  # 12:00–18:00
    evening = "evening"      # 18:00–24:00
    any = "any"


class AccommodationTier(str, Enum):
    budget = "budget"         # 1–2 star / basic
    midrange = "midrange"     # 3 star
    upscale = "upscale"       # 4 star
    luxury = "luxury"         # 5 star


class TravelPreferences(BaseModel):
    destination_query: str = ""
    resolved_destination: str = ""   # IATA city/airport code
    destination_display_name: str = ""  # Human-readable place name, e.g. "Sedona, AZ"
    points_strategy: PointsStrategy = PointsStrategy.mixed_ok
    departure_date: str = ""         # ISO 8601 date YYYY-MM-DD
    return_date: str = ""            # ISO 8601 date YYYY-MM-DD
    date_flexibility_days: int = 0   # 0–14
    num_travelers: int = 1
    flight_time_preference: FlightTimePreference = FlightTimePreference.any
    accommodation_tier: AccommodationTier = AccommodationTier.midrange
    origin_airport: str = ""         # IATA airport code

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_fully_specified(self) -> bool:
        return bool(
            self.resolved_destination
            and self.departure_date
            and self.return_date
            and self.origin_airport
            and self.num_travelers >= 1
        )
