"""Core agentic loop: multi-turn Claude API with tool dispatch."""

import json
from typing import Any

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.status import Status

from travel_agent.agent.prompts import build_system_prompt
from travel_agent.agent.tools import TOOL_SCHEMAS, ToolExecutor
from travel_agent.config import settings
from travel_agent.models.preferences import (
    AccommodationTier,
    FlightTimePreference,
    PointsStrategy,
    TravelPreferences,
)
from travel_agent.models.session import ConversationSession, SessionPhase
from travel_agent.models.travel import TripPlan

console = Console()

_MAX_TOOL_ROUNDS = 20  # safety limit per agent turn


def run_agent_turn(
    session: ConversationSession,
    tool_executor: ToolExecutor,
    user_input: str | None = None,
    spinner_status: Status | None = None,
) -> list[TripPlan]:
    """Run one user turn through the agentic loop.

    Returns any new TripPlans assembled during this turn.
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    if user_input is not None:
        session.add_message("user", user_input)

    new_plans: list[TripPlan] = []
    rounds = 0

    while rounds < _MAX_TOOL_ROUNDS:
        rounds += 1

        if spinner_status:
            spinner_status.update(f"[dim]Claude thinking… (round {rounds})[/dim]")

        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            system=build_system_prompt(session),
            messages=session.conversation_history,  # type: ignore[arg-type]
            tools=TOOL_SCHEMAS,  # type: ignore[arg-type]
        )

        # Print any text content immediately
        for block in response.content:
            if hasattr(block, "text") and block.text:
                if spinner_status:
                    spinner_status.stop()
                console.print(Markdown(block.text))
                if spinner_status:
                    spinner_status.start()

        if response.stop_reason == "end_turn":
            session.add_message("assistant", _content_to_serializable(response.content))
            break

        if response.stop_reason == "tool_use":
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    if spinner_status:
                        spinner_status.update(f"[dim]Calling {block.name}…[/dim]")
                    result_str = tool_executor.execute(block.name, block.input)
                    result_data = json.loads(result_str)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_str,
                        }
                    )
                    # Handle phase transitions triggered by tool calls
                    plan = _handle_phase_transition(
                        session, block.name, block.input, result_data, tool_executor
                    )
                    if plan:
                        new_plans.append(plan)

            session.add_message("assistant", _content_to_serializable(response.content))
            session.add_message("user", tool_results)
            continue

        # Unexpected stop reason — break out
        session.add_message("assistant", _content_to_serializable(response.content))
        break

    return new_plans


def _handle_phase_transition(
    session: ConversationSession,
    tool_name: str,
    tool_input: dict[str, Any],
    result: Any,
    tool_executor: ToolExecutor,
) -> TripPlan | None:
    if tool_name == "mark_preferences_complete":
        existing = session.preferences
        prefs = TravelPreferences(
            destination_query=tool_input.get("destination_query", ""),
            resolved_destination=tool_input.get("resolved_destination", ""),
            destination_display_name=tool_input.get("destination_display_name", "")
            or tool_input.get("destination_query", ""),
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
        session.preferences = prefs
        session.advance_phase(SessionPhase.CONFIRM_PREFERENCES)
        return None

    if tool_name == "calculate_trip_cost" and isinstance(result, dict) and "flight" in result:
        try:
            from travel_agent.models.points import CurrencyProgram, Issuer
            from travel_agent.models.travel import (
                FlightOption,
                FlightSegment,
                HotelOption,
                PointsCostBreakdown,
                TripPlan,
            )
            from decimal import Decimal

            def _seg(s: dict[str, Any]) -> FlightSegment:
                return FlightSegment(**s)

            fd = result["flight"]
            hd = result["hotel"]
            flight = FlightOption(
                outbound_segments=[_seg(s) for s in fd["outbound"]],
                inbound_segments=[_seg(s) for s in fd["inbound"]],
                total_miles_required=fd["total_miles_required"],
                program_to_book=CurrencyProgram(fd["program_to_book"]),
                source_issuer=Issuer(fd["source_issuer"]),
                transfer_partner_used=fd.get("transfer_partner_used", ""),
                cash_taxes_usd=Decimal(fd.get("cash_taxes_usd", "0")),
                amadeus_offer_id=fd.get("amadeus_offer_id", ""),
            )
            hotel = HotelOption(
                hotel_name=hd["hotel_name"],
                hotel_chain=hd.get("hotel_chain", ""),
                star_rating=hd.get("star_rating", 3.0),
                check_in=hd["check_in"],
                check_out=hd["check_out"],
                total_points_required=hd["total_points_required"],
                program_to_book=CurrencyProgram(hd["program_to_book"]),
                source_issuer=Issuer(hd["source_issuer"]),
                amadeus_hotel_id=hd.get("amadeus_hotel_id", ""),
            )
            breakdown = [
                PointsCostBreakdown(
                    issuer=Issuer(b["issuer"]),
                    program=CurrencyProgram(b["program"]),
                    points_used=b["points_used"],
                    cpp=Decimal(b["cpp"]),
                )
                for b in result["points_breakdown"]
            ]
            plan = TripPlan(
                flight=flight,
                hotel=hotel,
                points_breakdown=breakdown,
                total_cash_usd=Decimal(result.get("total_cash_usd", "0")),
                summary_label=result.get("summary_label", ""),
            )
            session.current_trip_plans.append(plan)
            # Advance to OPTIONS_PRESENTED after 3+ plans
            if (
                session.phase == SessionPhase.SEARCHING
                and len(session.current_trip_plans) >= 3
            ):
                session.advance_phase(SessionPhase.OPTIONS_PRESENTED)
                session.prune_search_history()
            return plan
        except Exception:
            pass

    return None


def _content_to_serializable(content: list[Any]) -> list[dict[str, Any]]:
    """Convert Anthropic content blocks to plain dicts for history storage."""
    result = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
    return result
