"""Rich tables for trip plan comparison and flight/hotel cards."""

from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from travel_agent.models.travel import FlightOption, HotelOption, TripPlan

console = Console()


def render_trip_plans_table(plans: list[TripPlan]) -> None:
    """Render a comparison table of all trip plans."""
    table = Table(
        title="[bold cyan]Trip Plan Options[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
        show_lines=True,
    )
    table.add_column("#", style="bold", width=3, justify="center")
    table.add_column("Summary", min_width=20)
    table.add_column("Flight", min_width=22)
    table.add_column("Hotel", min_width=20)
    table.add_column("Points Used", min_width=14, justify="right")
    table.add_column("Cash Taxes", justify="right")
    table.add_column("CPP", justify="right")

    for i, plan in enumerate(plans, start=1):
        flight = plan.flight
        hotel = plan.hotel
        seg = flight.outbound_segments[0] if flight.outbound_segments else None
        route = f"{seg.origin}→{seg.destination}" if seg else "—"
        dep = seg.departure_time[11:16] if seg and len(seg.departure_time) > 11 else ""
        airline_code = seg.airline if seg else ""
        flight_str = f"{airline_code} {route}\n{dep} | {flight.program_to_book.value}\n{flight.total_miles_required:,} pts"

        hotel_str = f"{hotel.hotel_name}\n{'★' * int(hotel.star_rating)} {hotel.star_rating}\n{hotel.total_points_required:,} pts"

        total_points = sum(b.points_used for b in plan.points_breakdown)
        pts_str = f"{total_points:,}"
        cpp_color = "green" if plan.blended_cpp > 1.5 else ("yellow" if plan.blended_cpp > 1.0 else "red")
        cpp_str = f"[{cpp_color}]{plan.blended_cpp:.3f}¢[/{cpp_color}]"

        table.add_row(
            str(i),
            plan.summary_label,
            flight_str,
            hotel_str,
            pts_str,
            f"${plan.total_cash_usd}",
            cpp_str,
        )

    console.print()
    console.print(table)
    console.print()


def render_flight_card(flight: FlightOption) -> Panel:
    lines: list[str] = []
    for seg in flight.outbound_segments:
        lines.append(f"  ✈  {seg.origin} → {seg.destination}  {seg.departure_time[11:16]} → {seg.arrival_time[11:16]}  [{seg.airline} {seg.flight_number}]")
    lines.append("  ─── return ───")
    for seg in flight.inbound_segments:
        lines.append(f"  ✈  {seg.origin} → {seg.destination}  {seg.departure_time[11:16]} → {seg.arrival_time[11:16]}  [{seg.airline} {seg.flight_number}]")
    lines.append(f"\n  Program: {flight.program_to_book.value}  |  Miles: {flight.total_miles_required:,}  |  Taxes: ${flight.cash_taxes_usd}")
    return Panel("\n".join(lines), title="[bold]Flight Details[/bold]", border_style="blue")


def render_hotel_card(hotel: HotelOption) -> Panel:
    stars = "★" * int(hotel.star_rating)
    lines = [
        f"  {hotel.hotel_name}  {stars}",
        f"  Chain: {hotel.hotel_chain}",
        f"  Check-in: {hotel.check_in}  →  Check-out: {hotel.check_out}",
        f"  Program: {hotel.program_to_book.value}  |  Points: {hotel.total_points_required:,}",
    ]
    return Panel("\n".join(lines), title="[bold]Hotel Details[/bold]", border_style="green")


def render_alternatives_table(items: list[dict[str, Any]], kind: str = "flight") -> None:
    """Render a table of alternative flights or hotels for fine-tuning."""
    if kind == "flight":
        _render_alternative_flights(items)
    else:
        _render_alternative_hotels(items)


def _render_alternative_flights(flights: list[dict[str, Any]]) -> None:
    table = Table(
        title="[bold cyan]Alternative Flights[/bold cyan]",
        header_style="bold magenta",
        border_style="dim",
        show_lines=True,
    )
    table.add_column("#", width=3, justify="center")
    table.add_column("Route")
    table.add_column("Departure")
    table.add_column("Program")
    table.add_column("Miles", justify="right")
    table.add_column("Taxes", justify="right")

    for f in flights:
        idx = str(f.get("index", ""))
        outbound = f.get("outbound", [])
        seg = outbound[0] if outbound else {}
        route = f"{seg.get('origin', '')}→{seg.get('destination', '')}" if seg else "—"
        dep = str(seg.get("departure_time", ""))
        dep_str = dep[11:16] if len(dep) > 11 else dep
        table.add_row(
            idx,
            route,
            dep_str,
            str(f.get("program_to_book", "")),
            f"{int(f.get('total_miles_required', 0)):,}",
            f"${f.get('cash_taxes_usd', '0')}",
        )

    console.print()
    console.print(table)


def _render_alternative_hotels(hotels: list[dict[str, Any]]) -> None:
    table = Table(
        title="[bold cyan]Alternative Hotels[/bold cyan]",
        header_style="bold magenta",
        border_style="dim",
        show_lines=True,
    )
    table.add_column("#", width=3, justify="center")
    table.add_column("Hotel")
    table.add_column("Stars", justify="center")
    table.add_column("Program")
    table.add_column("Points", justify="right")

    for h in hotels:
        stars = int(float(str(h.get("star_rating", 3))))
        table.add_row(
            str(h.get("index", "")),
            str(h.get("hotel_name", "")),
            "★" * stars,
            str(h.get("program_to_book", "")),
            f"{int(h.get('total_points_required', 0)):,}",
        )

    console.print()
    console.print(table)


def render_points_breakdown(plan: TripPlan) -> None:
    """Render a detailed points breakdown panel for a selected plan."""
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("Issuer")
    table.add_column("Program")
    table.add_column("Points", justify="right")
    table.add_column("CPP", justify="right")
    table.add_column("Value", justify="right")

    for b in plan.points_breakdown:
        cpp_color = "green" if b.cpp > 1.5 else ("yellow" if b.cpp > 1.0 else "red")
        table.add_row(
            b.issuer.value.upper(),
            b.program.value,
            f"{b.points_used:,}",
            f"[{cpp_color}]{b.cpp:.2f}¢[/{cpp_color}]",
            f"${b.cash_value_usd}",
        )

    total_pts = sum(b.points_used for b in plan.points_breakdown)
    total_val = sum(b.cash_value_usd for b in plan.points_breakdown)
    table.add_row(
        "[bold]TOTAL[/bold]", "", f"[bold]{total_pts:,}[/bold]",
        f"[bold]{plan.blended_cpp:.3f}¢[/bold]", f"[bold]${total_val}[/bold]",
    )

    console.print(Panel(table, title="[bold]Points Breakdown[/bold]", border_style="yellow"))
