"""Tests for ToolExecutor."""

import json

import pytest

from travel_agent.agent.tools import ToolExecutor
from travel_agent.clients.amadeus import AmadeusClient
from travel_agent.clients.transfer import TransferPartnerDB
from travel_agent.models.points import Issuer, PointsBalance, ISSUER_TO_PROGRAM


@pytest.fixture
def executor(mock_amadeus: AmadeusClient, transfer_db: TransferPartnerDB, sample_balances: list[PointsBalance]) -> ToolExecutor:
    return ToolExecutor(amadeus=mock_amadeus, transfer_db=transfer_db, balances=sample_balances)


class TestToolExecutor:
    def test_resolve_hawaii(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("resolve_destination", {"query": "somewhere warm in Hawaii"}))
        assert isinstance(result, list)
        assert result[0]["iata"] == "HNL"

    def test_resolve_unknown_returns_fallback(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("resolve_destination", {"query": "Zorbonia Island"}))
        assert isinstance(result, list)
        assert result[0]["confidence"] == 0.0

    def test_search_flights_returns_list(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_flights", {
            "origin": "JFK",
            "destination": "HNL",
            "departure_date": "2025-04-15",
            "return_date": "2025-04-22",
            "num_travelers": 2,
        }))
        assert isinstance(result, list)
        assert len(result) > 0
        assert "total_miles_required" in result[0]

    def test_search_hotels_returns_list(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("search_hotels", {
            "city_code": "HNL",
            "check_in": "2025-04-15",
            "check_out": "2025-04-22",
        }))
        assert isinstance(result, list)
        assert len(result) > 0
        assert "hotel_name" in result[0]

    def test_lookup_transfer_options_united(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("lookup_transfer_options", {
            "destination_program": "united_mileageplus",
            "points_needed": 30_000,
        }))
        assert isinstance(result, list)
        # Chase and Bilt both transfer to United
        issuers = {r["issuer"] for r in result}
        assert "chase" in issuers
        assert "bilt" in issuers

    def test_calculate_trip_cost_full_plan(self, executor: ToolExecutor) -> None:
        # Populate last_flights and last_hotels first
        executor.execute("search_flights", {
            "origin": "JFK",
            "destination": "HNL",
            "departure_date": "2025-04-15",
            "return_date": "2025-04-22",
        })
        executor.execute("search_hotels", {
            "city_code": "HNL",
            "check_in": "2025-04-15",
            "check_out": "2025-04-22",
        })

        result = json.loads(executor.execute("calculate_trip_cost", {
            "flight_index": 0,
            "hotel_index": 0,
            "flight_issuer": "chase",
            "hotel_issuer": "chase",
            "summary_label": "Chase UR Test Plan",
        }))
        assert "flight" in result
        assert "hotel" in result
        assert "points_breakdown" in result
        assert "blended_cpp" in result
        assert float(result["blended_cpp"]) > 0

    def test_calculate_trip_cost_out_of_range(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("calculate_trip_cost", {
            "flight_index": 999,
            "hotel_index": 0,
            "flight_issuer": "chase",
            "hotel_issuer": "chase",
            "summary_label": "Bad Plan",
        }))
        assert "error" in result

    def test_unknown_tool_returns_error(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("nonexistent_tool", {}))
        assert "error" in result

    def test_mark_preferences_complete(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("mark_preferences_complete", {
            "destination_query": "Hawaii",
            "resolved_destination": "HNL",
            "origin_airport": "JFK",
            "departure_date": "2025-04-15",
            "return_date": "2025-04-22",
        }))
        assert result["status"] == "preferences_confirmed"
