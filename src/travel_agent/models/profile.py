"""User profile for persisting points balances and stable preferences."""

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from travel_agent.models.points import ISSUER_TO_PROGRAM, Issuer, PointsBalance
from travel_agent.models.preferences import (
    AccommodationTier,
    FlightTimePreference,
    PointsStrategy,
)

DEFAULT_PROFILE_PATH = Path.home() / ".config" / "travel-agent" / "profile.toml"


class ProfilePreferences(BaseModel):
    origin_airport: str = ""
    num_travelers: int = 1
    flight_time_preference: FlightTimePreference = FlightTimePreference.any
    accommodation_tier: AccommodationTier = AccommodationTier.midrange
    points_strategy: PointsStrategy = PointsStrategy.mixed_ok


class ProfilePoints(BaseModel):
    chase: int = 0
    amex: int = 0
    citi: int = 0
    capital_one: int = 0
    bilt: int = 0

    def to_balances(self) -> list[PointsBalance]:
        mapping = {
            "chase": Issuer.chase,
            "amex": Issuer.amex,
            "citi": Issuer.citi,
            "capital_one": Issuer.capital_one,
            "bilt": Issuer.bilt,
        }
        balances = []
        for field_name, issuer in mapping.items():
            balance = getattr(self, field_name)
            balances.append(
                PointsBalance(
                    issuer=issuer,
                    program=ISSUER_TO_PROGRAM[issuer],
                    balance=balance,
                )
            )
        return balances


class UserProfile(BaseModel):
    preferences: ProfilePreferences = Field(default_factory=ProfilePreferences)
    points: ProfilePoints = Field(default_factory=ProfilePoints)

    @property
    def has_points(self) -> bool:
        return any(
            getattr(self.points, f) > 0
            for f in ("chase", "amex", "citi", "capital_one", "bilt")
        )

    @property
    def has_preferences(self) -> bool:
        return bool(self.preferences.origin_airport)


def load_profile(path: Path = DEFAULT_PROFILE_PATH) -> UserProfile | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    data: dict[str, Any] = tomllib.loads(raw)

    prefs_data = data.get("preferences", {})
    points_data = data.get("points", {})

    prefs = ProfilePreferences(**prefs_data)
    points = ProfilePoints(**points_data)
    return UserProfile(preferences=prefs, points=points)


def save_profile(profile: UserProfile, path: Path = DEFAULT_PROFILE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    p = profile.preferences
    pt = profile.points

    content = f"""\
# Travel Points Planner — User Profile

[preferences]
origin_airport = "{p.origin_airport}"
num_travelers = {p.num_travelers}
flight_time_preference = "{p.flight_time_preference.value}"    # morning | afternoon | evening | any
accommodation_tier = "{p.accommodation_tier.value}"        # budget | midrange | upscale | luxury
points_strategy = "{p.points_strategy.value}"          # POINTS_ONLY | MIXED_OK

[points]
chase = {pt.chase}
amex = {pt.amex}
citi = {pt.citi}
capital_one = {pt.capital_one}
bilt = {pt.bilt}
"""
    path.write_text(content, encoding="utf-8")
    return path
