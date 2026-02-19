"""Tests for improvements: location bias fix, free-text feedback, confirmation step, geocode search."""

import inspect
import json

import pytest

from travel_agent.agent.prompts import _sanitize_prompt_str, build_system_prompt
from travel_agent.agent.tools import TOOL_SCHEMAS, ToolExecutor
from travel_agent.clients.amadeus import AmadeusClient, _geocode_label
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
        assert "latitude" in prompt
        assert "longitude" in prompt
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


# ─── Geocode hotel search ─────────────────────────────────────────────────

class TestGeocodeHotelSearch:
    def test_schema_has_latitude_longitude(self) -> None:
        hotel_schema = next(s for s in TOOL_SCHEMAS if s["name"] == "search_hotels")
        props = hotel_schema["input_schema"]["properties"]
        assert "latitude" in props
        assert "longitude" in props

    def test_city_code_no_longer_required(self) -> None:
        hotel_schema = next(s for s in TOOL_SCHEMAS if s["name"] == "search_hotels")
        required = hotel_schema["input_schema"]["required"]
        assert "city_code" not in required
        assert "check_in" in required
        assert "check_out" in required

    def test_geocode_search_returns_location_named_hotels(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_hotels", {
            "latitude": 34.87,
            "longitude": -111.76,
            "check_in": "2025-06-01",
            "check_out": "2025-06-08",
        }))
        assert isinstance(result, list)
        assert len(result) == 3
        names = [h["hotel_name"] for h in result]
        assert all("Sedona" in name for name in names)

    def test_geocode_search_unknown_coords_uses_fallback(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_hotels", {
            "latitude": 10.0,
            "longitude": 20.0,
            "check_in": "2025-06-01",
            "check_out": "2025-06-08",
        }))
        assert isinstance(result, list)
        assert len(result) == 3
        names = [h["hotel_name"] for h in result]
        assert all("(10.0, 20.0)" in name for name in names)

    def test_city_code_search_still_works(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_hotels", {
            "city_code": "HNL",
            "check_in": "2025-04-15",
            "check_out": "2025-04-22",
        }))
        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0]["hotel_name"] == "Grand Hyatt"

    def test_no_city_code_or_coords_returns_error(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_hotels", {
            "check_in": "2025-06-01",
            "check_out": "2025-06-08",
        }))
        assert isinstance(result, list)
        assert result[0].get("error")

    def test_geocode_with_location_query(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_hotels", {
            "latitude": 34.87,
            "longitude": -111.76,
            "check_in": "2025-06-01",
            "check_out": "2025-06-08",
            "location_query": "Sedona, AZ",
        }))
        assert result[0]["location_query"] == "Sedona, AZ"
        assert "Sedona" in result[0]["hotel_name"]


class TestGeocodeLabel:
    def test_sedona_coords(self) -> None:
        assert _geocode_label(34.87, -111.76) == "Sedona"

    def test_napa_coords(self) -> None:
        assert _geocode_label(38.30, -122.30) == "Napa Valley"

    def test_unknown_coords_fallback(self) -> None:
        label = _geocode_label(0.0, 0.0)
        assert label == "(0.0, 0.0)"


class TestMixedOkPromptMentionsGeocode:
    def test_prompt_mentions_latitude_longitude(self, session: ConversationSession) -> None:
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
        assert "latitude=34.87" in prompt
        assert "longitude=-111.76" in prompt
        assert "city_code='PHX'" in prompt


# ─── Post-search interaction ──────────────────────────────────────────────

class TestPromptPostSearch:
    def test_function_exists(self) -> None:
        from travel_agent.display.prompts import prompt_post_search
        assert callable(prompt_post_search)

    def test_function_is_importable_from_main(self) -> None:
        """Verify main.py imports prompt_post_search."""
        import travel_agent.main as main_mod
        assert hasattr(main_mod, "prompt_post_search")


# ─── Agent suggestions safety net ─────────────────────────────────────────

class TestAgentSuggestionsSafetyNet:
    def test_prompt_agent_suggestions_exists(self) -> None:
        from travel_agent.display.prompts import prompt_agent_suggestions
        assert callable(prompt_agent_suggestions)

    def test_last_assistant_has_questions_true(self) -> None:
        from travel_agent.main import _last_assistant_has_questions
        session = ConversationSession()
        session.add_message("assistant", [{"type": "text", "text": "Would you like option 1 or 2?"}])
        assert _last_assistant_has_questions(session) is True

    def test_last_assistant_has_questions_false(self) -> None:
        from travel_agent.main import _last_assistant_has_questions
        session = ConversationSession()
        session.add_message("assistant", [{"type": "text", "text": "Great, confirming your preferences now."}])
        assert _last_assistant_has_questions(session) is False

    def test_last_assistant_has_questions_no_messages(self) -> None:
        from travel_agent.main import _last_assistant_has_questions
        session = ConversationSession()
        assert _last_assistant_has_questions(session) is False

    def test_last_assistant_has_questions_tool_only(self) -> None:
        from travel_agent.main import _last_assistant_has_questions
        session = ConversationSession()
        session.add_message("assistant", [{"type": "tool_use", "id": "x", "name": "mark_preferences_complete", "input": {}}])
        assert _last_assistant_has_questions(session) is False

    def test_prompt_no_questions_in_mark_preferences_prompt(self) -> None:
        """Verify the system prompt tells Claude not to ask questions with mark_preferences_complete."""
        prompt = build_system_prompt(ConversationSession())
        assert "do not include questions" in prompt.lower()


# ─── Nonstop flight preference ─────────────────────────────────────────────

class TestNonstopPreference:
    def test_travel_preferences_has_nonstop_default_false(self) -> None:
        prefs = TravelPreferences()
        assert prefs.nonstop_preferred is False

    def test_travel_preferences_nonstop_set_true(self) -> None:
        prefs = TravelPreferences(nonstop_preferred=True)
        assert prefs.nonstop_preferred is True

    def test_mark_preferences_schema_has_nonstop(self) -> None:
        schema = next(s for s in TOOL_SCHEMAS if s["name"] == "mark_preferences_complete")
        props = schema["input_schema"]["properties"]
        assert "nonstop_preferred" in props

    def test_search_flights_schema_has_nonstop(self) -> None:
        schema = next(s for s in TOOL_SCHEMAS if s["name"] == "search_flights")
        props = schema["input_schema"]["properties"]
        assert "nonstop" in props

    def test_get_alternative_flights_schema_has_nonstop(self) -> None:
        schema = next(s for s in TOOL_SCHEMAS if s["name"] == "get_alternative_flights")
        props = schema["input_schema"]["properties"]
        assert "nonstop" in props


class TestNonstopFlightSearch:
    def test_nonstop_true_returns_only_nonstop(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_flights", {
            "origin": "SEA",
            "destination": "PHX",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
            "nonstop": True,
        }))
        assert isinstance(result, list)
        assert len(result) == 3  # 3 nonstop options, no connecting
        for flight in result:
            assert len(flight["outbound"]) == 1, "Nonstop should have single outbound segment"
            assert len(flight["inbound"]) == 1, "Nonstop should have single inbound segment"

    def test_nonstop_false_includes_connecting(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_flights", {
            "origin": "SEA",
            "destination": "PHX",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
            "nonstop": False,
        }))
        assert isinstance(result, list)
        assert len(result) == 4  # 3 nonstop + 1 connecting
        connecting = [f for f in result if len(f["outbound"]) > 1]
        assert len(connecting) == 1
        assert connecting[0]["outbound"][0]["destination"] == "DEN"

    def test_default_nonstop_false_includes_connecting(self, executor: ToolExecutor) -> None:
        """Default search (no nonstop param) should include connecting flights."""
        result = json.loads(executor.execute("search_flights", {
            "origin": "SEA",
            "destination": "PHX",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
        }))
        assert len(result) == 4


class TestNonstopSearchingPrompt:
    def test_nonstop_preferred_shows_guidance(self, session: ConversationSession) -> None:
        session.advance_phase(SessionPhase.SEARCHING)
        session.preferences = TravelPreferences(
            destination_query="Phoenix",
            resolved_destination="PHX",
            origin_airport="SEA",
            departure_date="2025-06-01",
            return_date="2025-06-08",
            nonstop_preferred=True,
        )
        prompt = build_system_prompt(session)
        assert "nonstop=true" in prompt
        assert "connecting flights" in prompt.lower()

    def test_no_nonstop_preferred_no_guidance(self, session: ConversationSession) -> None:
        session.advance_phase(SessionPhase.SEARCHING)
        session.preferences = TravelPreferences(
            destination_query="Phoenix",
            resolved_destination="PHX",
            origin_airport="SEA",
            departure_date="2025-06-01",
            return_date="2025-06-08",
            nonstop_preferred=False,
        )
        prompt = build_system_prompt(session)
        assert "nonstop=true" not in prompt


class TestNonstopPhaseTransition:
    def test_nonstop_captured_in_preferences(self, session: ConversationSession) -> None:
        from travel_agent.agent.loop import _handle_phase_transition

        session.advance_phase(SessionPhase.PREFERENCE_GATHERING)
        tool_input = {
            "destination_query": "Phoenix",
            "resolved_destination": "PHX",
            "origin_airport": "SEA",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
            "nonstop_preferred": True,
        }
        _handle_phase_transition(session, "mark_preferences_complete", tool_input, {}, None)  # type: ignore[arg-type]
        assert session.preferences.nonstop_preferred is True

    def test_nonstop_defaults_false_when_omitted(self, session: ConversationSession) -> None:
        from travel_agent.agent.loop import _handle_phase_transition

        session.advance_phase(SessionPhase.PREFERENCE_GATHERING)
        tool_input = {
            "destination_query": "Phoenix",
            "resolved_destination": "PHX",
            "origin_airport": "SEA",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
        }
        _handle_phase_transition(session, "mark_preferences_complete", tool_input, {}, None)  # type: ignore[arg-type]
        assert session.preferences.nonstop_preferred is False


# ─── Web search hotel fallback ──────────────────────────────────────────────

class TestWebSearchHotels:
    def test_schema_exists(self) -> None:
        names = [s["name"] for s in TOOL_SCHEMAS]
        assert "web_search_hotels" in names

    def test_schema_properties(self) -> None:
        schema = next(s for s in TOOL_SCHEMAS if s["name"] == "web_search_hotels")
        props = schema["input_schema"]["properties"]
        assert "destination" in props
        assert "check_in" in props
        assert "check_out" in props
        assert "tier" in props

    def test_sedona_luxury_returns_known_hotels(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("web_search_hotels", {
            "destination": "Sedona, AZ",
            "check_in": "2025-06-01",
            "check_out": "2025-06-08",
            "tier": "luxury",
        }))
        assert result["source"] == "web_search"
        names = [r["name"] for r in result["results"]]
        assert "Enchantment Resort" in names
        assert "L'Auberge de Sedona" in names
        assert "Ambiente, A Landscape Hotel" in names

    def test_napa_luxury_returns_known_hotels(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("web_search_hotels", {
            "destination": "Napa Valley, CA",
            "check_in": "2025-06-01",
            "check_out": "2025-06-08",
            "tier": "luxury",
        }))
        assert result["source"] == "web_search"
        names = [r["name"] for r in result["results"]]
        assert "Meadowood Napa Valley" in names

    def test_unknown_destination_returns_generic(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("web_search_hotels", {
            "destination": "Timbuktu",
            "check_in": "2025-06-01",
            "check_out": "2025-06-08",
            "tier": "luxury",
        }))
        assert result["source"] == "web_search"
        assert len(result["results"]) >= 1
        assert "Timbuktu" in result["results"][0]["name"]

    def test_results_include_dates(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("web_search_hotels", {
            "destination": "Sedona, AZ",
            "check_in": "2025-06-01",
            "check_out": "2025-06-08",
            "tier": "luxury",
        }))
        for r in result["results"]:
            assert r["check_in"] == "2025-06-01"
            assert r["check_out"] == "2025-06-08"

    def test_cash_booking_note(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("web_search_hotels", {
            "destination": "Sedona, AZ",
            "check_in": "2025-06-01",
            "check_out": "2025-06-08",
            "tier": "luxury",
        }))
        assert "cash-booking" in result["note"].lower()


class TestSearchingPromptHotelFallback:
    def test_prompt_mentions_web_search_hotels(self, session: ConversationSession) -> None:
        session.advance_phase(SessionPhase.SEARCHING)
        session.preferences = TravelPreferences(
            destination_query="Sedona",
            resolved_destination="PHX",
            destination_display_name="Sedona, AZ",
            origin_airport="SEA",
            departure_date="2025-06-01",
            return_date="2025-06-08",
            accommodation_tier=AccommodationTier.luxury,
        )
        prompt = build_system_prompt(session)
        assert "web_search_hotels" in prompt
        assert "luxury" in prompt

    def test_tool_policy_mentions_web_search(self) -> None:
        prompt = build_system_prompt(ConversationSession())
        assert "web_search_hotels" in prompt
