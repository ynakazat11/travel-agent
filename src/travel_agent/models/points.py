from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, field_validator


class Issuer(str, Enum):
    chase = "chase"
    amex = "amex"
    citi = "citi"
    capital_one = "capital_one"
    bilt = "bilt"


class CurrencyProgram(str, Enum):
    # Issuer currencies
    chase_ur = "chase_ur"
    amex_mr = "amex_mr"
    citi_ty = "citi_ty"
    capital_one_miles = "capital_one_miles"
    bilt_rewards = "bilt_rewards"

    # Airline programs
    united_mileageplus = "united_mileageplus"
    american_airlines_aadvantage = "american_airlines_aadvantage"
    delta_skymiles = "delta_skymiles"
    southwest_rapid_rewards = "southwest_rapid_rewards"
    alaska_mileage_plan = "alaska_mileage_plan"
    jetblue_trueblue = "jetblue_trueblue"
    british_airways_avios = "british_airways_avios"
    air_france_flying_blue = "air_france_flying_blue"
    air_canada_aeroplan = "air_canada_aeroplan"
    singapore_krisflyer = "singapore_krisflyer"
    emirates_skywards = "emirates_skywards"
    turkish_miles_smiles = "turkish_miles_smiles"
    virgin_atlantic_flying_club = "virgin_atlantic_flying_club"
    cathay_asia_miles = "cathay_asia_miles"
    avianca_lifemiles = "avianca_lifemiles"
    thai_airways_royal_orchid = "thai_airways_royal_orchid"

    # Hotel programs
    world_of_hyatt = "world_of_hyatt"
    marriott_bonvoy = "marriott_bonvoy"
    hilton_honors = "hilton_honors"
    ihg_rewards = "ihg_rewards"
    wyndham_rewards = "wyndham_rewards"
    choice_privileges = "choice_privileges"


ISSUER_TO_PROGRAM: dict[Issuer, CurrencyProgram] = {
    Issuer.chase: CurrencyProgram.chase_ur,
    Issuer.amex: CurrencyProgram.amex_mr,
    Issuer.citi: CurrencyProgram.citi_ty,
    Issuer.capital_one: CurrencyProgram.capital_one_miles,
    Issuer.bilt: CurrencyProgram.bilt_rewards,
}


class PointsBalance(BaseModel):
    issuer: Issuer
    program: CurrencyProgram
    balance: int

    @field_validator("balance")
    @classmethod
    def balance_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("balance must be >= 0")
        return v


class TransferPartner(BaseModel):
    source_program: CurrencyProgram
    destination_program: CurrencyProgram
    ratio_from: int
    ratio_to: int
    transfer_time_hours: int

    def source_points_needed(self, destination_points: int) -> int:
        """Compute source points required to obtain `destination_points`."""
        return int((destination_points * self.ratio_from + self.ratio_to - 1) // self.ratio_to)


class PointValuation(BaseModel):
    program: CurrencyProgram
    cpp: Decimal  # cents per point
    source_date: str
