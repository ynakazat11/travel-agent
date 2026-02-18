"""Rich prompts for points input, profile setup, and fine-tune menus."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from travel_agent.models.points import ISSUER_TO_PROGRAM, Issuer, PointsBalance
from travel_agent.models.preferences import (
    AccommodationTier,
    FlightTimePreference,
    PointsStrategy,
    TravelPreferences,
)
from travel_agent.models.profile import ProfilePoints, ProfilePreferences, UserProfile
from travel_agent.models.travel import TripPlan

console = Console()


def prompt_points_balances() -> list[PointsBalance]:
    """Interactive Rich prompt to collect points balances for all 5 issuers."""
    console.print()
    console.print(
        Panel(
            "[bold cyan]Welcome to Travel Points Planner[/bold cyan]\n\n"
            "Let's start by entering your current points balances.\n"
            "Enter [bold]0[/bold] if you don't hold that currency.",
            title="Points Input",
            border_style="cyan",
        )
    )
    console.print()

    issuer_labels = {
        Issuer.chase: ("Chase Ultimate Rewards (UR)", "chase_ur"),
        Issuer.amex: ("Amex Membership Rewards (MR)", "amex_mr"),
        Issuer.citi: ("Citi ThankYou Points (TY)", "citi_ty"),
        Issuer.capital_one: ("Capital One Miles", "capital_one_miles"),
        Issuer.bilt: ("Bilt Rewards", "bilt_rewards"),
    }

    balances: list[PointsBalance] = []
    for issuer, (label, _) in issuer_labels.items():
        while True:
            try:
                raw = Prompt.ask(f"  [bold]{label}[/bold]", default="0")
                # Allow commas in input
                val = int(raw.replace(",", "").replace(" ", ""))
                if val < 0:
                    console.print("  [red]Must be 0 or greater.[/red]")
                    continue
                break
            except ValueError:
                console.print("  [red]Please enter a number (e.g. 75000).[/red]")

        program = ISSUER_TO_PROGRAM[issuer]
        balances.append(PointsBalance(issuer=issuer, program=program, balance=val))

    # Confirmation table
    console.print()
    table = Table(title="Your Points Portfolio", header_style="bold magenta", border_style="dim")
    table.add_column("Issuer")
    table.add_column("Program")
    table.add_column("Balance", justify="right")

    for b in balances:
        table.add_row(
            b.issuer.value.upper(),
            b.program.value,
            f"{b.balance:,}",
        )
    console.print(table)
    console.print()

    confirmed = Prompt.ask("Confirm balances? [Y/n]", default="y")
    if confirmed.lower().startswith("n"):
        return prompt_points_balances()

    return balances


def prompt_fine_tune_menu(plan: TripPlan) -> str:
    """Show fine-tune options for a selected plan. Returns the user's choice."""
    console.print()
    console.print(
        Panel(
            "[bold]Fine-Tune Your Trip[/bold]\n\n"
            "  [1] Swap outbound/inbound flight\n"
            "  [2] Swap hotel\n"
            "  [3] Change cabin class preference\n"
            "  [4] Adjust travel dates\n"
            "  [5] Done — return to plan list\n"
            "  [6] Give feedback in your own words\n",
            title=f"Fine-Tuning: {plan.summary_label}",
            border_style="yellow",
        )
    )
    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5", "6"], default="5")
    return choice


def prompt_plan_selection(num_plans: int) -> tuple[int, bool]:
    """Prompt the user to pick a plan or enter fine-tune mode.

    Returns (plan_index, is_fine_tune).
    """
    console.print()
    console.print("[bold]Select a plan number to finalize, or [F] to fine-tune:[/bold]")
    choices = [str(i) for i in range(1, num_plans + 1)] + ["f", "F"]
    raw = Prompt.ask(f"Plan [1–{num_plans}] or [F]ine-tune", default="1")
    if raw.lower() == "f":
        idx_raw = Prompt.ask(f"Which plan to fine-tune? [1–{num_plans}]", default="1")
        try:
            return int(idx_raw) - 1, True
        except ValueError:
            return 0, True
    try:
        return int(raw) - 1, False
    except ValueError:
        return 0, False


def prompt_alternative_selection(num_items: int, kind: str = "option") -> int | None:
    """Prompt to select an alternative from the rendered list. Returns 0-based index or None."""
    console.print()
    raw = Prompt.ask(
        f"Pick a {kind} number to swap in (or [S]kip)", default="s"
    )
    if raw.lower() == "s":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def prompt_profile_setup(existing: UserProfile | None = None) -> UserProfile:
    """Interactive wizard to create or update a user profile."""
    console.print()
    console.print(
        Panel(
            "[bold cyan]Profile Setup[/bold cyan]\n\n"
            "Save your points balances and stable preferences\n"
            "so you don't have to re-enter them every session.",
            title="Profile Wizard",
            border_style="cyan",
        )
    )

    defaults = existing or UserProfile()
    prefs = defaults.preferences
    pts = defaults.points

    # --- Preferences ---
    console.print("\n[bold]Travel Preferences[/bold]\n")

    origin = Prompt.ask(
        "  Home airport (IATA code)",
        default=prefs.origin_airport or "SFO",
    ).upper().strip()

    while True:
        try:
            raw = Prompt.ask("  Default number of travelers", default=str(prefs.num_travelers))
            num_travelers = int(raw)
            if num_travelers < 1:
                console.print("  [red]Must be at least 1.[/red]")
                continue
            break
        except ValueError:
            console.print("  [red]Please enter a number.[/red]")

    flight_time = Prompt.ask(
        "  Flight time preference",
        choices=["morning", "afternoon", "evening", "any"],
        default=prefs.flight_time_preference.value,
    )

    tier = Prompt.ask(
        "  Accommodation tier",
        choices=["budget", "midrange", "upscale", "luxury"],
        default=prefs.accommodation_tier.value,
    )

    strategy = Prompt.ask(
        "  Points strategy",
        choices=["POINTS_ONLY", "MIXED_OK"],
        default=prefs.points_strategy.value,
    )

    # --- Points ---
    console.print("\n[bold]Points Balances[/bold]\n")

    issuer_labels = [
        ("chase", "Chase Ultimate Rewards (UR)"),
        ("amex", "Amex Membership Rewards (MR)"),
        ("citi", "Citi ThankYou Points (TY)"),
        ("capital_one", "Capital One Miles"),
        ("bilt", "Bilt Rewards"),
    ]

    points_values: dict[str, int] = {}
    for field_name, label in issuer_labels:
        current = getattr(pts, field_name)
        while True:
            try:
                raw_val = Prompt.ask(f"  [bold]{label}[/bold]", default=f"{current:,}")
                val = int(raw_val.replace(",", "").replace(" ", ""))
                if val < 0:
                    console.print("  [red]Must be 0 or greater.[/red]")
                    continue
                points_values[field_name] = val
                break
            except ValueError:
                console.print("  [red]Please enter a number (e.g. 75000).[/red]")

    profile = UserProfile(
        preferences=ProfilePreferences(
            origin_airport=origin,
            num_travelers=num_travelers,
            flight_time_preference=FlightTimePreference(flight_time),
            accommodation_tier=AccommodationTier(tier),
            points_strategy=PointsStrategy(strategy),
        ),
        points=ProfilePoints(**points_values),
    )

    # Show summary for confirmation
    show_loaded_profile(profile.points.to_balances(), profile.preferences)

    confirmed = Prompt.ask("Save this profile? [Y/n]", default="y")
    if confirmed.lower().startswith("n"):
        return prompt_profile_setup(existing)

    return profile


def show_loaded_profile(
    balances: list[PointsBalance], prefs: ProfilePreferences
) -> None:
    """Print a summary table of loaded profile data."""
    console.print()

    # Preferences summary
    pref_table = Table(
        title="Loaded Profile — Preferences",
        header_style="bold magenta",
        border_style="dim",
    )
    pref_table.add_column("Setting")
    pref_table.add_column("Value")
    pref_table.add_row("Origin Airport", prefs.origin_airport)
    pref_table.add_row("Travelers", str(prefs.num_travelers))
    pref_table.add_row("Flight Time", prefs.flight_time_preference.value)
    pref_table.add_row("Accommodation", prefs.accommodation_tier.value)
    pref_table.add_row("Points Strategy", prefs.points_strategy.value)
    console.print(pref_table)

    # Points summary
    pts_table = Table(
        title="Loaded Profile — Points",
        header_style="bold magenta",
        border_style="dim",
    )
    pts_table.add_column("Issuer")
    pts_table.add_column("Program")
    pts_table.add_column("Balance", justify="right")

    for b in balances:
        pts_table.add_row(b.issuer.value.upper(), b.program.value, f"{b.balance:,}")

    console.print(pts_table)
    console.print()


def prompt_confirm_preferences(prefs: TravelPreferences) -> str:
    """Render a summary of captured preferences and ask user to confirm.

    Returns "y", "n", or "edit".
    """
    display_dest = prefs.destination_display_name or prefs.destination_query
    iata = prefs.resolved_destination

    table = Table(
        title="Trip Preferences Summary",
        header_style="bold magenta",
        border_style="dim",
    )
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Destination", f"{display_dest} ({iata})" if iata else display_dest)
    table.add_row("Origin", prefs.origin_airport)
    table.add_row("Dates", f"{prefs.departure_date} → {prefs.return_date}")
    table.add_row("Flexibility", f"±{prefs.date_flexibility_days} days")
    table.add_row("Travelers", str(prefs.num_travelers))
    table.add_row("Flight Time", prefs.flight_time_preference.value)
    table.add_row("Accommodation", prefs.accommodation_tier.value)
    table.add_row("Points Strategy", prefs.points_strategy.value)

    console.print()
    console.print(table)
    console.print()

    raw = Prompt.ask(
        "Does this look right? [Y/n/edit]",
        choices=["y", "n", "edit", "Y", "N", "Edit", "EDIT", "e", "E"],
        default="y",
    )
    normalized = raw.strip().lower()
    if normalized in ("e", "edit"):
        return "edit"
    return normalized


def prompt_save_guide(destination: str) -> str | None:
    """Ask user if they want to save the booking guide."""
    console.print()
    raw = Prompt.ask(
        f"Save booking guide to ~/Downloads/trip-guide-{destination}.md? [Y/n]",
        default="y",
    )
    if raw.lower().startswith("n"):
        return None
    import os
    path = os.path.expanduser(f"~/Downloads/trip-guide-{destination}.md")
    return path
