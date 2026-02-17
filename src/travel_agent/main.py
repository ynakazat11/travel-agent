"""Entry point: CLI bootstrap for Travel Points Planner."""

import argparse
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.status import Status

from travel_agent.agent.loop import run_agent_turn
from travel_agent.agent.tools import ToolExecutor
from travel_agent.clients.amadeus import AmadeusClient
from travel_agent.clients.transfer import TransferPartnerDB
from travel_agent.config import settings
from travel_agent.display.booking_guide import render_booking_guide, save_booking_guide
from travel_agent.display.prompts import (
    prompt_fine_tune_menu,
    prompt_plan_selection,
    prompt_points_balances,
    prompt_profile_setup,
    prompt_save_guide,
    show_loaded_profile,
)
from travel_agent.display.tables import (
    render_flight_card,
    render_hotel_card,
    render_points_breakdown,
    render_trip_plans_table,
)
from travel_agent.models.preferences import TravelPreferences
from travel_agent.models.profile import (
    DEFAULT_PROFILE_PATH,
    ProfilePoints,
    ProfilePreferences,
    UserProfile,
    load_profile,
    save_profile,
)
from travel_agent.models.session import ConversationSession, SessionPhase
from travel_agent.models.travel import TripPlan

console = Console()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Travel Points Planner — CLI award travel optimizer"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock Amadeus data (no API calls required)",
    )
    parser.add_argument(
        "--setup-profile",
        action="store_true",
        help="Run the interactive profile setup wizard",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="Path to a custom profile TOML file",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    profile_path: Path = args.profile or DEFAULT_PROFILE_PATH

    # --- Early exit: --setup-profile ---
    if args.setup_profile:
        existing = load_profile(profile_path)
        profile = prompt_profile_setup(existing)
        saved_path = save_profile(profile, profile_path)
        console.print(f"\n[green]Profile saved to {saved_path}[/green]")
        return

    if not args.mock and not settings.anthropic_api_key:
        console.print("[red]Error: ANTHROPIC_API_KEY not set. Copy .env.example to .env and fill it in.[/red]")
        sys.exit(1)

    console.print(
        Panel(
            "[bold cyan]Travel Points Planner[/bold cyan]\n"
            "Optimize your award trips across Chase UR, Amex MR, Citi TY, Capital One & Bilt\n\n"
            f"Mode: {'[yellow]MOCK[/yellow]' if args.mock else '[green]LIVE[/green]'}",
            border_style="cyan",
        )
    )

    # --- Load profile ---
    profile = load_profile(profile_path)
    profile_loaded = False

    if profile and profile.has_points:
        balances = profile.points.to_balances()
        show_loaded_profile(balances, profile.preferences)
        profile_loaded = True
    else:
        # --- Phase: POINTS_INPUT (no profile) ---
        balances = prompt_points_balances()

    # Initialize clients and session
    amadeus = AmadeusClient(mock=args.mock)
    transfer_db = TransferPartnerDB()
    tool_executor = ToolExecutor(amadeus=amadeus, transfer_db=transfer_db, balances=balances)

    session = ConversationSession()
    session.points_balances = balances

    if profile_loaded and profile is not None:
        session.profile_loaded = True
        p = profile.preferences
        session.preferences = TravelPreferences(
            origin_airport=p.origin_airport,
            num_travelers=p.num_travelers,
            flight_time_preference=p.flight_time_preference,
            accommodation_tier=p.accommodation_tier,
            points_strategy=p.points_strategy,
        )

    session.advance_phase(SessionPhase.PREFERENCE_GATHERING)

    # --- Phase: PREFERENCE_GATHERING ---
    console.print()
    if profile_loaded:
        console.print("[bold cyan]Profile loaded! Just tell me where and when.[/bold cyan]")
    else:
        console.print("[bold cyan]Great! Now let's find your perfect trip.[/bold cyan]")
    console.print("[dim]Tell me where you'd like to go and I'll handle the rest.[/dim]\n")

    while session.phase == SessionPhase.PREFERENCE_GATHERING:
        try:
            user_input = console.input("[bold green]You:[/bold green] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye![/yellow]")
            return

        with Status("[dim]Thinking…[/dim]", console=console) as status:
            run_agent_turn(session, tool_executor, user_input=user_input, spinner_status=status)

    # --- Phase: SEARCHING ---
    console.print()
    with Status("[bold cyan]Searching for the best award options…[/bold cyan]", console=console) as status:
        run_agent_turn(session, tool_executor, spinner_status=status)

    # Loop: OPTIONS_PRESENTED → FINE_TUNING → FINALIZING
    while session.phase not in (SessionPhase.FINALIZING, SessionPhase.COMPLETE):

        # OPTIONS_PRESENTED
        if session.phase == SessionPhase.OPTIONS_PRESENTED:
            if not session.current_trip_plans:
                console.print("[red]No trip plans were assembled. Try again with different criteria.[/red]")
                return

            render_trip_plans_table(session.current_trip_plans)
            plan_idx, fine_tune = prompt_plan_selection(len(session.current_trip_plans))

            if fine_tune:
                session.fine_tune_state.active = True
                session.fine_tune_state.target_plan_index = plan_idx
                session.advance_phase(SessionPhase.FINE_TUNING)
            else:
                session.selected_plan = session.current_trip_plans[plan_idx]
                session.advance_phase(SessionPhase.FINALIZING)

        # FINE_TUNING
        elif session.phase == SessionPhase.FINE_TUNING:
            target_idx = session.fine_tune_state.target_plan_index
            plan = session.current_trip_plans[target_idx]

            console.print()
            console.print(render_flight_card(plan.flight))
            console.print(render_hotel_card(plan.hotel))
            render_points_breakdown(plan)

            choice = prompt_fine_tune_menu(plan)

            if choice == "5":
                session.fine_tune_state.active = False
                session.advance_phase(SessionPhase.OPTIONS_PRESENTED)
                continue

            fine_tune_prompt = _build_fine_tune_prompt(choice, plan)
            with Status("[dim]Finding alternatives…[/dim]", console=console) as status:
                run_agent_turn(session, tool_executor, user_input=fine_tune_prompt, spinner_status=status)

            # After agent returns alternatives, show them and let user swap
            _handle_fine_tune_swap(session, tool_executor, choice, plan)

    # FINALIZING
    if session.phase == SessionPhase.FINALIZING and session.selected_plan:
        plan = session.selected_plan
        console.print()
        console.print(render_flight_card(plan.flight))
        console.print(render_hotel_card(plan.hotel))
        render_points_breakdown(plan)

        md = render_booking_guide(plan)

        dest = plan.flight.outbound_segments[-1].destination if plan.flight.outbound_segments else "trip"
        save_path = prompt_save_guide(dest.lower())
        if save_path:
            save_booking_guide(md, save_path)

        session.advance_phase(SessionPhase.COMPLETE)

    # --- Offer to save profile if none existed ---
    if not profile_loaded and profile is None:
        _offer_profile_save(session, profile_path)

    console.print()
    console.print(Panel("[bold green]Happy travels![/bold green]", border_style="green"))
    amadeus.close()


def _offer_profile_save(session: ConversationSession, profile_path: Path) -> None:
    """After a successful run without a profile, offer to save one."""
    console.print()
    raw = Prompt.ask(
        "Save your points & preferences for next time? [Y/n]", default="y"
    )
    if raw.lower().startswith("n"):
        return

    p = session.preferences
    pts_map: dict[str, int] = {}
    for b in session.points_balances:
        pts_map[b.issuer.value] = b.balance

    profile = UserProfile(
        preferences=ProfilePreferences(
            origin_airport=p.origin_airport,
            num_travelers=p.num_travelers,
            flight_time_preference=p.flight_time_preference,
            accommodation_tier=p.accommodation_tier,
            points_strategy=p.points_strategy,
        ),
        points=ProfilePoints(**pts_map),
    )
    saved_path = save_profile(profile, profile_path)
    console.print(f"[green]Profile saved to {saved_path}[/green]")


def _build_fine_tune_prompt(choice: str, plan: TripPlan) -> str:

    if choice == "1":
        seg = plan.flight.outbound_segments[0] if plan.flight.outbound_segments else None
        ret = plan.flight.inbound_segments[0] if plan.flight.inbound_segments else None
        dep = seg.departure_time[:10] if seg else ""
        ret_date = ret.departure_time[:10] if ret else ""
        origin = seg.origin if seg else ""
        dest = seg.destination if seg else ""
        return (
            f"Find alternative flights for {origin}→{dest} on {dep}, return {ret_date}. "
            f"Show me different airlines and departure times."
        )
    elif choice == "2":
        h = plan.hotel
        return (
            f"Find alternative hotels in the same city ({h.check_in}→{h.check_out}). "
            f"Show a mix of chains and point programs."
        )
    elif choice == "3":
        return "Find business class or premium economy alternatives for this route."
    elif choice == "4":
        return "Show me flight options ±3 days around my current dates for better availability."
    return "Show me alternative options."


def _handle_fine_tune_swap(
    session: ConversationSession,
    tool_executor: ToolExecutor,
    choice: str,
    plan: TripPlan,
) -> None:
    from travel_agent.display.prompts import prompt_alternative_selection
    from travel_agent.display.tables import render_alternatives_table

    target_idx = session.fine_tune_state.target_plan_index

    if choice in ("1", "3", "4") and tool_executor._last_flights:
        items: list[dict[str, Any]] = [
            {
                "index": i,
                "outbound": [s.model_dump() for s in f.outbound_segments],
                "inbound": [s.model_dump() for s in f.inbound_segments],
                "total_miles_required": f.total_miles_required,
                "program_to_book": f.program_to_book.value,
                "cash_taxes_usd": str(f.cash_taxes_usd),
            }
            for i, f in enumerate(tool_executor._last_flights)
        ]
        render_alternatives_table(items, kind="flight")
        sel = prompt_alternative_selection(len(items), kind="flight")
        if sel is not None and sel < len(tool_executor._last_flights):
            updated_flight = tool_executor._last_flights[sel]
            new_plan = session.current_trip_plans[target_idx].model_copy(
                update={"flight": updated_flight}
            )
            session.current_trip_plans[target_idx] = new_plan

    elif choice == "2" and tool_executor._last_hotels:
        hotel_items: list[dict[str, Any]] = [
            {
                "index": i,
                "hotel_name": h.hotel_name,
                "hotel_chain": h.hotel_chain,
                "star_rating": h.star_rating,
                "total_points_required": h.total_points_required,
                "program_to_book": h.program_to_book.value,
            }
            for i, h in enumerate(tool_executor._last_hotels)
        ]
        render_alternatives_table(hotel_items, kind="hotel")
        sel = prompt_alternative_selection(len(hotel_items), kind="hotel")
        if sel is not None and sel < len(tool_executor._last_hotels):
            updated_hotel = tool_executor._last_hotels[sel]
            new_plan = session.current_trip_plans[target_idx].model_copy(
                update={"hotel": updated_hotel}
            )
            session.current_trip_plans[target_idx] = new_plan

    session.advance_phase(SessionPhase.OPTIONS_PRESENTED)


if __name__ == "__main__":
    main()
