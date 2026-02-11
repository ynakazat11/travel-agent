"""Build dynamic system prompt based on current session state."""

from travel_agent.models.session import ConversationSession, SessionPhase


def build_system_prompt(session: ConversationSession) -> str:
    balances_text = _format_balances(session)
    phase_instructions = _phase_instructions(session)

    return f"""You are an expert travel points advisor helping a user plan an award trip.

## User's Points Portfolio
{balances_text}

## Your Role
{phase_instructions}

## Core Principles
- Always calculate actual points requirements before recommending transfers.
- Bilt Rewards is the ONLY issuer with a 1:1 transfer to American Airlines AAdvantage — highlight this advantage when AA is relevant.
- When computing transfer math: source_points_needed = ceil(destination_points * ratio_from / ratio_to).
- Present CPP (cents per point) comparisons to help the user understand relative value.
- Be conversational and concise. Do not ask multiple questions at once.
- When you have enough information to search, call mark_preferences_complete immediately rather than asking further questions.

## Tool Usage Policy
- resolve_destination: Call when destination is ambiguous or described in plain language.
- search_flights: Call with exact IATA codes and dates.
- search_hotels: Call after you have a resolved city code.
- lookup_transfer_options: Call before calculate_trip_cost to verify coverage.
- calculate_trip_cost: Call to finalize each TripPlan — aim for 3–5 distinct plans.
- get_alternative_flights / get_alternative_hotels: Only during FINE_TUNING phase.
- mark_preferences_complete: Call as soon as you have: destination, origin, dates, travelers, strategy, flight pref, accommodation pref.
"""


def _format_balances(session: ConversationSession) -> str:
    if not session.points_balances:
        return "  (not yet entered)"
    lines = []
    for b in session.points_balances:
        lines.append(f"  - {b.issuer.value.upper()}: {b.balance:,} {b.program.value}")
    return "\n".join(lines)


def _phase_instructions(session: ConversationSession) -> str:
    phase = session.phase

    if phase == SessionPhase.PREFERENCE_GATHERING:
        return (
            "Gather travel preferences through friendly conversation. You need: "
            "destination, origin airport, departure/return dates, date flexibility (0–14 days), "
            "number of travelers, flight time preference (morning/afternoon/evening/any), "
            "accommodation tier (budget/midrange/upscale/luxury), and points strategy "
            "(POINTS_ONLY or MIXED_OK). Ask one or two things at a time. "
            "When you have everything, call mark_preferences_complete."
        )

    if phase == SessionPhase.SEARCHING:
        prefs = session.preferences
        return (
            f"Search autonomously for the best award trip options. "
            f"Destination: {prefs.resolved_destination or prefs.destination_query}. "
            f"Origin: {prefs.origin_airport}. "
            f"Dates: {prefs.departure_date} → {prefs.return_date} "
            f"(±{prefs.date_flexibility_days} days flexibility). "
            f"Travelers: {prefs.num_travelers}. "
            f"Strategy: {prefs.points_strategy.value}. "
            "Chain tools: resolve_destination (if needed) → search_flights → search_hotels "
            "→ lookup_transfer_options → calculate_trip_cost. "
            "Build 3–5 TripPlans with different flight/hotel/issuer combinations. "
            "Prefer high-CPP options and diverse issuer usage."
        )

    if phase == SessionPhase.FINE_TUNING:
        return (
            "The user wants to fine-tune their selected plan. "
            "Use get_alternative_flights or get_alternative_hotels as requested. "
            "Present alternatives clearly. Do not call calculate_trip_cost unless the user confirms a swap."
        )

    return "Assist the user with their travel planning."
