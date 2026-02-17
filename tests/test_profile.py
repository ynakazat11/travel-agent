"""Tests for user profile loading, saving, and integration."""

from pathlib import Path

import pytest

from travel_agent.models.points import ISSUER_TO_PROGRAM, Issuer
from travel_agent.models.preferences import (
    AccommodationTier,
    FlightTimePreference,
    PointsStrategy,
    TravelPreferences,
)
from travel_agent.models.profile import (
    ProfilePoints,
    ProfilePreferences,
    UserProfile,
    load_profile,
    save_profile,
)
from travel_agent.models.session import ConversationSession, SessionPhase


class TestProfilePoints:
    def test_to_balances_all_issuers(self) -> None:
        pts = ProfilePoints(chase=100_000, amex=80_000, citi=50_000, capital_one=60_000, bilt=30_000)
        balances = pts.to_balances()
        assert len(balances) == 5
        by_issuer = {b.issuer: b for b in balances}
        assert by_issuer[Issuer.chase].balance == 100_000
        assert by_issuer[Issuer.bilt].balance == 30_000
        assert by_issuer[Issuer.amex].program == ISSUER_TO_PROGRAM[Issuer.amex]

    def test_to_balances_zeros(self) -> None:
        pts = ProfilePoints()
        balances = pts.to_balances()
        assert all(b.balance == 0 for b in balances)


class TestUserProfile:
    def test_has_points_true(self) -> None:
        profile = UserProfile(points=ProfilePoints(chase=50_000))
        assert profile.has_points is True

    def test_has_points_false_when_all_zero(self) -> None:
        profile = UserProfile()
        assert profile.has_points is False

    def test_has_preferences_true(self) -> None:
        profile = UserProfile(preferences=ProfilePreferences(origin_airport="SFO"))
        assert profile.has_preferences is True

    def test_has_preferences_false_when_empty(self) -> None:
        profile = UserProfile()
        assert profile.has_preferences is False


class TestSaveLoadRoundtrip:
    def test_roundtrip(self, tmp_path: Path) -> None:
        profile = UserProfile(
            preferences=ProfilePreferences(
                origin_airport="SFO",
                num_travelers=2,
                flight_time_preference=FlightTimePreference.morning,
                accommodation_tier=AccommodationTier.upscale,
                points_strategy=PointsStrategy.points_only,
            ),
            points=ProfilePoints(
                chase=120_000, amex=85_000, citi=0, capital_one=60_000, bilt=45_000
            ),
        )
        path = tmp_path / "profile.toml"
        save_profile(profile, path)
        loaded = load_profile(path)

        assert loaded is not None
        assert loaded.preferences.origin_airport == "SFO"
        assert loaded.preferences.num_travelers == 2
        assert loaded.preferences.flight_time_preference == FlightTimePreference.morning
        assert loaded.preferences.accommodation_tier == AccommodationTier.upscale
        assert loaded.preferences.points_strategy == PointsStrategy.points_only
        assert loaded.points.chase == 120_000
        assert loaded.points.amex == 85_000
        assert loaded.points.citi == 0
        assert loaded.points.capital_one == 60_000
        assert loaded.points.bilt == 45_000

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        result = load_profile(tmp_path / "nope.toml")
        assert result is None

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "profile.toml"
        profile = UserProfile()
        save_profile(profile, path)
        assert path.exists()

    def test_malformed_toml_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.toml"
        path.write_text("this is not [valid toml =", encoding="utf-8")
        assert load_profile(path) is None

    def test_invalid_enum_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "bad_enum.toml"
        path.write_text(
            '[preferences]\npoints_strategy = "ALL_POINTS"\n',
            encoding="utf-8",
        )
        assert load_profile(path) is None

    def test_save_roundtrip_with_special_chars(self, tmp_path: Path) -> None:
        profile = UserProfile(
            preferences=ProfilePreferences(origin_airport='S"FO'),
        )
        path = tmp_path / "profile.toml"
        save_profile(profile, path)
        loaded = load_profile(path)
        assert loaded is not None
        assert loaded.preferences.origin_airport == 'S"FO'

    def test_toml_content_has_comments(self, tmp_path: Path) -> None:
        profile = UserProfile(
            preferences=ProfilePreferences(origin_airport="JFK"),
        )
        path = tmp_path / "profile.toml"
        save_profile(profile, path)
        content = path.read_text()
        assert "# morning | afternoon | evening | any" in content
        assert "# budget | midrange | upscale | luxury" in content
        assert "# POINTS_ONLY | MIXED_OK" in content


class TestProfileLoadedSession:
    def test_session_profile_loaded_default(self) -> None:
        session = ConversationSession()
        assert session.profile_loaded is False

    def test_session_profile_loaded_set(self) -> None:
        session = ConversationSession(profile_loaded=True)
        assert session.profile_loaded is True


class TestPreferenceFallbackMerge:
    def test_profile_defaults_fill_missing_fields(self) -> None:
        """When the agent omits stable fields, profile defaults should be used."""
        session = ConversationSession(profile_loaded=True)
        session.preferences = TravelPreferences(
            origin_airport="SFO",
            num_travelers=2,
            flight_time_preference=FlightTimePreference.morning,
            accommodation_tier=AccommodationTier.upscale,
            points_strategy=PointsStrategy.mixed_ok,
        )

        # Simulate agent calling mark_preferences_complete with only trip-specific fields
        tool_input = {
            "destination_query": "Tokyo",
            "resolved_destination": "TYO",
            "departure_date": "2026-04-15",
            "return_date": "2026-04-22",
            "date_flexibility_days": 3,
            # Agent omits origin_airport, num_travelers, etc. — should fall back
        }
        existing = session.preferences
        prefs = TravelPreferences(
            destination_query=tool_input.get("destination_query", ""),
            resolved_destination=tool_input.get("resolved_destination", ""),
            origin_airport=tool_input.get("origin_airport", "") or existing.origin_airport,
            departure_date=tool_input.get("departure_date", ""),
            return_date=tool_input.get("return_date", ""),
            date_flexibility_days=tool_input.get("date_flexibility_days", 0),
            num_travelers=tool_input.get("num_travelers", 0) or existing.num_travelers,
            flight_time_preference=FlightTimePreference(
                tool_input.get("flight_time_preference", "") or existing.flight_time_preference.value
            ),
            accommodation_tier=AccommodationTier(
                tool_input.get("accommodation_tier", "") or existing.accommodation_tier.value
            ),
            points_strategy=PointsStrategy(
                tool_input.get("points_strategy", "") or existing.points_strategy.value
            ),
        )

        assert prefs.origin_airport == "SFO"
        assert prefs.num_travelers == 2
        assert prefs.flight_time_preference == FlightTimePreference.morning
        assert prefs.accommodation_tier == AccommodationTier.upscale
        assert prefs.resolved_destination == "TYO"
        assert prefs.departure_date == "2026-04-15"


class TestSystemPromptConditional:
    def test_profile_loaded_prompt_mentions_defaults(self) -> None:
        from travel_agent.agent.prompts import _phase_instructions

        session = ConversationSession(profile_loaded=True)
        session.preferences = TravelPreferences(
            origin_airport="SFO",
            num_travelers=2,
            flight_time_preference=FlightTimePreference.morning,
            accommodation_tier=AccommodationTier.upscale,
            points_strategy=PointsStrategy.mixed_ok,
        )
        session.advance_phase(SessionPhase.PREFERENCE_GATHERING)
        text = _phase_instructions(session)
        assert "SFO" in text
        assert "Do NOT re-ask" in text

    def test_no_profile_prompt_asks_everything(self) -> None:
        from travel_agent.agent.prompts import _phase_instructions

        session = ConversationSession()
        session.advance_phase(SessionPhase.PREFERENCE_GATHERING)
        text = _phase_instructions(session)
        assert "destination" in text
        assert "Do NOT re-ask" not in text
