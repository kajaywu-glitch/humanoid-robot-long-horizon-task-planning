from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..models import GaitParams, PlanDecision, Stage, SubStage
from .gait import PosturePrimitive, RecoveryPrimitive, SinusoidalGait


def _joint_count(agent_params: Mapping[str, Any], key: str, default: int) -> int:
    indices = agent_params.get(key)
    if isinstance(indices, Sequence) and not isinstance(indices, (str, bytes)):
        return len(indices)
    return default


# ---------------------------------------------------------------------------
# Per-stage gait parameter overrides (heuristic — calibrate in Docker)
# ---------------------------------------------------------------------------

_FLAT_GAIT = GaitParams(
    frequency=1.8,
    step_length=0.35,
    step_height=0.12,
    body_height_offset=0.0,
    forward_lean=0.02,
)

_STAIR_GAIT = GaitParams(
    frequency=1.0,
    step_length=0.25,
    step_height=0.22,
    body_height_offset=0.05,
    forward_lean=0.10,
    double_support_ratio=0.15,
)

_SLOPE_GAIT = GaitParams(
    frequency=1.2,
    step_length=0.20,
    step_height=0.12,
    body_height_offset=-0.03,
    forward_lean=-0.08,
    double_support_ratio=0.12,
)

_UNEVEN_GAIT = GaitParams(
    frequency=1.0,
    step_length=0.18,
    step_height=0.18,
    body_height_offset=0.03,
    lateral_swing=0.08,
    double_support_ratio=0.15,
)

# Which sub-stages use which gait
_STAIR_SUBSTAGES = {SubStage.CLIMBING_STAIRS}
_SLOPE_SUBSTAGES = {SubStage.DESCENDING_SLOPE}
_UNEVEN_SUBSTAGES = {SubStage.CROSSING_UNEVEN}


class ActionFactory:
    """Builds validated Tongverse action dicts from planner decisions.

    In **safe mode** (default) every decision produces a validated neutral
    (zero-vector) action regardless of stage or sub-stage.  This is the
    required baseline until joint indices, control modes, pick semantics,
    and observation fields are confirmed against the real Docker environment.

    When ``safe_mode=False`` the factory delegates to :class:`SinusoidalGait`,
    :class:`PosturePrimitive`, and :class:`RecoveryPrimitive`.  Those code
    paths remain available for experimental branches but MUST NOT run on
    ``main`` without explicit approval.
    """

    def __init__(
        self,
        agent_params: Mapping[str, Any] | None = None,
        *,
        safe_mode: bool = True,
    ) -> None:
        params = agent_params if isinstance(agent_params, Mapping) else {}
        self._arm_count = _joint_count(params, "arm_idx", 14)
        self._leg_count = _joint_count(params, "leg_idx", 12)
        self._head_count = _joint_count(params, "head_idx", 2)
        self._safe_mode = safe_mode

        # Experimental primitives — initialised but NOT used in safe mode.
        self._gait = SinusoidalGait(
            params=_FLAT_GAIT,
            leg_count=self._leg_count,
            arm_count=self._arm_count,
        )
        self._posture = PosturePrimitive(
            leg_count=self._leg_count,
            arm_count=self._arm_count,
        )
        self._recovery = RecoveryPrimitive(
            arm_count=self._arm_count,
            leg_count=self._leg_count,
        )

        self._step_index: int = 0
        self._dt: float = 0.02  # estimated control period (s)
        self._in_recovery: bool = False  # tracks recovery entry for reset

    # ------------------------------------------------------------------
    # public entry point
    # ------------------------------------------------------------------

    def for_decision(self, decision: PlanDecision, task_id: str | None) -> dict[str, Any]:
        self._step_index += 1

        # --- safe mode: always neutral ---------------------------------
        if self._safe_mode:
            return self._neutral_action(decision, task_id)

        # --- experimental paths (guarded by safe_mode=False) -----------

        # Reset recovery primitive on new recovery entry
        entering_recovery = decision.needs_recovery or decision.sub_stage == SubStage.FALL_RECOVERY
        if entering_recovery and not self._in_recovery:
            self._recovery.reset()
            self._in_recovery = True
        elif not entering_recovery:
            self._in_recovery = False

        if entering_recovery:
            return self._recovery_action()

        if decision.stage == Stage.NAVIGATE_TERRAIN:
            return self._terrain_action(decision)
        if decision.stage in (Stage.SORT_PARTS, Stage.MOVE_BOX_TO_SHELF):
            return self._manipulation_action(decision)

        return self._neutral_action(decision, task_id)

    # ------------------------------------------------------------------
    # terrain
    # ------------------------------------------------------------------

    def _terrain_action(self, decision: PlanDecision) -> dict[str, Any]:
        sub = decision.sub_stage

        # pick gait variant
        if sub in _STAIR_SUBSTAGES:
            self._gait.params = _STAIR_GAIT
            arm_vals, leg_vals = self._gait.tick_stairs(self._dt)
        elif sub in _SLOPE_SUBSTAGES:
            self._gait.params = _SLOPE_GAIT
            arm_vals, leg_vals = self._gait.tick_slope_down(self._dt)
        elif sub in _UNEVEN_SUBSTAGES:
            self._gait.params = _UNEVEN_GAIT
            arm_vals, leg_vals = self._gait.tick_uneven(self._dt)
        else:
            self._gait.params = _FLAT_GAIT
            arm_vals, leg_vals = self._gait.tick_flat(self._dt)

        action = self._make_action("position", arm_vals, leg_vals, ctrl_mode_legs="position")
        validate_action(action, self._arm_count, self._leg_count, self._head_count)
        return action

    # ------------------------------------------------------------------
    # manipulation (sort / box)
    # ------------------------------------------------------------------

    def _manipulation_action(self, decision: PlanDecision) -> dict[str, Any]:
        arm_vals, leg_vals = self._posture.stand()
        sub = decision.sub_stage

        # Arm targets for approaching objects
        if sub in (SubStage.APPROACH_PART, SubStage.GRASP_PART, SubStage.APPROACH_BOX):
            arm_vals = self._posture.arms_forward(0.6)
        elif sub == SubStage.LIFT_BOX:
            # arms forward and slightly up for lifting
            arm_vals = self._posture.arms_forward(0.4)
            for i in range(len(arm_vals)):
                arm_vals[i] += 0.1  # slight upward offset

        action = self._make_action("position", arm_vals, leg_vals, ctrl_mode_legs="position")

        # pick / release flags — always present for manipulation stages
        if sub == SubStage.GRASP_PART:
            action["pick"] = "right_hand"
        elif sub == SubStage.RELEASE_PART:
            action["pick"] = None
        else:
            action["pick"] = None  # neutral pick for all other manipulation sub-stages

        validate_action(action, self._arm_count, self._leg_count, self._head_count)
        return action

    # ------------------------------------------------------------------
    # recovery
    # ------------------------------------------------------------------

    def _recovery_action(self) -> dict[str, Any]:
        arm_vals, leg_vals = self._recovery.tick(self._dt)
        action = self._make_action("position", arm_vals, leg_vals, ctrl_mode_legs="position")
        validate_action(action, self._arm_count, self._leg_count, self._head_count)
        return action

    # ------------------------------------------------------------------
    # neutral (fallback)
    # ------------------------------------------------------------------

    def _neutral_action(self, decision: PlanDecision, task_id: str | None) -> dict[str, Any]:
        action = {
            "arms": {
                "ctrl_mode": "position",
                "joint_values": [0.0] * self._arm_count,
                "stiffness": self._default_arm_stiffness(),
                "dampings": [0.0] * self._arm_count,
            },
            "legs": {
                "ctrl_mode": "effort",
                "joint_values": [0.0] * self._leg_count,
                "stiffness": None,
                "dampings": None,
            },
            "head": {
                "ctrl_mode": "position",
                "joint_values": [0.0] * self._head_count,
                "stiffness": None,
                "dampings": None,
            },
        }

        if task_id in ("TaskTwo", "TaskThree") or decision.stage in (
            Stage.SORT_PARTS,
            Stage.MOVE_BOX_TO_SHELF,
        ):
            action["pick"] = None

        validate_action(action, self._arm_count, self._leg_count, self._head_count)
        return action

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_action(
        self,
        ctrl_mode_arms: str,
        arm_values: list[float],
        leg_values: list[float],
        ctrl_mode_legs: str = "effort",
    ) -> dict[str, Any]:
        return {
            "arms": {
                "ctrl_mode": ctrl_mode_arms,
                "joint_values": list(arm_values),
                "stiffness": self._default_arm_stiffness(),
                "dampings": [0.0] * self._arm_count,
            },
            "legs": {
                "ctrl_mode": ctrl_mode_legs,
                "joint_values": list(leg_values),
                "stiffness": None,
                "dampings": None,
            },
            "head": {
                "ctrl_mode": "position",
                "joint_values": [0.0] * self._head_count,
                "stiffness": None,
                "dampings": None,
            },
        }

    def _default_arm_stiffness(self) -> list[float]:
        values = [0.0] * self._arm_count
        for index in (0, 4, 8):
            if index < self._arm_count:
                values[index] = 50.0
        return values


# ---------------------------------------------------------------------------
# validation (unchanged public API)
# ---------------------------------------------------------------------------


def validate_action(
    action: Mapping[str, Any],
    arm_count: int = 14,
    leg_count: int = 12,
    head_count: int = 2,
) -> None:
    expected = {"arms": arm_count, "legs": leg_count, "head": head_count}
    valid_modes = {"position", "velocity", "effort"}

    for group, count in expected.items():
        command = action.get(group)
        if not isinstance(command, Mapping):
            raise ValueError(f"missing action group: {group}")
        if command.get("ctrl_mode") not in valid_modes:
            raise ValueError(f"invalid ctrl_mode for {group}")

        values = command.get("joint_values")
        if values is not None and len(values) != count:
            raise ValueError(f"{group}.joint_values must contain {count} values")

        for optional_key in ("stiffness", "dampings"):
            optional_values = command.get(optional_key)
            if optional_values is not None and len(optional_values) != count:
                raise ValueError(f"{group}.{optional_key} must contain {count} values")

    if "pick" in action and action["pick"] not in (None, "left_hand", "right_hand"):
        raise ValueError("pick must be None, left_hand, or right_hand")
