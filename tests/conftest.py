"""Shared fixtures for travel-agent tests."""

import pytest

from travel_agent.clients.amadeus import AmadeusClient
from travel_agent.clients.transfer import TransferPartnerDB
from travel_agent.models.points import Issuer, PointsBalance, ISSUER_TO_PROGRAM


@pytest.fixture
def mock_amadeus() -> AmadeusClient:
    return AmadeusClient(mock=True)


@pytest.fixture
def transfer_db() -> TransferPartnerDB:
    return TransferPartnerDB()


@pytest.fixture
def sample_balances() -> list[PointsBalance]:
    return [
        PointsBalance(issuer=Issuer.chase, program=ISSUER_TO_PROGRAM[Issuer.chase], balance=100_000),
        PointsBalance(issuer=Issuer.amex, program=ISSUER_TO_PROGRAM[Issuer.amex], balance=80_000),
        PointsBalance(issuer=Issuer.citi, program=ISSUER_TO_PROGRAM[Issuer.citi], balance=50_000),
        PointsBalance(issuer=Issuer.capital_one, program=ISSUER_TO_PROGRAM[Issuer.capital_one], balance=60_000),
        PointsBalance(issuer=Issuer.bilt, program=ISSUER_TO_PROGRAM[Issuer.bilt], balance=30_000),
    ]
