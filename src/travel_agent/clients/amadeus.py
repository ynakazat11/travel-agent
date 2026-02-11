"""Amadeus API client with OAuth2 token management and flight/hotel search."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from travel_agent.config import settings
from travel_agent.models.points import CurrencyProgram, Issuer
from travel_agent.models.travel import FlightOption, FlightSegment, HotelOption


_AMADEUS_AUTH_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
_AMADEUS_BASE_URL = "https://test.api.amadeus.com"


@dataclass
class _TokenCache:
    access_token: str = ""
    expires_at: float = 0.0


class AmadeusClient:
    def __init__(self, mock: bool = False) -> None:
        self._mock = mock
        self._token_cache = _TokenCache()
        self._http = httpx.Client(timeout=30.0)

    def _ensure_token(self) -> str:
        if self._mock:
            return "mock-token"
        if self._token_cache.access_token and time.time() < self._token_cache.expires_at - 60:
            return self._token_cache.access_token
        resp = self._http.post(
            _AMADEUS_AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.amadeus_client_id,
                "client_secret": settings.amadeus_client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token_cache.access_token = data["access_token"]
        self._token_cache.expires_at = time.time() + data.get("expires_in", 1800)
        return self._token_cache.access_token

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        token = self._ensure_token()
        resp = self._http.get(
            f"{_AMADEUS_BASE_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str,
        num_travelers: int = 1,
        currency: str = "USD",
        max_results: int = 5,
    ) -> list[FlightOption]:
        if self._mock:
            return _mock_flight_options(origin, destination, departure_date, return_date)

        params: dict[str, Any] = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "returnDate": return_date,
            "adults": num_travelers,
            "currencyCode": currency,
            "max": max_results,
            "nonStop": "false",
        }
        data = self._get("/v2/shopping/flight-offers", params)
        return _parse_flight_offers(data.get("data", []))

    def search_flights_parallel(
        self,
        origin: str,
        destination: str,
        dates: list[tuple[str, str]],
        num_travelers: int = 1,
    ) -> list[FlightOption]:
        results: list[FlightOption] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(
                    self.search_flights, origin, destination, dep, ret, num_travelers
                ): (dep, ret)
                for dep, ret in dates
            }
            for fut in as_completed(futures):
                try:
                    results.extend(fut.result())
                except Exception:
                    pass
        return results

    def search_hotels(
        self,
        city_code: str,
        check_in: str,
        check_out: str,
        num_travelers: int = 1,
        max_results: int = 5,
    ) -> list[HotelOption]:
        if self._mock:
            return _mock_hotel_options(city_code, check_in, check_out)

        # Step 1: get hotel IDs for city
        hotel_data = self._get(
            "/v1/reference-data/locations/hotels/by-city",
            {"cityCode": city_code, "radius": 20, "radiusUnit": "KM"},
        )
        hotel_ids = [h["hotelId"] for h in hotel_data.get("data", [])[:20]]
        if not hotel_ids:
            return []

        # Step 2: get offers for those hotels
        offers_data = self._get(
            "/v3/shopping/hotel-offers",
            {
                "hotelIds": ",".join(hotel_ids),
                "checkInDate": check_in,
                "checkOutDate": check_out,
                "adults": num_travelers,
                "currency": "USD",
                "bestRateOnly": "true",
            },
        )
        return _parse_hotel_offers(offers_data.get("data", [])[:max_results])

    def close(self) -> None:
        self._http.close()


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_flight_offers(offers: list[dict[str, Any]]) -> list[FlightOption]:
    results: list[FlightOption] = []
    for offer in offers:
        try:
            itineraries = offer.get("itineraries", [])
            if len(itineraries) < 2:
                continue
            outbound = _parse_segments(itineraries[0].get("segments", []))
            inbound = _parse_segments(itineraries[1].get("segments", []))
            price = offer.get("price", {})
            taxes_usd = Decimal(price.get("fees", [{"amount": "0"}])[0].get("amount", "0"))
            total = Decimal(price.get("total", "0"))
            results.append(
                FlightOption(
                    outbound_segments=outbound,
                    inbound_segments=inbound,
                    total_miles_required=int(total * 100),  # approximate; real award pricing differs
                    program_to_book=CurrencyProgram.united_mileageplus,
                    source_issuer=Issuer.chase,
                    cash_taxes_usd=taxes_usd,
                    amadeus_offer_id=offer.get("id", ""),
                )
            )
        except Exception:
            continue
    return results


def _parse_segments(segments: list[dict[str, Any]]) -> list[FlightSegment]:
    result = []
    for s in segments:
        dep = s.get("departure", {})
        arr = s.get("arrival", {})
        carrier = s.get("carrierCode", "")
        result.append(
            FlightSegment(
                origin=dep.get("iataCode", ""),
                destination=arr.get("iataCode", ""),
                departure_time=dep.get("at", ""),
                arrival_time=arr.get("at", ""),
                airline=carrier,
                flight_number=f"{carrier}{s.get('number', '')}",
            )
        )
    return result


def _parse_hotel_offers(offers: list[dict[str, Any]]) -> list[HotelOption]:
    results: list[HotelOption] = []
    for offer in offers:
        try:
            hotel = offer.get("hotel", {})
            room_offers = offer.get("offers", [{}])
            price = room_offers[0].get("price", {}) if room_offers else {}
            total = int(float(price.get("total", "0")) * 100)  # approx points
            results.append(
                HotelOption(
                    hotel_name=hotel.get("name", "Unknown Hotel"),
                    hotel_chain=hotel.get("chainCode", ""),
                    star_rating=float(hotel.get("rating", 3)),
                    check_in=room_offers[0].get("checkInDate", "") if room_offers else "",
                    check_out=room_offers[0].get("checkOutDate", "") if room_offers else "",
                    total_points_required=total,
                    program_to_book=CurrencyProgram.world_of_hyatt,
                    source_issuer=Issuer.chase,
                    amadeus_hotel_id=hotel.get("hotelId", ""),
                )
            )
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# Mock data for --mock mode
# ---------------------------------------------------------------------------

def _mock_flight_options(
    origin: str, destination: str, departure_date: str, return_date: str
) -> list[FlightOption]:
    airline_programs = [
        (CurrencyProgram.united_mileageplus, Issuer.chase, "UA", 30000),
        (CurrencyProgram.american_airlines_aadvantage, Issuer.bilt, "AA", 25000),
        (CurrencyProgram.air_france_flying_blue, Issuer.amex, "AF", 27500),
    ]
    options = []
    for program, issuer, code, miles in airline_programs:
        options.append(
            FlightOption(
                outbound_segments=[
                    FlightSegment(
                        origin=origin,
                        destination=destination,
                        departure_time=f"{departure_date}T08:00:00",
                        arrival_time=f"{departure_date}T14:00:00",
                        airline=code,
                        flight_number=f"{code}101",
                    )
                ],
                inbound_segments=[
                    FlightSegment(
                        origin=destination,
                        destination=origin,
                        departure_time=f"{return_date}T15:00:00",
                        arrival_time=f"{return_date}T21:00:00",
                        airline=code,
                        flight_number=f"{code}102",
                    )
                ],
                total_miles_required=miles,
                program_to_book=program,
                source_issuer=issuer,
                transfer_partner_used=program.value,
                cash_taxes_usd=Decimal("11.20"),
                amadeus_offer_id=f"mock-{code}-{departure_date}",
            )
        )
    return options


def _mock_hotel_options(city_code: str, check_in: str, check_out: str) -> list[HotelOption]:
    hotels = [
        ("Grand Hyatt", "Park Hyatt", CurrencyProgram.world_of_hyatt, Issuer.chase, 4.5, 20000),
        ("Hilton Garden Inn", "Hilton", CurrencyProgram.hilton_honors, Issuer.amex, 3.5, 40000),
        ("Marriott Waikiki", "Marriott", CurrencyProgram.marriott_bonvoy, Issuer.amex, 4.0, 35000),
    ]
    options = []
    for name, chain, program, issuer, stars, points in hotels:
        options.append(
            HotelOption(
                hotel_name=name,
                hotel_chain=chain,
                star_rating=stars,
                check_in=check_in,
                check_out=check_out,
                total_points_required=points,
                program_to_book=program,
                source_issuer=issuer,
                amadeus_hotel_id=f"mock-{name.lower().replace(' ', '-')}",
            )
        )
    return options
