"""Tests for Pydantic models."""

from decimal import Decimal

import pytest

from travel_agent.models.points import (
    CurrencyProgram,
    Issuer,
    PointsBalance,
    PointValuation,
    TransferPartner,
)
from travel_agent.models.preferences import (
    AccommodationTier,
    FlightTimePreference,
    PointsStrategy,
    TravelPreferences,
)
from travel_agent.models.travel import (
    FlightOption,
    FlightSegment,
    HotelOption,
    PointsCostBreakdown,
    TripPlan,
)
from travel_agent.models.session import ConversationSession, SessionPhase


class TestPointsBalance:
    def test_valid_balance(self) -> None:
        b = PointsBalance(issuer=Issuer.chase, program=CurrencyProgram.chase_ur, balance=50_000)
        assert b.balance == 50_000

    def test_zero_balance_allowed(self) -> None:
        b = PointsBalance(issuer=Issuer.bilt, program=CurrencyProgram.bilt_rewards, balance=0)
        assert b.balance == 0

    def test_negative_balance_rejected(self) -> None:
        with pytest.raises(Exception):
            PointsBalance(issuer=Issuer.amex, program=CurrencyProgram.amex_mr, balance=-1)


class TestTransferPartner:
    def test_1_to_1_ratio(self) -> None:
        tp = TransferPartner(
            source_program=CurrencyProgram.chase_ur,
            destination_program=CurrencyProgram.united_mileageplus,
            ratio_from=1,
            ratio_to=1,
            transfer_time_hours=0,
        )
        assert tp.source_points_needed(30_000) == 30_000

    def test_1_to_2_ratio(self) -> None:
        tp = TransferPartner(
            source_program=CurrencyProgram.amex_mr,
            destination_program=CurrencyProgram.hilton_honors,
            ratio_from=1,
            ratio_to=2,
            transfer_time_hours=0,
        )
        # 40k Hilton needs 20k Amex
        assert tp.source_points_needed(40_000) == 20_000

    def test_ceiling_math(self) -> None:
        # 250:200 ratio (JetBlue)
        tp = TransferPartner(
            source_program=CurrencyProgram.amex_mr,
            destination_program=CurrencyProgram.jetblue_trueblue,
            ratio_from=250,
            ratio_to=200,
            transfer_time_hours=0,
        )
        # 200 JetBlue = 250 Amex; 201 JetBlue should need 252 (ceiling)
        assert tp.source_points_needed(200) == 250
        assert tp.source_points_needed(201) == 252


class TestTravelPreferences:
    def test_not_fully_specified_by_default(self) -> None:
        prefs = TravelPreferences()
        assert prefs.is_fully_specified is False

    def test_fully_specified(self) -> None:
        prefs = TravelPreferences(
            destination_query="Hawaii",
            resolved_destination="HNL",
            origin_airport="JFK",
            departure_date="2025-04-15",
            return_date="2025-04-22",
            num_travelers=2,
        )
        assert prefs.is_fully_specified is True

    def test_missing_return_date(self) -> None:
        prefs = TravelPreferences(
            resolved_destination="HNL",
            origin_airport="JFK",
            departure_date="2025-04-15",
        )
        assert prefs.is_fully_specified is False


class TestPointsCostBreakdown:
    def test_cash_value_calculation(self) -> None:
        b = PointsCostBreakdown(
            issuer=Issuer.chase,
            program=CurrencyProgram.united_mileageplus,
            points_used=30_000,
            cpp=Decimal("1.35"),
        )
        # 30000 * 1.35 / 100 = 405.00
        assert b.cash_value_usd == Decimal("405.00")

    def test_effective_cpp_equals_cpp_for_direct_booking(self) -> None:
        b = PointsCostBreakdown(
            issuer=Issuer.chase,
            program=CurrencyProgram.chase_ur,
            points_used=10_000,
            cpp=Decimal("2.05"),
        )
        assert b.effective_cpp == Decimal("2.050")

    def test_zero_points_returns_zero_cpp(self) -> None:
        b = PointsCostBreakdown(
            issuer=Issuer.chase,
            program=CurrencyProgram.world_of_hyatt,
            points_used=0,
            cpp=Decimal("2.30"),
        )
        assert b.effective_cpp == Decimal("0")


class TestTripPlan:
    def _make_segment(self, origin: str = "JFK", dest: str = "HNL") -> FlightSegment:
        return FlightSegment(
            origin=origin,
            destination=dest,
            departure_time="2025-04-15T08:00:00",
            arrival_time="2025-04-15T14:00:00",
            airline="UA",
            flight_number="UA101",
        )

    def test_blended_cpp(self) -> None:
        seg = self._make_segment()
        flight = FlightOption(
            outbound_segments=[seg],
            inbound_segments=[self._make_segment("HNL", "JFK")],
            total_miles_required=30_000,
            program_to_book=CurrencyProgram.united_mileageplus,
            source_issuer=Issuer.chase,
        )
        hotel = HotelOption(
            hotel_name="Grand Hyatt",
            check_in="2025-04-15",
            check_out="2025-04-22",
            total_points_required=20_000,
            program_to_book=CurrencyProgram.world_of_hyatt,
            source_issuer=Issuer.chase,
        )
        breakdown = [
            PointsCostBreakdown(
                issuer=Issuer.chase,
                program=CurrencyProgram.united_mileageplus,
                points_used=30_000,
                cpp=Decimal("1.35"),
            ),
            PointsCostBreakdown(
                issuer=Issuer.chase,
                program=CurrencyProgram.world_of_hyatt,
                points_used=20_000,
                cpp=Decimal("2.30"),
            ),
        ]
        plan = TripPlan(flight=flight, hotel=hotel, points_breakdown=breakdown)
        # Total value = 30000*1.35/100 + 20000*2.30/100 = 405 + 460 = 865
        # Total points = 50000
        # Blended CPP = 865/50000 * 100 = 1.73
        assert plan.blended_cpp == Decimal("1.730")


class TestConversationSession:
    def test_initial_phase(self) -> None:
        session = ConversationSession()
        assert session.phase == SessionPhase.POINTS_INPUT

    def test_add_message(self) -> None:
        session = ConversationSession()
        session.add_message("user", "Hello")
        assert len(session.conversation_history) == 1
        assert session.conversation_history[0]["role"] == "user"

    def test_advance_phase(self) -> None:
        session = ConversationSession()
        session.advance_phase(SessionPhase.PREFERENCE_GATHERING)
        assert session.phase == SessionPhase.PREFERENCE_GATHERING
