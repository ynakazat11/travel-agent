from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from travel_agent.models.points import PointsBalance
from travel_agent.models.preferences import TravelPreferences
from travel_agent.models.travel import TripPlan


class SessionPhase(str, Enum):
    POINTS_INPUT = "POINTS_INPUT"
    PREFERENCE_GATHERING = "PREFERENCE_GATHERING"
    SEARCHING = "SEARCHING"
    OPTIONS_PRESENTED = "OPTIONS_PRESENTED"
    FINE_TUNING = "FINE_TUNING"
    FINALIZING = "FINALIZING"
    COMPLETE = "COMPLETE"


class FineTuneState(BaseModel):
    active: bool = False
    target_plan_index: int = 0
    pending_alternative_flights: list[Any] = Field(default_factory=list)
    pending_alternative_hotels: list[Any] = Field(default_factory=list)


class ConversationSession(BaseModel):
    phase: SessionPhase = SessionPhase.POINTS_INPUT
    points_balances: list[PointsBalance] = Field(default_factory=list)
    preferences: TravelPreferences = Field(default_factory=TravelPreferences)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    current_trip_plans: list[TripPlan] = Field(default_factory=list)
    selected_plan: TripPlan | None = None
    fine_tune_state: FineTuneState = Field(default_factory=FineTuneState)

    def add_message(self, role: str, content: Any) -> None:
        self.conversation_history.append({"role": role, "content": content})

    def advance_phase(self, next_phase: SessionPhase) -> None:
        self.phase = next_phase

    def prune_search_history(self) -> None:
        """Replace raw tool call exchanges with a compact summary after SEARCHING."""
        summary = {
            "role": "user",
            "content": (
                "[Search phase complete. "
                f"{len(self.current_trip_plans)} trip plan(s) assembled. "
                "Full search tool history pruned for context efficiency.]"
            ),
        }
        self.conversation_history = [
            m for m in self.conversation_history
            if not _is_search_tool_exchange(m)
        ]
        self.conversation_history.append(summary)


def _is_search_tool_exchange(message: dict[str, Any]) -> bool:
    content = message.get("content", "")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("tool_use", "tool_result"):
                return True
    return False
