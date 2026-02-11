"""Tests for optimizer logic: CPP calculations and transfer math."""

from decimal import Decimal

import pytest

from travel_agent.clients.transfer import TransferPartnerDB
from travel_agent.models.points import CurrencyProgram, Issuer
from travel_agent.models.travel import (
    FlightOption,
    FlightSegment,
    HotelOption,
    PointsCostBreakdown,
    TripPlan,
)


def _make_segment(
    origin: str = "JFK",
    dest: str = "HNL",
    dep: str = "2025-04-15T08:00:00",
    arr: str = "2025-04-15T14:00:00",
    airline: str = "UA",
    fn: str = "UA101",
) -> FlightSegment:
    return FlightSegment(
        origin=origin,
        destination=dest,
        departure_time=dep,
        arrival_time=arr,
        airline=airline,
        flight_number=fn,
    )


def _make_flight(program: CurrencyProgram, miles: int, issuer: Issuer) -> FlightOption:
    return FlightOption(
        outbound_segments=[_make_segment()],
        inbound_segments=[_make_segment("HNL", "JFK")],
        total_miles_required=miles,
        program_to_book=program,
        source_issuer=issuer,
    )


def _make_hotel(program: CurrencyProgram, points: int, issuer: Issuer) -> HotelOption:
    return HotelOption(
        hotel_name="Test Hotel",
        check_in="2025-04-15",
        check_out="2025-04-22",
        total_points_required=points,
        program_to_book=program,
        source_issuer=issuer,
    )


class TestCPPCalculations:
    def test_hyatt_high_cpp(self) -> None:
        b = PointsCostBreakdown(
            issuer=Issuer.chase,
            program=CurrencyProgram.world_of_hyatt,
            points_used=20_000,
            cpp=Decimal("2.30"),
        )
        assert b.cash_value_usd == Decimal("460.00")
        assert b.effective_cpp == Decimal("2.300")

    def test_delta_skymiles_lower_cpp(self) -> None:
        b = PointsCostBreakdown(
            issuer=Issuer.amex,
            program=CurrencyProgram.delta_skymiles,
            points_used=50_000,
            cpp=Decimal("1.20"),
        )
        assert b.cash_value_usd == Decimal("600.00")

    def test_blended_cpp_weighted_average(self) -> None:
        flight = _make_flight(CurrencyProgram.united_mileageplus, 30_000, Issuer.chase)
        hotel = _make_hotel(CurrencyProgram.world_of_hyatt, 20_000, Issuer.chase)
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
        # (30000*1.35 + 20000*2.30) / 50000 = (40500 + 46000) / 50000 = 86500/50000 = 1.73
        assert plan.blended_cpp == Decimal("1.730")

    def test_bilt_aa_advantage_unique(self, transfer_db: TransferPartnerDB) -> None:
        """Verify Bilt is the only issuer with an AA transfer partner."""
        partners = transfer_db.partners_for_destination(CurrencyProgram.american_airlines_aadvantage)
        source_programs = [p.source_program for p in partners]
        assert CurrencyProgram.bilt_rewards in source_programs
        # No other major issuer currency has AA
        for prog in [
            CurrencyProgram.chase_ur,
            CurrencyProgram.amex_mr,
            CurrencyProgram.citi_ty,
            CurrencyProgram.capital_one_miles,
        ]:
            assert prog not in source_programs, f"{prog} should not transfer to AA"


class TestTransferMath:
    def test_chase_to_united_1_to_1(self, transfer_db: TransferPartnerDB) -> None:
        partners = transfer_db.partners_for_destination(CurrencyProgram.united_mileageplus)
        chase_partner = next(p for p in partners if p.source_program == CurrencyProgram.chase_ur)
        assert chase_partner.source_points_needed(30_000) == 30_000

    def test_amex_to_hilton_1_to_2(self, transfer_db: TransferPartnerDB) -> None:
        partners = transfer_db.partners_for_destination(CurrencyProgram.hilton_honors)
        amex_partner = next(p for p in partners if p.source_program == CurrencyProgram.amex_mr)
        # 80k Hilton = 40k Amex
        assert amex_partner.source_points_needed(80_000) == 40_000

    def test_coverage_check(self, transfer_db: TransferPartnerDB) -> None:
        balances = {
            Issuer.chase: 25_000,  # insufficient
            Issuer.bilt: 35_000,   # sufficient
            Issuer.amex: 0,
            Issuer.citi: 0,
            Issuer.capital_one: 0,
        }
        options = transfer_db.issuers_that_can_cover(
            CurrencyProgram.united_mileageplus, 30_000, balances
        )
        chase_opt = next((o for o in options if o["issuer"] == Issuer.chase), None)
        bilt_opt = next((o for o in options if o["issuer"] == Issuer.bilt), None)
        assert chase_opt is not None
        assert chase_opt["can_cover"] is False
        assert bilt_opt is not None
        assert bilt_opt["can_cover"] is True

    def test_no_issuers_with_zero_balances(self, transfer_db: TransferPartnerDB) -> None:
        balances = {i: 0 for i in Issuer}
        options = transfer_db.issuers_that_can_cover(
            CurrencyProgram.united_mileageplus, 30_000, balances
        )
        assert all(not o["can_cover"] for o in options)
