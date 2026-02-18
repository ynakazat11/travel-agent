"""Tests for the three improvements: location bias fix, free-text feedback, confirmation step."""

import inspect
import json

import pytest

from travel_agent.agent.prompts import _sanitize_prompt_str, build_system_prompt
from travel_agent.agent.tools import TOOL_SCHEMAS, ToolExecutor
from travel_agent.clients.amadeus import AmadeusClient
from travel_agent.clients.transfer import TransferPartnerDB
from travel_agent.models.points import ISSUER_TO_PROGRAM, Issuer, PointsBalance
from travel_agent.models.preferences import (
    AccommodationTier,
    FlightTimePreference,
    PointsStrategy,
    TravelPreferences,
)
from travel_agent.models.session import ConversationSession, SessionPhase


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def session(sample_balances: list[PointsBalance]) -> ConversationSession:
    return ConversationSession(points_balances=sample_balances)


@pytest.fixture
def executor(mock_amadeus: AmadeusClient, transfer_db: TransferPartnerDB, sample_balances: list[PointsBalance]) -> ToolExecutor:
    return ToolExecutor(amadeus=mock_amadeus, transfer_db=transfer_db, balances=sample_balances)


# ─── Change 1: SEARCHING prompt differs based on points_strategy ─────────────

class TestSearchingPromptStrategy:
    def test_points_only_mentions_high_cpp(self, session: ConversationSession) -> None:
        session.advance_phase(SessionPhase.SEARCHING)
        session.preferences = TravelPreferences(
            destination_query="Sedona",
            resolved_destination="PHX",
            destination_display_name="Sedona, AZ",
            origin_airport="JFK",
            departure_date="2025-06-01",
            return_date="2025-06-08",
            points_strategy=PointsStrategy.points_only,
        )
        prompt = build_system_prompt(session)
        assert "Prefer high-CPP" in prompt
        assert "Location match is more important" not in prompt

    def test_mixed_ok_prioritizes_location(self, session: ConversationSession) -> None:
        session.advance_phase(SessionPhase.SEARCHING)
        session.preferences = TravelPreferences(
            destination_query="Sedona",
            resolved_destination="PHX",
            destination_display_name="Sedona, AZ",
            origin_airport="JFK",
            departure_date="2025-06-01",
            return_date="2025-06-08",
            points_strategy=PointsStrategy.mixed_ok,
        )
        prompt = build_system_prompt(session)
        assert "Location match is more important" in prompt
        assert "Sedona, AZ" in prompt
        assert "Prefer high-CPP" not in prompt

    def test_destination_display_name_shown_in_prompt(self, session: ConversationSession) -> None:
        session.advance_phase(SessionPhase.SEARCHING)
        session.preferences = TravelPreferences(
            destination_query="Sedona trip",
            resolved_destination="PHX",
            destination_display_name="Sedona, AZ",
            origin_airport="SFO",
            departure_date="2025-07-01",
            return_date="2025-07-05",
        )
        prompt = build_system_prompt(session)
        assert "Sedona, AZ" in prompt
        assert "IATA: PHX" in prompt


# ─── Change 1: search_hotels accepts location_query ─────────────────────────

class TestSearchHotelsLocationQuery:
    def test_schema_has_location_query(self) -> None:
        hotel_schema = next(s for s in TOOL_SCHEMAS if s["name"] == "search_hotels")
        props = hotel_schema["input_schema"]["properties"]
        assert "location_query" in props

    def test_location_query_surfaces_in_results(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_hotels", {
            "city_code": "HNL",
            "check_in": "2025-04-15",
            "check_out": "2025-04-22",
            "location_query": "Sedona, AZ",
        }))
        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0]["location_query"] == "Sedona, AZ"

    def test_no_location_query_omits_field(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_hotels", {
            "city_code": "HNL",
            "check_in": "2025-04-15",
            "check_out": "2025-04-22",
        }))
        assert isinstance(result, list)
        assert len(result) > 0
        assert "location_query" not in result[0]


# ─── Change 1: mark_preferences_complete has destination_display_name ────────

class TestMarkPreferencesSchema:
    def test_schema_has_destination_display_name(self) -> None:
        schema = next(s for s in TOOL_SCHEMAS if s["name"] == "mark_preferences_complete")
        props = schema["input_schema"]["properties"]
        assert "destination_display_name" in props


# ─── Change 1: destination_display_name on TravelPreferences ────────────────

class TestTravelPreferencesDisplayName:
    def test_default_empty(self) -> None:
        prefs = TravelPreferences()
        assert prefs.destination_display_name == ""

    def test_set_value(self) -> None:
        prefs = TravelPreferences(destination_display_name="Sedona, AZ")
        assert prefs.destination_display_name == "Sedona, AZ"


# ─── Change 1: _sanitize_prompt_str ──────────────────────────────────────────

class TestSanitizePromptStr:
    def test_strips_newlines(self) -> None:
        assert _sanitize_prompt_str("line1\nline2\rline3") == "line1 line2 line3"

    def test_truncates_long_input(self) -> None:
        long_str = "a" * 200
        assert len(_sanitize_prompt_str(long_str)) == 100

    def test_leaves_normal_text_unchanged(self) -> None:
        assert _sanitize_prompt_str("Sedona, AZ") == "Sedona, AZ"


# ─── Change 2: fine-tune menu includes option 6 ─────────────────────────────

class TestFineTuneMenuOption6:
    def test_prompt_fine_tune_menu_accepts_choice_6(self) -> None:
        """Verify the menu source includes '6' as a valid choice in Prompt.ask."""
        from travel_agent.display.prompts import prompt_fine_tune_menu
        source = inspect.getsource(prompt_fine_tune_menu)
        assert '"6"' in source
        assert "Give feedback in your own words" in source


# ─── Change 3: CONFIRM_PREFERENCES phase exists and transitions ─────────────

class TestConfirmPreferencesPhase:
    def test_phase_exists(self) -> None:
        assert hasattr(SessionPhase, "CONFIRM_PREFERENCES")
        assert SessionPhase.CONFIRM_PREFERENCES.value == "CONFIRM_PREFERENCES"

    def test_mark_preferences_transitions_to_confirm(self, session: ConversationSession) -> None:
        """Verify that _handle_phase_transition sends to CONFIRM_PREFERENCES, not SEARCHING."""
        from travel_agent.agent.loop import _handle_phase_transition

        session.advance_phase(SessionPhase.PREFERENCE_GATHERING)
        tool_input = {
            "destination_query": "Sedona",
            "resolved_destination": "PHX",
            "destination_display_name": "Sedona, AZ",
            "origin_airport": "JFK",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
        }
        _handle_phase_transition(session, "mark_preferences_complete", tool_input, {}, None)  # type: ignore[arg-type]
        assert session.phase == SessionPhase.CONFIRM_PREFERENCES

    def test_confirm_to_searching_transition(self, session: ConversationSession) -> None:
        """Verify that advancing from CONFIRM_PREFERENCES to SEARCHING works."""
        session.advance_phase(SessionPhase.CONFIRM_PREFERENCES)
        session.advance_phase(SessionPhase.SEARCHING)
        assert session.phase == SessionPhase.SEARCHING

    def test_confirm_back_to_gathering_transition(self, session: ConversationSession) -> None:
        """Verify the 'n' path: CONFIRM_PREFERENCES → PREFERENCE_GATHERING."""
        session.advance_phase(SessionPhase.CONFIRM_PREFERENCES)
        session.advance_phase(SessionPhase.PREFERENCE_GATHERING)
        assert session.phase == SessionPhase.PREFERENCE_GATHERING

    def test_destination_display_name_captured(self, session: ConversationSession) -> None:
        from travel_agent.agent.loop import _handle_phase_transition

        session.advance_phase(SessionPhase.PREFERENCE_GATHERING)
        tool_input = {
            "destination_query": "Sedona trip",
            "resolved_destination": "PHX",
            "destination_display_name": "Sedona, AZ",
            "origin_airport": "JFK",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
        }
        _handle_phase_transition(session, "mark_preferences_complete", tool_input, {}, None)  # type: ignore[arg-type]
        assert session.preferences.destination_display_name == "Sedona, AZ"

    def test_display_name_falls_back_to_query(self, session: ConversationSession) -> None:
        from travel_agent.agent.loop import _handle_phase_transition

        session.advance_phase(SessionPhase.PREFERENCE_GATHERING)
        tool_input = {
            "destination_query": "Sedona trip",
            "resolved_destination": "PHX",
            "origin_airport": "JFK",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
        }
        _handle_phase_transition(session, "mark_preferences_complete", tool_input, {}, None)  # type: ignore[arg-type]
        assert session.preferences.destination_display_name == "Sedona trip"


# ─── Change 3: prompt_confirm_preferences exists ────────────────────────────

class TestPromptConfirmPreferences:
    def test_function_exists(self) -> None:
        from travel_agent.display.prompts import prompt_confirm_preferences
        assert callable(prompt_confirm_preferences)
