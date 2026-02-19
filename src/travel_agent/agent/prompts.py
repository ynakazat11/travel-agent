"""Build dynamic system prompt based on current session state."""

from travel_agent.models.preferences import PointsStrategy
from travel_agent.models.session import ConversationSession, SessionPhase


def _sanitize_prompt_str(s: str, max_len: int = 100) -> str:
    """Strip control characters and truncate user-supplied text for safe prompt interpolation."""
    return s.replace("\n", " ").replace("\r", " ")[:max_len]


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
- When you have enough information to search, call mark_preferences_complete immediately.
- IMPORTANT: When calling mark_preferences_complete, do NOT include questions or suggestions in the same response. Just confirm what you're doing. The user will have a chance to refine after reviewing the preferences summary.

## Tool Usage Policy
- resolve_destination: Call when destination is ambiguous or described in plain language.
- search_flights: Call with exact IATA codes and dates.
- search_hotels: Call after you have a resolved city code.
- lookup_transfer_options: Call before calculate_trip_cost to verify coverage.
- calculate_trip_cost: Call to finalize each TripPlan — aim for 3–5 distinct plans.
- web_search_hotels: Fallback when search_hotels results don't match the user's accommodation tier. Returns cash-booking options.
- get_alternative_flights / get_alternative_hotels: Only during FINE_TUNING phase.
- mark_preferences_complete: Call as soon as you have: destination, origin, dates, travelers, strategy, flight pref, accommodation pref, nonstop pref.
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
        if session.profile_loaded:
            p = session.preferences
            return (
                "The user has a saved profile with these defaults:\n"
                f"  - Origin airport: {p.origin_airport}\n"
                f"  - Travelers: {p.num_travelers}\n"
                f"  - Flight time: {p.flight_time_preference.value}\n"
                f"  - Accommodation: {p.accommodation_tier.value}\n"
                f"  - Points strategy: {p.points_strategy.value}\n"
                f"  - Nonstop preferred: {p.nonstop_preferred}\n\n"
                "Do NOT re-ask about these. Focus on destination, dates, and flexibility. "
                "The user can override any default by mentioning it. "
                "When you have destination and dates, call mark_preferences_complete "
                "including ALL fields (use the defaults above for anything the user didn't override)."
            )
        return (
            "Gather travel preferences through friendly conversation. You need: "
            "destination, origin airport, departure/return dates, date flexibility (0–14 days), "
            "number of travelers, flight time preference (morning/afternoon/evening/any), "
            "accommodation tier (budget/midrange/upscale/luxury), nonstop preference "
            "(direct flights preferred or connections OK), and points strategy "
            "(POINTS_ONLY or MIXED_OK). Ask one or two things at a time. "
            "When you have everything, call mark_preferences_complete."
        )

    if phase == SessionPhase.SEARCHING:
        prefs = session.preferences
        display_dest = _sanitize_prompt_str(
            prefs.destination_display_name or prefs.destination_query
        )
        iata_dest = prefs.resolved_destination

        if prefs.points_strategy == PointsStrategy.points_only:
            strategy_guidance = (
                "Prefer high-CPP options and diverse issuer usage."
            )
        else:
            strategy_guidance = (
                "Location match is more important than points optimization. "
                f"The user wants to stay in or near {display_dest}. "
                "If the destination does not have its own IATA city code, search hotels using "
                "latitude and longitude coordinates instead of the nearest major city's code. "
                "For example, for Sedona use latitude=34.87, longitude=-111.76 rather than "
                "city_code='PHX'. This ensures hotel results are actually near the destination."
            )

        nonstop_guidance = ""
        if prefs.nonstop_preferred:
            nonstop_guidance = (
                "The user prefers nonstop flights. Search with nonstop=true first. "
                "If no results, retry with nonstop=false and note that only connecting flights are available. "
            )

        tier = prefs.accommodation_tier.value
        hotel_fallback_guidance = (
            f"If hotel results from search_hotels do not match the user's accommodation tier ({tier}), "
            "call web_search_hotels as a fallback. Label web results as cash-booking options. "
        )

        return (
            f"Search autonomously for the best award trip options. "
            f"Destination: {display_dest} (IATA: {iata_dest or 'unresolved'}). "
            f"Origin: {prefs.origin_airport}. "
            f"Dates: {prefs.departure_date} → {prefs.return_date} "
            f"(±{prefs.date_flexibility_days} days flexibility). "
            f"Travelers: {prefs.num_travelers}. "
            f"Strategy: {prefs.points_strategy.value}. "
            "Chain tools: resolve_destination (if needed) → search_flights → search_hotels "
            "→ lookup_transfer_options → calculate_trip_cost. "
            "Build 3–5 TripPlans with different flight/hotel/issuer combinations. "
            f"{strategy_guidance} "
            f"{nonstop_guidance}"
            f"{hotel_fallback_guidance}"
        )

    if phase == SessionPhase.FINE_TUNING:
        return (
            "The user wants to fine-tune their selected plan. "
            "Use get_alternative_flights or get_alternative_hotels as requested. "
            "Present alternatives clearly. Do not call calculate_trip_cost unless the user confirms a swap."
        )

    return "Assist the user with their travel planning."
