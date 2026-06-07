from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .control.actions import ActionFactory
from .models import Stage
from .perception.scene import ObservationParser
from .planner.fsm import LongHorizonPlanner
from .telemetry import Telemetry

LOGGER = logging.getLogger(__name__)


class TaskSolver:
    """Official entry point for the Tongverse challenge.

    Instantiated once per episode with *task_params* and *agent_params*.
    Each simulation step calls :meth:`next_action` with the current
    observation dict, which returns a validated action dict.
    """

    def __init__(self, task_params: Mapping[str, Any], agent_params: Mapping[str, Any]) -> None:
        self.task_params = dict(task_params or {})
        self.agent_params = dict(agent_params or {})
        self._telemetry = Telemetry()
        self._parser = ObservationParser()
        self._planner = LongHorizonPlanner(on_transition=self._telemetry.record_transition)
        self._actions = ActionFactory(self.agent_params)

    # ------------------------------------------------------------------
    # public properties
    # ------------------------------------------------------------------

    @property
    def current_stage(self) -> Stage:
        return self._planner.stage

    @property
    def current_sub_stage(self) -> str:
        return self._planner.sub_stage.value

    @property
    def telemetry(self) -> Telemetry:
        return self._telemetry

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------

    def next_action(self, obs: dict) -> dict:
        try:
            snapshot = self._parser.parse(obs)
        except Exception:
            LOGGER.exception("observation parse failed")
            self._telemetry.record_error("parse", "observation parse failure", {"obs_keys": list(obs) if isinstance(obs, dict) else []})
            # Return a safe neutral action on parse failure
            return self._neutral_fallback()

        decision = self._planner.tick(snapshot)

        try:
            action = self._actions.for_decision(decision, snapshot.task_id)
        except Exception:
            LOGGER.exception("action construction failed")
            self._telemetry.record_error(
                "action",
                "action construction failure",
                {"stage": decision.stage.value, "sub_stage": decision.sub_stage.value},
            )
            return self._neutral_fallback()

        # telemetry
        pick_val = action.get("pick") if isinstance(action, dict) else None
        self._telemetry.record_action(
            decision=decision,
            joint_count=len(action.get("arms", {}).get("joint_values", [])),
            pick_command=str(pick_val) if pick_val else None,
            fall_detected=snapshot.is_fallen,
            elapsed_minutes=snapshot.elapsed_minutes,
        )

        if snapshot.is_fallen:
            self._telemetry.record_fall(
                sub_stage=decision.sub_stage.value,
                elapsed_minutes=snapshot.elapsed_minutes,
            )

        return action

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _neutral_fallback(self) -> dict:
        """Return a safe zero-vector action when normal processing fails."""
        from .control.actions import validate_action

        arm_count = len(self.agent_params.get("arm_idx", [0] * 14))
        leg_count = len(self.agent_params.get("leg_idx", [0] * 12))
        head_count = len(self.agent_params.get("head_idx", [0] * 2))

        action = {
            "arms": {
                "ctrl_mode": "position",
                "joint_values": [0.0] * arm_count,
                "stiffness": [0.0] * arm_count,
                "dampings": [0.0] * arm_count,
            },
            "legs": {
                "ctrl_mode": "effort",
                "joint_values": [0.0] * leg_count,
                "stiffness": None,
                "dampings": None,
            },
            "head": {
                "ctrl_mode": "position",
                "joint_values": [0.0] * head_count,
                "stiffness": None,
                "dampings": None,
            },
        }
        validate_action(action, arm_count, leg_count, head_count)
        return action
