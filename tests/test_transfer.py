"""Tests for TransferPartnerDB."""

from travel_agent.clients.transfer import TransferPartnerDB
from travel_agent.models.points import CurrencyProgram, Issuer


class TestTransferPartnerDB:
    def test_load_without_error(self, transfer_db: TransferPartnerDB) -> None:
        assert len(transfer_db._partners) > 0
        assert len(transfer_db._valuations) > 0

    def test_partners_for_destination_united(self, transfer_db: TransferPartnerDB) -> None:
        partners = transfer_db.partners_for_destination(CurrencyProgram.united_mileageplus)
        source_programs = {p.source_program for p in partners}
        # Both Chase UR and Bilt transfer to United
        assert CurrencyProgram.chase_ur in source_programs
        assert CurrencyProgram.bilt_rewards in source_programs

    def test_bilt_is_only_aa_partner(self, transfer_db: TransferPartnerDB) -> None:
        partners = transfer_db.partners_for_destination(CurrencyProgram.american_airlines_aadvantage)
        source_programs = {p.source_program for p in partners}
        # Only Bilt transfers to AA among the major issuers
        assert CurrencyProgram.bilt_rewards in source_programs
        assert CurrencyProgram.chase_ur not in source_programs
        assert CurrencyProgram.amex_mr not in source_programs
        assert CurrencyProgram.citi_ty not in source_programs
        assert CurrencyProgram.capital_one_miles not in source_programs

    def test_issuers_that_can_cover(self, transfer_db: TransferPartnerDB) -> None:
        balances = {
            Issuer.chase: 100_000,
            Issuer.amex: 80_000,
            Issuer.citi: 0,
            Issuer.capital_one: 0,
            Issuer.bilt: 30_000,
        }
        options = transfer_db.issuers_that_can_cover(
            CurrencyProgram.united_mileageplus, 30_000, balances
        )
        assert len(options) >= 2
        # Chase should appear first (coverable, 30k needed, has 100k)
        coverable = [o for o in options if o["can_cover"]]
        assert len(coverable) >= 2

    def test_valuation_for_world_of_hyatt(self, transfer_db: TransferPartnerDB) -> None:
        val = transfer_db.get_valuation(CurrencyProgram.world_of_hyatt)
        assert val is not None
        assert val.cpp > 2  # Hyatt is among the best hotel programs

    def test_bilt_differentiator_flagged(self, transfer_db: TransferPartnerDB) -> None:
        balances = {
            Issuer.bilt: 50_000,
            Issuer.chase: 0,
            Issuer.amex: 0,
            Issuer.citi: 0,
            Issuer.capital_one: 0,
        }
        options = transfer_db.issuers_that_can_cover(
            CurrencyProgram.american_airlines_aadvantage, 25_000, balances
        )
        bilt_opt = next((o for o in options if o["issuer"] == Issuer.bilt), None)
        assert bilt_opt is not None
        assert bilt_opt["bilt_differentiator"] is True

    def test_1_to_2_ratio_for_amex_hilton(self, transfer_db: TransferPartnerDB) -> None:
        partners = transfer_db.partners_for_destination(CurrencyProgram.hilton_honors)
        amex_partner = next(
            (p for p in partners if p.source_program == CurrencyProgram.amex_mr), None
        )
        assert amex_partner is not None
        assert amex_partner.ratio_from == 1
        assert amex_partner.ratio_to == 2
        # 40k Hilton = 20k Amex MR
        assert amex_partner.source_points_needed(40_000) == 20_000
