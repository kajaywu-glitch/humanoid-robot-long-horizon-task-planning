from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Mapping

from ..models import (
    PlanDecision,
    SceneSnapshot,
    Stage,
    SubStage,
    TerrainType,
)

LOGGER = logging.getLogger(__name__)

TransitionListener = Callable[[Stage, Stage, str], None]


# ---------------------------------------------------------------------------
# Per-stage sub-state chains (ordered)
# ---------------------------------------------------------------------------

_TERRAIN_CHAIN = (
    SubStage.TERRAIN_START,
    SubStage.APPROACH_STAIRS,
    SubStage.CLIMBING_STAIRS,
    SubStage.POST_STAIRS_TRANSITION,
    SubStage.APPROACH_DOWNHILL,
    SubStage.DESCENDING_SLOPE,
    SubStage.POST_SLOPE_TRANSITION,
    SubStage.CROSSING_UNEVEN,
    SubStage.TERRAIN_COMPLETE,
)

_SORT_CHAIN = (
    SubStage.SORT_START,
    SubStage.SCAN_WORKSPACE,
    SubStage.IDENTIFY_TARGET,
    SubStage.APPROACH_PART,
    SubStage.GRASP_PART,
    SubStage.VERIFY_GRASP,
    SubStage.MOVE_TO_BOX,
    SubStage.RELEASE_PART,
    SubStage.SORT_COMPLETE,
)

_BOX_CHAIN = (
    SubStage.BOX_START,
    SubStage.APPROACH_BOX,
    SubStage.LIFT_BOX,
    SubStage.NAVIGATE_TO_SHELF,
    SubStage.ALIGN_SHELF,
    SubStage.PLACE_BOX,
    SubStage.STABILIZE,
    SubStage.BOX_COMPLETE,
)

_STAGE_CHAINS: Mapping[Stage, tuple[SubStage, ...]] = {
    Stage.NAVIGATE_TERRAIN: _TERRAIN_CHAIN,
    Stage.SORT_PARTS: _SORT_CHAIN,
    Stage.MOVE_BOX_TO_SHELF: _BOX_CHAIN,
}

# Deadlines in minutes per stage (from 20-minute total budget)
_STAGE_DEADLINES: Mapping[Stage, float] = {
    Stage.NAVIGATE_TERRAIN: 6.0,
    Stage.SORT_PARTS: 10.0,
    Stage.MOVE_BOX_TO_SHELF: 4.0,
}

# Maximum retries per failed operation before skipping
_MAX_RETRIES = 2


class LongHorizonPlanner:
    """Long-horizon finite-state-machine planner.

    On each ``tick()`` the planner inspects the snapshot, advances sub-stages
    within the current top-level stage, and emits a :class:`PlanDecision` that
    encodes both the strategic stage and the tactical sub-stage.
    """

    _TASK_STAGE: Mapping[str, Stage] = {
        "TaskOne": Stage.NAVIGATE_TERRAIN,
        "TaskTwo": Stage.SORT_PARTS,
        "TaskThree": Stage.MOVE_BOX_TO_SHELF,
    }

    def __init__(self, on_transition: TransitionListener | None = None) -> None:
        self._stage: Stage = Stage.INIT
        self._sub_stage: SubStage = SubStage.IDLE
        self._on_transition = on_transition

        # --- per-stage bookkeeping ---
        self._entry_elapsed: float = 0.0
        self._retry_count: int = 0
        self._part_picked_count: int = 0
        self._last_stage_elapsed: Mapping[Stage, float] = {}

        # --- terrain inference ---
        self._terrain: TerrainType = TerrainType.UNKNOWN

        # --- recovery state ---
        self._in_recovery: bool = False
        self._pre_recovery_sub_stage: SubStage = SubStage.IDLE

    # ------------------------------------------------------------------
    # public properties
    # ------------------------------------------------------------------

    @property
    def stage(self) -> Stage:
        return self._stage

    @property
    def sub_stage(self) -> SubStage:
        return self._sub_stage

    @property
    def retry_count(self) -> int:
        return self._retry_count

    @property
    def part_picked_count(self) -> int:
        return self._part_picked_count

    # ------------------------------------------------------------------
    # main tick
    # ------------------------------------------------------------------

    def tick(self, snapshot: SceneSnapshot) -> PlanDecision:
        info_lower = snapshot.info.lower()

        # -- terminal guards ---------------------------------------------------
        if self._stage in (Stage.DONE, Stage.FAILED):
            return self._decision(snapshot)

        if "task is done" in info_lower:
            self._transition(Stage.DONE, snapshot.info)
            return self._decision(snapshot)

        if "time limit reached" in info_lower or "fall detected" in info_lower:
            self._transition(Stage.FAILED, snapshot.info)
            return self._decision(snapshot)

        # -- top-level stage mapping -------------------------------------------
        target_stage = self._TASK_STAGE.get(snapshot.task_id or "")
        if target_stage is not None and self._stage != target_stage:
            self._enter_stage(target_stage, snapshot)

        # -- fall detection ----------------------------------------------------
        if snapshot.is_fallen and not self._in_recovery:
            self._trigger_recovery(snapshot)
            return self._decision(snapshot)

        # -- recovery in progress ----------------------------------------------
        if self._in_recovery:
            return self._tick_recovery(snapshot)

        # -- timeout check -----------------------------------------------------
        stage_elapsed = snapshot.elapsed_minutes - self._entry_elapsed
        deadline = _STAGE_DEADLINES.get(self._stage)
        if deadline is not None and stage_elapsed > deadline:
            self._sub_stage = SubStage.TIMEOUT_ABORT
            self._transition(Stage.FAILED, f"stage timeout after {stage_elapsed:.1f} min")

        # -- sub-stage advancement ---------------------------------------------
        self._advance_sub_stage(snapshot)

        return self._decision(snapshot)

    # ------------------------------------------------------------------
    # stage entry
    # ------------------------------------------------------------------

    def _enter_stage(self, target: Stage, snapshot: SceneSnapshot) -> None:
        self._transition(target, f"environment task id is {snapshot.task_id}")
        self._entry_elapsed = snapshot.elapsed_minutes
        self._retry_count = 0
        self._in_recovery = False

        chain = _STAGE_CHAINS.get(target, ())
        self._sub_stage = chain[0] if chain else SubStage.IDLE

        # guess terrain type from stage
        if target == Stage.NAVIGATE_TERRAIN:
            self._terrain = TerrainType.FLAT
        else:
            self._terrain = TerrainType.UNKNOWN

    # ------------------------------------------------------------------
    # sub-stage advancement
    # ------------------------------------------------------------------

    def _advance_sub_stage(self, snapshot: SceneSnapshot) -> None:
        """Advance to the next sub-stage when conditions are met."""
        chain = _STAGE_CHAINS.get(self._stage)
        if not chain:
            return

        try:
            idx = chain.index(self._sub_stage)
        except ValueError:
            return

        # Check if the current sub-stage is complete
        if self._sub_stage_complete(self._sub_stage, snapshot) and idx + 1 < len(chain):
            self._sub_stage = chain[idx + 1]
            LOGGER.debug("sub_stage_advance stage=%s sub=%s", self._stage.value, self._sub_stage.value)

        # If sort is complete for one part, loop back to scan for next part
        if self._sub_stage == SubStage.SORT_COMPLETE and self._part_picked_count < self._part_target(snapshot):
            self._retry_count = 0
            self._sub_stage = SubStage.SCAN_WORKSPACE
            LOGGER.debug("sort_loop part=%d/%d", self._part_picked_count, self._part_target(snapshot))

    @staticmethod
    def _part_target(snapshot: SceneSnapshot) -> int:
        goal = snapshot.task_goal
        count = goal.get("count") if isinstance(goal, Mapping) else None
        try:
            return int(count) if count is not None else 3
        except (TypeError, ValueError):
            return 3

    def _sub_stage_complete(self, sub: SubStage, snapshot: SceneSnapshot) -> bool:
        """Heuristic per-sub-stage completion check.

        In the absence of reliable simulator state feedback, most sub-stages
        auto-advance after an estimated time budget.  These estimates MUST be
        calibrated against real simulator runs once Docker is available.
        """
        stage_elapsed = snapshot.elapsed_minutes - self._entry_elapsed

        # --- terrain heuristics (time-based, keyed to chain position) ---------
        _TERRAIN_BUDGETS: Mapping[SubStage, float] = {
            SubStage.TERRAIN_START: 0.1,
            SubStage.APPROACH_STAIRS: 0.3,
            SubStage.CLIMBING_STAIRS: 1.0,
            SubStage.POST_STAIRS_TRANSITION: 0.3,
            SubStage.APPROACH_DOWNHILL: 0.3,
            SubStage.DESCENDING_SLOPE: 0.8,
            SubStage.POST_SLOPE_TRANSITION: 0.3,
            SubStage.CROSSING_UNEVEN: 1.0,
        }

        # --- sort heuristics ------------------------------------------------
        _SORT_BUDGETS: Mapping[SubStage, float] = {
            SubStage.SORT_START: 0.1,
            SubStage.SCAN_WORKSPACE: 0.5,
            SubStage.IDENTIFY_TARGET: 0.3,
            SubStage.APPROACH_PART: 0.5,
            SubStage.GRASP_PART: 0.5,
            SubStage.VERIFY_GRASP: 0.2,
            SubStage.MOVE_TO_BOX: 0.5,
            SubStage.RELEASE_PART: 0.3,
        }

        # --- box heuristics --------------------------------------------------
        _BOX_BUDGETS: Mapping[SubStage, float] = {
            SubStage.BOX_START: 0.1,
            SubStage.APPROACH_BOX: 0.5,
            SubStage.LIFT_BOX: 0.5,
            SubStage.NAVIGATE_TO_SHELF: 1.0,
            SubStage.ALIGN_SHELF: 0.5,
            SubStage.PLACE_BOX: 0.5,
            SubStage.STABILIZE: 0.3,
        }

        budgets: Mapping[SubStage, float] = {}
        if self._stage == Stage.NAVIGATE_TERRAIN:
            budgets = _TERRAIN_BUDGETS
        elif self._stage == Stage.SORT_PARTS:
            budgets = _SORT_BUDGETS
        elif self._stage == Stage.MOVE_BOX_TO_SHELF:
            budgets = _BOX_BUDGETS

        budget = budgets.get(sub, 2.0)
        return stage_elapsed > budget

    # ------------------------------------------------------------------
    # recovery
    # ------------------------------------------------------------------

    def _trigger_recovery(self, snapshot: SceneSnapshot) -> None:
        LOGGER.warning("fall_detected stage=%s sub=%s elapsed=%.2f",
                       self._stage.value, self._sub_stage.value, snapshot.elapsed_minutes)
        self._in_recovery = True
        self._pre_recovery_sub_stage = self._sub_stage
        self._sub_stage = SubStage.FALL_RECOVERY

    def _tick_recovery(self, snapshot: SceneSnapshot) -> PlanDecision:
        # Recovery is complete when robot is upright again
        if not snapshot.is_fallen and snapshot.robot_has_ground_contact:
            self._in_recovery = False
            self._sub_stage = self._pre_recovery_sub_stage
            self._retry_count += 1

            if self._retry_count > _MAX_RETRIES:
                self._sub_stage = SubStage.SKIP_CURRENT
                LOGGER.warning("max_retries_exceeded stage=%s", self._stage.value)

            LOGGER.info("recovery_complete retries=%d resume_sub=%s",
                        self._retry_count, self._sub_stage.value)
        else:
            self._sub_stage = SubStage.FALL_RECOVERY

        return self._decision(snapshot)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _decision(self, snapshot: SceneSnapshot) -> PlanDecision:
        return PlanDecision(
            stage=self._stage,
            reason=f"{self._stage.value}:{self._sub_stage.value}",
            sub_stage=self._sub_stage,
            terrain=self._terrain,
            needs_recovery=self._in_recovery,
            retry_count=self._retry_count,
            part_picked_count=self._part_picked_count,
            part_target_count=self._part_target(snapshot),
        )

    def _transition(self, target: Stage, reason: str) -> None:
        if target == self._stage:
            return
        previous = self._stage
        self._stage = target
        # reset sub-stage on top-level transition
        chain = _STAGE_CHAINS.get(target)
        self._sub_stage = chain[0] if chain else SubStage.IDLE
        self._retry_count = 0
        if self._on_transition is not None:
            self._on_transition(previous, target, reason)

    # ------------------------------------------------------------------
    # methods for external coordination
    # ------------------------------------------------------------------

    def record_successful_grasp(self) -> None:
        self._part_picked_count += 1
        self._retry_count = 0

    def record_failed_grasp(self) -> None:
        self._retry_count += 1
        if self._retry_count > _MAX_RETRIES:
            self._sub_stage = SubStage.SKIP_CURRENT
