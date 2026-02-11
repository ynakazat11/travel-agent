"""Transfer partner database: load JSON and look up transfer options."""

import json
from decimal import Decimal
from typing import Any

from travel_agent.config import settings
from travel_agent.models.points import (
    CurrencyProgram,
    Issuer,
    ISSUER_TO_PROGRAM,
    PointValuation,
    TransferPartner,
)


class TransferPartnerDB:
    def __init__(self) -> None:
        self._partners: list[TransferPartner] = []
        self._valuations: dict[CurrencyProgram, PointValuation] = {}
        self._load()

    def _load(self) -> None:
        with open(settings.transfer_partners_path) as f:
            data = json.load(f)
        for item in data["partners"]:
            self._partners.append(TransferPartner(**item))

        with open(settings.point_valuations_path) as f:
            val_data = json.load(f)
        for item in val_data["valuations"]:
            pv = PointValuation(
                program=CurrencyProgram(item["program"]),
                cpp=Decimal(item["cpp"]),
                source_date=item["source_date"],
            )
            self._valuations[pv.program] = pv

    def get_valuation(self, program: CurrencyProgram) -> PointValuation | None:
        return self._valuations.get(program)

    def partners_for_destination(
        self, destination: CurrencyProgram
    ) -> list[TransferPartner]:
        return [p for p in self._partners if p.destination_program == destination]

    def issuers_that_can_cover(
        self,
        destination_program: CurrencyProgram,
        points_needed: int,
        balances: dict[Issuer, int],
    ) -> list[dict[str, Any]]:
        """Return list of dicts with issuer, source_points_needed, and partner info."""
        results = []
        for partner in self.partners_for_destination(destination_program):
            # Find which issuer holds this source program
            issuer = _program_to_issuer(partner.source_program)
            if issuer is None:
                continue
            available = balances.get(issuer, 0)
            needed = partner.source_points_needed(points_needed)
            results.append(
                {
                    "issuer": issuer,
                    "source_program": partner.source_program,
                    "destination_program": destination_program,
                    "source_points_needed": needed,
                    "available_balance": available,
                    "can_cover": available >= needed,
                    "transfer_time_hours": partner.transfer_time_hours,
                    "ratio": f"{partner.ratio_from}:{partner.ratio_to}",
                    "bilt_differentiator": issuer == Issuer.bilt
                    and destination_program == CurrencyProgram.american_airlines_aadvantage,
                }
            )
        # Sort: coverable first, then by source points needed ascending
        results.sort(key=lambda r: (not r["can_cover"], r["source_points_needed"]))
        return results

    def all_partners_from_issuer(self, issuer: Issuer) -> list[TransferPartner]:
        source_program = ISSUER_TO_PROGRAM[issuer]
        return [p for p in self._partners if p.source_program == source_program]


def _program_to_issuer(program: CurrencyProgram) -> Issuer | None:
    for issuer, prog in ISSUER_TO_PROGRAM.items():
        if prog == program:
            return issuer
    return None
