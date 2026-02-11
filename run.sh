#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/.venv"
PYTHON="$VENV/bin/python"

# Bootstrap venv if it doesn't exist
if [[ ! -x "$PYTHON" ]]; then
  echo "Setting up virtual environment..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -e ".[dev]"
  echo "Done."
fi

# Check for .env (skip warning in mock mode)
if [[ ! -f "$SCRIPT_DIR/.env" ]] && [[ "${1:-}" != "--mock" ]]; then
  echo "Warning: no .env file found. Copy .env.example to .env and fill in your API keys."
  echo "         Or run with --mock to use fixture data: ./run.sh --mock"
fi

exec "$PYTHON" -m travel_agent.main "$@"
