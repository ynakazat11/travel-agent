"""Render step-by-step booking guide for a selected TripPlan."""

from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from travel_agent.models.travel import TripPlan

console = Console()

# Booking URLs per program
_TRANSFER_URLS: dict[str, str] = {
    "chase_ur": "https://creditcards.chase.com/ultimate-rewards/",
    "amex_mr": "https://www.americanexpress.com/en-us/rewards/membership-rewards/partners/transfer/",
    "citi_ty": "https://www.citi.com/credit-cards/citi-thankyou-rewards/",
    "capital_one_miles": "https://capital-one-travel.com/rewards",
    "bilt_rewards": "https://www.biltrewards.com/points/transfer",
}

_AWARD_BOOKING_URLS: dict[str, str] = {
    "united_mileageplus": "https://www.united.com/en/us/book-flight/united-awards",
    "american_airlines_aadvantage": "https://www.aa.com/aadvantage-program/miles/redeem/award-travel",
    "delta_skymiles": "https://www.delta.com/us/en/skymiles/redeeming-miles/book-award-travel",
    "southwest_rapid_rewards": "https://www.southwest.com/rapidrewards/",
    "alaska_mileage_plan": "https://www.alaskaair.com/content/mileage-plan/use-miles/award-travel",
    "british_airways_avios": "https://www.britishairways.com/en-us/executive-club/spending-avios/redeeming-avios",
    "air_france_flying_blue": "https://wwws.airfrance.us/information/fidelite/blue-business",
    "air_canada_aeroplan": "https://www.aircanada.com/us/en/aco/home/aeroplan/redeem-miles.html",
    "singapore_krisflyer": "https://www.singaporeair.com/en_UK/us/ppsclub-krisflyer/krisflyer/award/",
    "emirates_skywards": "https://www.emirates.com/us/english/skywards/use-your-miles/award-flights/",
    "turkish_miles_smiles": "https://www.turkishairlines.com/en-us/miles-smiles/",
    "virgin_atlantic_flying_club": "https://www.virgin-atlantic.com/us/en/flying-club/spend-miles.html",
    "world_of_hyatt": "https://world.hyatt.com/content/gp/en/rewards/free-nights.html",
    "marriott_bonvoy": "https://www.marriott.com/bonvoy/rewards/points/redeem.mi",
    "hilton_honors": "https://www.hilton.com/en/hilton-honors/redeem/",
}


def render_booking_guide(plan: TripPlan) -> str:
    """Render the booking guide to the console and return markdown string."""
    flight = plan.flight
    hotel = plan.hotel

    lines: list[str] = [
        f"# Booking Guide: {plan.summary_label}",
        "",
        "## Overview",
        f"- **Destination**: {flight.outbound_segments[-1].destination if flight.outbound_segments else 'Unknown'}",
        f"- **Travel Dates**: {flight.outbound_segments[0].departure_time[:10] if flight.outbound_segments else '—'} → {flight.inbound_segments[0].departure_time[:10] if flight.inbound_segments else '—'}",
        f"- **Hotel**: {hotel.hotel_name} ({hotel.check_in} → {hotel.check_out})",
        f"- **Blended CPP**: {plan.blended_cpp:.3f}¢",
        "",
        "---",
        "",
        "## Step 1: Transfer Points",
        "",
    ]

    for b in plan.points_breakdown:
        transfer_url = _TRANSFER_URLS.get(b.issuer.value, "https://your-card-issuer.com")
        lines += [
            f"### {b.issuer.value.upper()} → {b.program.value}",
            f"- **Points to transfer**: {b.points_used:,}",
            f"- **Transfer URL**: {transfer_url}",
            f"- **Estimated CPP**: {b.cpp:.2f}¢  (cash value ≈ ${b.cash_value_usd})",
            "",
            "> ⚠️ Transfer points BEFORE booking the award — transfers are often instant but",
            "> some programs (Singapore KrisFlyer) can take 24–48 hours. Do NOT book until",
            "> points land in the loyalty account.",
            "",
        ]

    lines += [
        "---",
        "",
        "## Step 2: Book the Award Flight",
        "",
        f"**Program**: {flight.program_to_book.value}",
        f"**Miles required**: {flight.total_miles_required:,}",
        f"**Cash taxes/fees**: ${flight.cash_taxes_usd}",
        "",
        "### Outbound Segments",
    ]
    for seg in flight.outbound_segments:
        lines.append(f"- {seg.airline} {seg.flight_number}: {seg.origin} → {seg.destination}  {seg.departure_time[11:16]} → {seg.arrival_time[11:16]}")
    lines += ["", "### Return Segments"]
    for seg in flight.inbound_segments:
        lines.append(f"- {seg.airline} {seg.flight_number}: {seg.origin} → {seg.destination}  {seg.departure_time[11:16]} → {seg.arrival_time[11:16]}")

    award_url = _AWARD_BOOKING_URLS.get(flight.program_to_book.value, "https://your-airline.com/award")
    lines += [
        "",
        f"**Award booking URL**: {award_url}",
        "",
        "> 💡 Search by exact flight numbers if possible. Call the airline's award desk",
        "> if the website shows no availability — phone agents often see additional seats.",
        "",
        "---",
        "",
        "## Step 3: Book the Hotel",
        "",
        f"**Hotel**: {hotel.hotel_name}",
        f"**Program**: {hotel.program_to_book.value}",
        f"**Points**: {hotel.total_points_required:,}",
        f"**Dates**: {hotel.check_in} → {hotel.check_out}",
        "",
    ]

    hotel_url = _AWARD_BOOKING_URLS.get(hotel.program_to_book.value, "https://your-hotel-program.com")
    lines += [
        f"**Redemption URL**: {hotel_url}",
        "",
        "> 💡 Book the hotel AFTER confirming your flights — award hotel bookings are",
        "> generally more flexible (free cancellation up to 24h before check-in for most programs).",
        "",
        "---",
        "",
        "## Order of Operations Summary",
        "",
        "1. Initiate point transfers from issuer portals (Step 1).",
        "2. Wait for points to land in loyalty accounts (check email confirmations).",
        "3. Search and book award flights first (Step 2) — availability is limited.",
        "4. Book hotel award nights (Step 3).",
        "5. Pay cash taxes/fees on the flight with your best travel card.",
        "",
        "---",
        "",
        f"> Generated by Travel Points Planner | {plan.summary_label}",
    ]

    md = "\n".join(lines)
    console.print()
    console.print(Panel(Markdown(md), title="[bold green]Booking Guide[/bold green]", border_style="green"))
    return md


def save_booking_guide(md: str, path: str) -> None:
    """Save markdown booking guide to disk."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md, encoding="utf-8")
    console.print(f"\n[green]Booking guide saved to:[/green] {path}")
