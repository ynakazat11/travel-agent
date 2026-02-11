"""Rich prompts for points input and fine-tune menus."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from travel_agent.models.points import ISSUER_TO_PROGRAM, Issuer, PointsBalance
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
            "  [5] Done — return to plan list\n",
            title=f"Fine-Tuning: {plan.summary_label}",
            border_style="yellow",
        )
    )
    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5"], default="5")
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
