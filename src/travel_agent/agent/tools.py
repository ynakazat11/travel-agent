"""Tool schemas and executor for the travel agent."""

import json
from decimal import Decimal
from typing import Any

from travel_agent.clients.amadeus import AmadeusClient
from travel_agent.clients.transfer import TransferPartnerDB
from travel_agent.models.points import CurrencyProgram, Issuer, PointsBalance
from travel_agent.models.travel import FlightOption, HotelOption, PointsCostBreakdown, TripPlan


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "resolve_destination",
        "description": (
            "Convert a vague destination description into ranked IATA airport/city codes. "
            "Returns up to 3 candidates with confidence scores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language destination, e.g. 'somewhere warm in Hawaii'"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_flights",
        "description": "Search for award flight options via Amadeus. Returns FlightOption list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "IATA airport code, e.g. 'JFK'"},
                "destination": {"type": "string", "description": "IATA airport code, e.g. 'HNL'"},
                "departure_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "return_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "num_travelers": {"type": "integer", "description": "Number of adult travelers", "default": 1},
            },
            "required": ["origin", "destination", "departure_date", "return_date"],
        },
    },
    {
        "name": "search_hotels",
        "description": "Search for hotel options via Amadeus. Returns HotelOption list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city_code": {"type": "string", "description": "IATA city code, e.g. 'HNL'"},
                "check_in": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "check_out": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "num_travelers": {"type": "integer", "description": "Number of travelers", "default": 1},
            },
            "required": ["city_code", "check_in", "check_out"],
        },
    },
    {
        "name": "lookup_transfer_options",
        "description": (
            "Find which issuers can transfer to a given loyalty program and how many source points are needed. "
            "Highlights Bilt→AA as a unique differentiator."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destination_program": {
                    "type": "string",
                    "description": "CurrencyProgram value, e.g. 'united_mileageplus'",
                },
                "points_needed": {
                    "type": "integer",
                    "description": "Award miles/points required in the destination program",
                },
            },
            "required": ["destination_program", "points_needed"],
        },
    },
    {
        "name": "calculate_trip_cost",
        "description": "Assemble a FlightOption + HotelOption into a complete TripPlan with CPP breakdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "flight_index": {"type": "integer", "description": "Index into last search_flights result"},
                "hotel_index": {"type": "integer", "description": "Index into last search_hotels result"},
                "flight_issuer": {"type": "string", "description": "Issuer enum value to pay for flight"},
                "hotel_issuer": {"type": "string", "description": "Issuer enum value to pay for hotel"},
                "summary_label": {"type": "string", "description": "Short label, e.g. 'Chase UR + Hyatt'"},
            },
            "required": ["flight_index", "hotel_index", "flight_issuer", "hotel_issuer", "summary_label"],
        },
    },
    {
        "name": "get_alternative_flights",
        "description": "Get alternative flights for fine-tuning. Filters by time window or airline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "destination": {"type": "string"},
                "departure_date": {"type": "string"},
                "return_date": {"type": "string"},
                "preferred_time": {
                    "type": "string",
                    "enum": ["morning", "afternoon", "evening", "any"],
                    "description": "Filter by departure time window",
                },
                "preferred_airline": {"type": "string", "description": "IATA airline code or empty for any"},
                "num_travelers": {"type": "integer", "default": 1},
            },
            "required": ["origin", "destination", "departure_date", "return_date"],
        },
    },
    {
        "name": "get_alternative_hotels",
        "description": "Get alternative hotels for fine-tuning. Filters by tier or property name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city_code": {"type": "string"},
                "check_in": {"type": "string"},
                "check_out": {"type": "string"},
                "tier": {
                    "type": "string",
                    "enum": ["budget", "midrange", "upscale", "luxury"],
                    "description": "Accommodation tier filter",
                },
                "chain_preference": {"type": "string", "description": "Hotel chain preference or empty"},
                "num_travelers": {"type": "integer", "default": 1},
            },
            "required": ["city_code", "check_in", "check_out"],
        },
    },
    {
        "name": "mark_preferences_complete",
        "description": (
            "Signal that all travel preferences have been gathered. "
            "Include the fully structured preferences. This triggers the search phase."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destination_query": {"type": "string"},
                "resolved_destination": {"type": "string", "description": "IATA city code"},
                "origin_airport": {"type": "string", "description": "IATA airport code"},
                "departure_date": {"type": "string"},
                "return_date": {"type": "string"},
                "date_flexibility_days": {"type": "integer", "default": 0},
                "num_travelers": {"type": "integer", "default": 1},
                "flight_time_preference": {
                    "type": "string",
                    "enum": ["morning", "afternoon", "evening", "any"],
                    "default": "any",
                },
                "accommodation_tier": {
                    "type": "string",
                    "enum": ["budget", "midrange", "upscale", "luxury"],
                    "default": "midrange",
                },
                "points_strategy": {
                    "type": "string",
                    "enum": ["POINTS_ONLY", "MIXED_OK"],
                    "default": "MIXED_OK",
                },
            },
            "required": [
                "destination_query",
                "resolved_destination",
                "origin_airport",
                "departure_date",
                "return_date",
            ],
        },
    },
]


class ToolExecutor:
    def __init__(
        self,
        amadeus: AmadeusClient,
        transfer_db: TransferPartnerDB,
        balances: list[PointsBalance],
    ) -> None:
        self._amadeus = amadeus
        self._transfer_db = transfer_db
        self._balances = balances
        # State shared between tool calls within a session
        self._last_flights: list[FlightOption] = []
        self._last_hotels: list[HotelOption] = []

    @property
    def balance_map(self) -> dict[Issuer, int]:
        return {b.issuer: b.balance for b in self._balances}

    def execute(self, name: str, inputs: dict[str, Any]) -> str:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            result = handler(**inputs)
            return json.dumps(result, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _tool_resolve_destination(self, query: str) -> list[dict[str, Any]]:
        # Heuristic mapping for common destinations
        known: dict[str, list[dict[str, Any]]] = {
            "hawaii": [
                {"iata": "HNL", "name": "Honolulu, Hawaii", "confidence": 0.9},
                {"iata": "OGG", "name": "Maui (Kahului), Hawaii", "confidence": 0.7},
                {"iata": "KOA", "name": "Kona, Big Island, Hawaii", "confidence": 0.6},
            ],
            "maui": [{"iata": "OGG", "name": "Maui (Kahului), Hawaii", "confidence": 0.95}],
            "paris": [{"iata": "CDG", "name": "Paris Charles de Gaulle", "confidence": 0.95}],
            "london": [{"iata": "LHR", "name": "London Heathrow", "confidence": 0.9}],
            "tokyo": [{"iata": "NRT", "name": "Tokyo Narita", "confidence": 0.85}],
            "cancun": [{"iata": "CUN", "name": "Cancun International", "confidence": 0.95}],
            "maldives": [{"iata": "MLE", "name": "Male, Maldives", "confidence": 0.95}],
            "bali": [{"iata": "DPS", "name": "Bali (Denpasar)", "confidence": 0.95}],
        }
        q = query.lower()
        for key, candidates in known.items():
            if key in q:
                return candidates
        # Fallback: return empty with a note
        return [{"iata": "", "name": query, "confidence": 0.0, "note": "Could not resolve — please specify IATA code"}]

    def _tool_search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str,
        num_travelers: int = 1,
    ) -> list[dict[str, Any]]:
        flights = self._amadeus.search_flights(
            origin, destination, departure_date, return_date, num_travelers
        )
        self._last_flights = flights
        return [_flight_to_dict(i, f) for i, f in enumerate(flights)]

    def _tool_search_hotels(
        self,
        city_code: str,
        check_in: str,
        check_out: str,
        num_travelers: int = 1,
    ) -> list[dict[str, Any]]:
        hotels = self._amadeus.search_hotels(city_code, check_in, check_out, num_travelers)
        self._last_hotels = hotels
        return [_hotel_to_dict(i, h) for i, h in enumerate(hotels)]

    def _tool_lookup_transfer_options(
        self,
        destination_program: str,
        points_needed: int,
    ) -> list[dict[str, Any]]:
        prog = CurrencyProgram(destination_program)
        options = self._transfer_db.issuers_that_can_cover(prog, points_needed, self.balance_map)
        return options

    def _tool_calculate_trip_cost(
        self,
        flight_index: int,
        hotel_index: int,
        flight_issuer: str,
        hotel_issuer: str,
        summary_label: str,
    ) -> dict[str, Any]:
        if flight_index >= len(self._last_flights):
            raise ValueError(f"flight_index {flight_index} out of range")
        if hotel_index >= len(self._last_hotels):
            raise ValueError(f"hotel_index {hotel_index} out of range")

        flight = self._last_flights[flight_index]
        hotel = self._last_hotels[hotel_index]
        f_issuer = Issuer(flight_issuer)
        h_issuer = Issuer(hotel_issuer)

        flight = flight.model_copy(update={"source_issuer": f_issuer})
        hotel = hotel.model_copy(update={"source_issuer": h_issuer})

        breakdown: list[PointsCostBreakdown] = []
        for src_issuer, program, points in [
            (f_issuer, flight.program_to_book, flight.total_miles_required),
            (h_issuer, hotel.program_to_book, hotel.total_points_required),
        ]:
            valuation = self._transfer_db.get_valuation(program)
            cpp = valuation.cpp if valuation else Decimal("1.0")
            breakdown.append(
                PointsCostBreakdown(
                    issuer=src_issuer,
                    program=program,
                    points_used=points,
                    cpp=cpp,
                )
            )

        plan = TripPlan(
            flight=flight,
            hotel=hotel,
            points_breakdown=breakdown,
            total_cash_usd=flight.cash_taxes_usd,
            summary_label=summary_label,
        )
        return _trip_plan_to_dict(plan)

    def _tool_get_alternative_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str,
        preferred_time: str = "any",
        preferred_airline: str = "",
        num_travelers: int = 1,
    ) -> list[dict[str, Any]]:
        flights = self._amadeus.search_flights(
            origin, destination, departure_date, return_date, num_travelers, max_results=8
        )
        if preferred_time != "any":
            flights = _filter_by_time(flights, preferred_time)
        if preferred_airline:
            flights = [
                f for f in flights
                if any(s.airline == preferred_airline for s in f.outbound_segments)
            ]
        self._last_flights = flights
        return [_flight_to_dict(i, f) for i, f in enumerate(flights)]

    def _tool_get_alternative_hotels(
        self,
        city_code: str,
        check_in: str,
        check_out: str,
        tier: str = "midrange",
        chain_preference: str = "",
        num_travelers: int = 1,
    ) -> list[dict[str, Any]]:
        hotels = self._amadeus.search_hotels(city_code, check_in, check_out, num_travelers, max_results=8)
        tier_stars = {"budget": (1, 2.5), "midrange": (2.5, 3.5), "upscale": (3.5, 4.5), "luxury": (4.5, 6)}
        lo, hi = tier_stars.get(tier, (1, 6))
        hotels = [h for h in hotels if lo <= h.star_rating <= hi]
        if chain_preference:
            hotels = [h for h in hotels if chain_preference.lower() in h.hotel_chain.lower()]
        self._last_hotels = hotels
        return [_hotel_to_dict(i, h) for i, h in enumerate(hotels)]

    def _tool_mark_preferences_complete(self, **kwargs: Any) -> dict[str, Any]:
        # The phase transition is handled by the loop — just ack here
        return {"status": "preferences_confirmed", "details": kwargs}

    def store_trip_plans_from_results(self, results: list[dict[str, Any]]) -> list[Any]:
        """Parse TripPlan dicts from calculate_trip_cost results."""
        from travel_agent.models.travel import TripPlan  # local import to avoid circular
        plans = []
        for r in results:
            try:
                plans.append(TripPlan(**r))
            except Exception:
                pass
        return plans


def _flight_to_dict(index: int, f: FlightOption) -> dict[str, Any]:
    return {
        "index": index,
        "outbound": [s.model_dump() for s in f.outbound_segments],
        "inbound": [s.model_dump() for s in f.inbound_segments],
        "total_miles_required": f.total_miles_required,
        "program_to_book": f.program_to_book.value,
        "source_issuer": f.source_issuer.value,
        "transfer_partner_used": f.transfer_partner_used,
        "cash_taxes_usd": str(f.cash_taxes_usd),
        "amadeus_offer_id": f.amadeus_offer_id,
    }


def _hotel_to_dict(index: int, h: HotelOption) -> dict[str, Any]:
    return {
        "index": index,
        "hotel_name": h.hotel_name,
        "hotel_chain": h.hotel_chain,
        "star_rating": h.star_rating,
        "check_in": h.check_in,
        "check_out": h.check_out,
        "total_points_required": h.total_points_required,
        "program_to_book": h.program_to_book.value,
        "source_issuer": h.source_issuer.value,
        "amadeus_hotel_id": h.amadeus_hotel_id,
    }


def _trip_plan_to_dict(plan: TripPlan) -> dict[str, Any]:
    return {
        "flight": _flight_to_dict(0, plan.flight),
        "hotel": _hotel_to_dict(0, plan.hotel),
        "points_breakdown": [
            {
                "issuer": b.issuer.value,
                "program": b.program.value,
                "points_used": b.points_used,
                "cpp": str(b.cpp),
                "cash_value_usd": str(b.cash_value_usd),
                "effective_cpp": str(b.effective_cpp),
            }
            for b in plan.points_breakdown
        ],
        "total_cash_usd": str(plan.total_cash_usd),
        "summary_label": plan.summary_label,
        "blended_cpp": str(plan.blended_cpp),
    }


def _filter_by_time(flights: list[FlightOption], preferred_time: str) -> list[FlightOption]:
    windows = {
        "morning": (6, 12),
        "afternoon": (12, 18),
        "evening": (18, 24),
    }
    lo, hi = windows.get(preferred_time, (0, 24))
    result = []
    for f in flights:
        if not f.outbound_segments:
            continue
        dep = f.outbound_segments[0].departure_time
        try:
            hour = int(dep[11:13])
        except (IndexError, ValueError):
            result.append(f)
            continue
        if lo <= hour < hi:
            result.append(f)
    return result or flights  # fallback: return all if no match
