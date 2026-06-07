from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Mapping

from ..models import (
    CompletionStatus,
    EpisodeContext,
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

# Per-sub-stage time budgets (minutes) — estimated completion time.
# These are fallback values; the planner prefers observation-driven completion.
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

_BOX_BUDGETS: Mapping[SubStage, float] = {
    SubStage.BOX_START: 0.1,
    SubStage.APPROACH_BOX: 0.5,
    SubStage.LIFT_BOX: 0.5,
    SubStage.NAVIGATE_TO_SHELF: 1.0,
    SubStage.ALIGN_SHELF: 0.5,
    SubStage.PLACE_BOX: 0.5,
    SubStage.STABILIZE: 0.3,
}

# Per-sub-stage timeout (minutes) — maximum time before skipping.
# Significantly longer than budgets; triggers skip, not completion.
_SUB_STAGE_TIMEOUT = 5.0  # generous default per sub-stage

# Maximum retries per failed operation before skipping
_MAX_RETRIES = 2

# Recovery timing (seconds)
_RECOVERY_MIN_DURATION = 0.5 / 60.0   # minimum recovery time (min)
_RECOVERY_TIMEOUT = 10.0 / 60.0        # give up after 10 s (min)


class LongHorizonPlanner:
    """Long-horizon finite-state-machine planner.

    On each ``tick()`` the planner inspects the snapshot, advances sub-stages
    within the current top-level stage, and emits a :class:`PlanDecision` that
    encodes both the strategic stage and the tactical sub-stage.

    When an *episode_context* is provided it becomes the single source of
    truth for task-level parameters (part type, count) that may arrive via
    ``task_params`` rather than per-frame observation.
    """

    _TASK_STAGE: Mapping[str, Stage] = {
        "TaskOne": Stage.NAVIGATE_TERRAIN,
        "TaskTwo": Stage.SORT_PARTS,
        "TaskThree": Stage.MOVE_BOX_TO_SHELF,
    }

    def __init__(
        self,
        on_transition: TransitionListener | None = None,
        episode_context: EpisodeContext | None = None,
    ) -> None:
        self._stage: Stage = Stage.INIT
        self._sub_stage: SubStage = SubStage.IDLE
        self._on_transition = on_transition
        self._context = episode_context or EpisodeContext()

        # --- per-stage bookkeeping ---
        self._entry_elapsed: float = 0.0
        self._sub_stage_entry_elapsed: float = 0.0  # per-sub-stage clock
        self._retry_count: int = 0
        self._part_picked_count: int = 0
        self._last_stage_elapsed: Mapping[Stage, float] = {}
        self._last_failure_reason: str = ""

        # --- terrain inference ---
        self._terrain: TerrainType = TerrainType.UNKNOWN

        # --- recovery state ---
        self._in_recovery: bool = False
        self._recovery_entry_elapsed: float = 0.0
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

    @property
    def episode_context(self) -> EpisodeContext:
        return self._context

    # ------------------------------------------------------------------
    # main tick
    # ------------------------------------------------------------------

    def tick(self, snapshot: SceneSnapshot) -> PlanDecision:
        # Update context with per-frame observation task info
        self._context = self._context.merge_observation(
            snapshot.task_id, snapshot.task_goal
        )

        info_lower = snapshot.info.lower()

        # -- terminal guards ---------------------------------------------------
        if self._stage in (Stage.DONE, Stage.FAILED):
            return self._decision(snapshot)

        if "task is done" in info_lower:
            self._transition(Stage.DONE, snapshot.info)
            return self._decision(snapshot)

        if "time limit reached" in info_lower or "fall detected" in info_lower:
            self._last_failure_reason = snapshot.info
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

        # -- stage-level timeout -----------------------------------------------
        stage_elapsed = snapshot.elapsed_minutes - self._entry_elapsed
        deadline = _STAGE_DEADLINES.get(self._stage)
        if deadline is not None and stage_elapsed > deadline:
            self._last_failure_reason = f"stage timeout after {stage_elapsed:.1f} min"
            self._sub_stage = SubStage.TIMEOUT_ABORT
            self._transition(Stage.FAILED, self._last_failure_reason)
            return self._decision(snapshot)

        # -- sub-stage advancement ---------------------------------------------
        self._advance_sub_stage(snapshot)

        return self._decision(snapshot)

    # ------------------------------------------------------------------
    # stage entry
    # ------------------------------------------------------------------

    def _enter_stage(self, target: Stage, snapshot: SceneSnapshot) -> None:
        self._transition(target, f"environment task id is {snapshot.task_id}")
        self._entry_elapsed = snapshot.elapsed_minutes
        self._sub_stage_entry_elapsed = snapshot.elapsed_minutes
        self._retry_count = 0
        self._in_recovery = False
        self._last_failure_reason = ""

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
        """Advance to the next sub-stage when conditions are met.

        Completion is determined by :meth:`_check_completion` which returns a
        structured :class:`CompletionStatus`.  Each sub-stage uses a per-stage
        clock that resets on advance.
        """
        chain = _STAGE_CHAINS.get(self._stage)
        if not chain:
            return

        try:
            idx = chain.index(self._sub_stage)
        except ValueError:
            return

        status = self._check_completion(self._sub_stage, snapshot)

        if status.is_complete and idx + 1 < len(chain):
            if status.is_timeout:
                LOGGER.warning(
                    "sub_stage_timeout stage=%s sub=%s reason=%s",
                    self._stage.value, self._sub_stage.value, status.reason,
                )
                # On timeout, advance but record the reason
                self._last_failure_reason = status.reason
            else:
                self._last_failure_reason = ""

            self._sub_stage = chain[idx + 1]
            self._sub_stage_entry_elapsed = snapshot.elapsed_minutes
            LOGGER.debug(
                "sub_stage_advance stage=%s sub=%s reason=%s",
                self._stage.value, self._sub_stage.value, status.reason,
            )

        # If sort is complete for one part, loop back to scan for next part
        if self._sub_stage == SubStage.SORT_COMPLETE and self._part_picked_count < self._part_target():
            self._retry_count = 0
            self._sub_stage = SubStage.SCAN_WORKSPACE
            self._sub_stage_entry_elapsed = snapshot.elapsed_minutes
            LOGGER.debug("sort_loop part=%d/%d", self._part_picked_count, self._part_target())

    def _part_target(self) -> int:
        return self._context.target_part_count

    def _check_completion(self, sub: SubStage, snapshot: SceneSnapshot) -> CompletionStatus:
        """Structured completion check for *sub*.

        Checks in priority order:
        1. **Observation-driven** — concrete evidence from the scene.
        2. **Time budget** — estimated time elapsed (fallback).
        3. **Timeout** — maximum allowed time exceeded.

        All reasons are logged for auditability.
        """
        sub_elapsed = snapshot.elapsed_minutes - self._sub_stage_entry_elapsed

        # --- observation-driven checks ----------------------------------------
        obs_status = self._observation_complete(sub, snapshot)
        if obs_status is not None:
            return obs_status

        # --- time budget (fallback) -------------------------------------------
        budget = self._budget_for(sub)
        if sub_elapsed > budget:
            return CompletionStatus.done(
                f"time_budget: {sub_elapsed:.3f} min > {budget:.3f} min"
            )

        # --- sub-stage timeout (skip, don't silently succeed) -----------------
        if sub_elapsed > _SUB_STAGE_TIMEOUT:
            return CompletionStatus.timeout(
                f"sub_stage_timeout: {sub_elapsed:.3f} min > {_SUB_STAGE_TIMEOUT:.3f} min"
            )

        return CompletionStatus.not_yet(
            f"waiting: {sub_elapsed:.3f}/{budget:.3f} min"
        )

    # ------------------------------------------------------------------
    # observation-driven completion (extensible per sub-stage)
    # ------------------------------------------------------------------

    def _observation_complete(
        self, sub: SubStage, snapshot: SceneSnapshot
    ) -> CompletionStatus | None:
        """Return a CompletionStatus if *sub* can be decided from observation.

        Returns ``None`` when there is no observation-based check for this
        sub-stage — the caller falls back to time-based heuristics.

        This method is designed to grow as Docker sampling reveals which
        observation fields actually signal completion.
        """
        # --- grasp verification ------------------------------------------------
        if sub == SubStage.VERIFY_GRASP:
            if snapshot.is_holding_object:
                return CompletionStatus.done("observation: holding object confirmed")
            return None  # fall back to time

        # --- release verification ----------------------------------------------
        if sub == SubStage.RELEASE_PART:
            if not snapshot.is_holding_object:
                return CompletionStatus.done("observation: released object")
            return None

        # --- terrain detection from IMU ----------------------------------------
        if sub == SubStage.TERRAIN_COMPLETE:
            return CompletionStatus.done("observation: chain exhausted")

        # No observation-based check for this sub-stage yet
        return None

    # ------------------------------------------------------------------
    # budget lookup
    # ------------------------------------------------------------------

    @staticmethod
    def _budget_for(sub: SubStage) -> float:
        """Return the estimated time budget for *sub* regardless of stage."""
        for budgets in (_TERRAIN_BUDGETS, _SORT_BUDGETS, _BOX_BUDGETS):
            if sub in budgets:
                return budgets[sub]
        return 2.0

    # ------------------------------------------------------------------
    # recovery
    # ------------------------------------------------------------------

    def _trigger_recovery(self, snapshot: SceneSnapshot) -> None:
        LOGGER.warning("fall_detected stage=%s sub=%s elapsed=%.2f",
                       self._stage.value, self._sub_stage.value, snapshot.elapsed_minutes)
        self._in_recovery = True
        self._recovery_entry_elapsed = snapshot.elapsed_minutes
        self._pre_recovery_sub_stage = self._sub_stage
        self._sub_stage = SubStage.FALL_RECOVERY

    def _tick_recovery(self, snapshot: SceneSnapshot) -> PlanDecision:
        """Tick recovery with proper timing guards.

        Recovery requires BOTH:
        1. Minimum duration elapsed (so the recovery primitive has time to run)
        2. Robot is upright with ground contact

        Times out after _RECOVERY_TIMEOUT minutes.
        Success is checked first — a slow-but-successful recovery is fine.
        """
        recovery_elapsed = snapshot.elapsed_minutes - self._recovery_entry_elapsed

        # Check if robot is upright AND minimum duration has passed
        is_upright = not snapshot.is_fallen and snapshot.robot_has_ground_contact
        min_duration_met = recovery_elapsed >= _RECOVERY_MIN_DURATION

        if is_upright and min_duration_met:
            self._in_recovery = False
            self._sub_stage = self._pre_recovery_sub_stage
            self._sub_stage_entry_elapsed = snapshot.elapsed_minutes
            self._retry_count += 1

            if self._retry_count > _MAX_RETRIES:
                self._sub_stage = SubStage.SKIP_CURRENT
                self._last_failure_reason = f"max retries ({_MAX_RETRIES}) exceeded"
                LOGGER.warning("max_retries_exceeded stage=%s", self._stage.value)

            LOGGER.info("recovery_complete retries=%d resume_sub=%s elapsed=%.2f",
                        self._retry_count, self._sub_stage.value, recovery_elapsed)
            return self._decision(snapshot)

        # Timeout — give up and mark as failed
        if recovery_elapsed > _RECOVERY_TIMEOUT:
            self._last_failure_reason = f"recovery timeout after {recovery_elapsed:.2f} min"
            LOGGER.warning(self._last_failure_reason)
            self._in_recovery = False
            self._sub_stage = SubStage.TIMEOUT_ABORT
            self._transition(Stage.FAILED, self._last_failure_reason)
            return self._decision(snapshot)

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
            part_target_count=self._part_target(),
            failure_reason=self._last_failure_reason,
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
