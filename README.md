# Travel Points Planner

A CLI-based agentic travel planner that optimizes award trips across your credit card points portfolios. Powered by [Claude](https://anthropic.com) for conversation and [Amadeus](https://developers.amadeus.com) for flight and hotel search.

> ⚠️ **Never commit your `.env` file.** API keys give access to paid services.

---

## Features

- **Natural conversation** — tell Claude where you want to go; it gathers the rest
- **All 5 major currencies** — Chase UR, Amex MR, Citi TY, Capital One Miles, Bilt Rewards
- **Transfer math** — computes exact source points needed per transfer ratio
- **Bilt → AA differentiator** — surfaces Bilt Rewards as the only issuer with a 1:1 American Airlines transfer
- **CPP rankings** — blended cents-per-point across flight + hotel for every plan
- **Fine-tuning** — swap flights, swap hotels, change cabin, adjust dates
- **Booking guide** — step-by-step transfer and redemption instructions, saveable to `~/Downloads/`
- **Rich terminal UI** — tables, panels, spinners throughout
- **`--mock` mode** — full flow with fixture data, no API keys required

---

## Quickstart

```bash
git clone https://github.com/ynakazat11/travel-agent.git
cd travel-agent
cp .env.example .env   # fill in your keys
./run.sh
```

`run.sh` auto-creates a virtualenv and installs dependencies on first run. All CLI args are forwarded.

### Mock mode (no API keys needed)

```bash
./run.sh --mock
```

---

## Setup

### 1. API Keys

| Key | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `AMADEUS_CLIENT_ID` | [developers.amadeus.com](https://developers.amadeus.com) — free sandbox |
| `AMADEUS_CLIENT_SECRET` | same as above |

```bash
cp .env.example .env
# edit .env with your values
```

### 2. Manual install (optional)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m travel_agent.main --mock
```

---

## How it works

The app runs a 7-phase conversation state machine:

```
POINTS_INPUT        Rich prompts collect balances for all 5 issuers
       ↓
PREFERENCE_GATHERING  Claude gathers destination, dates, travelers, preferences
       ↓
SEARCHING           Claude autonomously chains tools: resolve → flights → hotels
                    → transfer lookup → trip cost (3–5 plans assembled)
       ↓
OPTIONS_PRESENTED   Rich table compares plans by CPP, points, cash taxes
       ↓
FINE_TUNING         Swap flights or hotels; Claude fetches alternatives
       ↓
FINALIZING          Selected plan displayed with full CPP breakdown
       ↓
COMPLETE            Booking guide rendered; optionally saved to ~/Downloads/
```

### Claude Tools

| Tool | Purpose |
|---|---|
| `resolve_destination` | Vague description → IATA codes |
| `search_flights` | Amadeus flight offers |
| `search_hotels` | Amadeus hotel offers (2-step: city → offers) |
| `lookup_transfer_options` | Which issuers can cover a program + points needed |
| `calculate_trip_cost` | Assemble TripPlan with CPP breakdown |
| `get_alternative_flights` | Fine-tune: filtered flight alternatives |
| `get_alternative_hotels` | Fine-tune: filtered hotel alternatives |
| `mark_preferences_complete` | Signal preference gathering is done → triggers search |

---

## Project structure

```
travel-agent/
├── run.sh                          # Entry point
├── .env.example                    # Key placeholders (safe to commit)
├── data/
│   ├── transfer_partners.json      # 51 transfer partner relationships
│   └── point_valuations.json       # TPG CPP valuations (27 programs)
└── src/travel_agent/
    ├── config.py                   # pydantic-settings — single env var source
    ├── main.py                     # CLI state machine
    ├── models/                     # Pydantic models
    ├── agent/                      # Claude loop, tools, prompts
    ├── clients/                    # Amadeus API + transfer partner DB
    └── display/                    # Rich tables, prompts, booking guide
```

---

## Development

```bash
# Run tests
.venv/bin/pytest -x -q tests/

# Type check
.venv/bin/mypy src/
```

40 tests, mypy strict, Python 3.11+.

---

## Transfer partners

| Issuer | Notable partners |
|---|---|
| Chase UR | United, Hyatt, British Airways, Air France, Singapore, Emirates |
| Amex MR | Delta, British Airways, Air France, Hilton (1:2), Marriott, Air Canada |
| Citi TY | Turkish, Singapore, Air France, Emirates, JetBlue, Avianca |
| Capital One | Air Canada, Turkish, British Airways, Air France, Avianca |
| Bilt Rewards | **American Airlines (1:1 — unique)**, United, Hyatt, Alaska, Air Canada, + more |

---

## Security notes

- `.env` is in `.gitignore` — never committed
- All secrets flow through `config.py` (pydantic-settings) — no scattered `os.getenv()` calls
- Points balances are in-memory only — never written to disk
- Booking guides save to `~/Downloads/` — outside the repo directory
- Amadeus sandbox is free; use sandbox credentials only in `.env`
