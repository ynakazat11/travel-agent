from decimal import Decimal

from pydantic import BaseModel, computed_field

from travel_agent.models.points import CurrencyProgram, Issuer


class FlightSegment(BaseModel):
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    airline: str
    flight_number: str


class FlightOption(BaseModel):
    outbound_segments: list[FlightSegment]
    inbound_segments: list[FlightSegment]
    total_miles_required: int
    program_to_book: CurrencyProgram
    source_issuer: Issuer
    transfer_partner_used: str = ""
    cash_taxes_usd: Decimal = Decimal("0")
    amadeus_offer_id: str = ""


class HotelOption(BaseModel):
    hotel_name: str
    hotel_chain: str = ""
    star_rating: float = 3.0
    check_in: str
    check_out: str
    total_points_required: int
    program_to_book: CurrencyProgram
    source_issuer: Issuer
    amadeus_hotel_id: str = ""


class PointsCostBreakdown(BaseModel):
    issuer: Issuer
    program: CurrencyProgram
    points_used: int
    cpp: Decimal  # base valuation cents per point

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cash_value_usd(self) -> Decimal:
        return (self.cpp * self.points_used / 100).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_cpp(self) -> Decimal:
        if self.points_used == 0:
            return Decimal("0")
        return (self.cash_value_usd * 100 / self.points_used).quantize(Decimal("0.001"))


class TripPlan(BaseModel):
    flight: FlightOption
    hotel: HotelOption
    points_breakdown: list[PointsCostBreakdown]
    total_cash_usd: Decimal = Decimal("0")
    summary_label: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def blended_cpp(self) -> Decimal:
        total_points = sum(b.points_used for b in self.points_breakdown)
        total_value = sum(b.cash_value_usd for b in self.points_breakdown)
        if total_points == 0:
            return Decimal("0")
        return (Decimal(total_value) * 100 / total_points).quantize(Decimal("0.001"))
