"""Structured telemetry for the task-solver pipeline.

Every significant event — state transition, action emission, error, or
recovery — is recorded as a lightweight dict that can be serialised to
JSON or emitted through ``logging``.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping

from .models import PlanDecision, Stage, SubStage

LOGGER = logging.getLogger(__name__)


class Telemetry:
    """Collect and emit structured telemetry records."""

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []
        self._action_index: int = 0
        self._start_wall: float = time.monotonic()

    # ------------------------------------------------------------------
    # recording API
    # ------------------------------------------------------------------

    def record_transition(
        self,
        previous: Stage,
        target: Stage,
        reason: str,
    ) -> None:
        self._records.append({
            "type": "transition",
            "action_index": self._action_index,
            "wall_seconds": time.monotonic() - self._start_wall,
            "previous": previous.value,
            "target": target.value,
            "reason": reason,
        })
        LOGGER.info(
            "planner_transition previous=%s target=%s reason=%s",
            previous.value,
            target.value,
            reason,
        )

    def record_action(
        self,
        decision: PlanDecision,
        joint_count: int,
        pick_command: str | None,
        fall_detected: bool,
        elapsed_minutes: float,
    ) -> None:
        self._action_index += 1
        self._records.append({
            "type": "action",
            "action_index": self._action_index,
            "wall_seconds": time.monotonic() - self._start_wall,
            "elapsed_minutes": elapsed_minutes,
            "stage": decision.stage.value,
            "sub_stage": decision.sub_stage.value,
            "reason": decision.reason,
            "joint_count": joint_count,
            "pick": pick_command,
            "fall_detected": fall_detected,
            "needs_recovery": decision.needs_recovery,
            "retry_count": decision.retry_count,
        })

    def record_error(
        self,
        error_type: str,
        message: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        entry = {
            "type": "error",
            "action_index": self._action_index,
            "wall_seconds": time.monotonic() - self._start_wall,
            "error_type": error_type,
            "message": message,
        }
        if context:
            entry["context"] = dict(context)
        self._records.append(entry)
        LOGGER.warning("telemetry_error type=%s message=%s", error_type, message)

    def record_fall(self, sub_stage: str, elapsed_minutes: float) -> None:
        self._records.append({
            "type": "fall",
            "action_index": self._action_index,
            "wall_seconds": time.monotonic() - self._start_wall,
            "elapsed_minutes": elapsed_minutes,
            "sub_stage": sub_stage,
        })
        LOGGER.warning("fall_detected sub_stage=%s elapsed=%.2f", sub_stage, elapsed_minutes)

    def record_recovery(self, success: bool, retry_count: int) -> None:
        self._records.append({
            "type": "recovery",
            "action_index": self._action_index,
            "wall_seconds": time.monotonic() - self._start_wall,
            "success": success,
            "retry_count": retry_count,
        })

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------

    @property
    def action_index(self) -> int:
        return self._action_index

    @property
    def records(self) -> list[dict[str, Any]]:
        return list(self._records)

    def recent(self, n: int = 10) -> list[dict[str, Any]]:
        return self._records[-n:] if self._records else []

    def counts_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._records:
            t = r.get("type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self._records.clear()
        self._action_index = 0
        self._start_wall = time.monotonic()
