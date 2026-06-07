import math
import unittest

from submission.task_solver.models import (
    CompletionStatus,
    EpisodeContext,
    SceneSnapshot,
    Stage,
    SubStage,
)
from submission.task_solver.planner.fsm import LongHorizonPlanner


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _snap(
    task_id: str = "TaskOne",
    info: str = "",
    elapsed: float = 0.0,
    imu_pitch: float = 0.0,
    imu_roll: float = 0.0,
    left_contact: bool = True,
    right_contact: bool = True,
    is_holding: bool = False,
    task_goal: dict | None = None,
) -> SceneSnapshot:
    return SceneSnapshot(
        task_id=task_id,
        elapsed_minutes=elapsed,
        info=info,
        imu_pitch=imu_pitch,
        imu_roll=imu_roll,
        left_foot_contact=left_contact,
        right_foot_contact=right_contact,
        is_holding_object=is_holding,
        task_goal=task_goal or {},
    )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class LongHorizonPlannerTests(unittest.TestCase):
    """Existing tests — preserved and adapted for new signatures."""

    def test_maps_environment_tasks_to_stages(self) -> None:
        planner = LongHorizonPlanner()

        d1 = planner.tick(_snap("TaskOne"))
        self.assertEqual(d1.stage, Stage.NAVIGATE_TERRAIN)
        self.assertEqual(d1.sub_stage, SubStage.TERRAIN_START)

        d2 = planner.tick(_snap("TaskTwo"))
        self.assertEqual(d2.stage, Stage.SORT_PARTS)
        self.assertEqual(d2.sub_stage, SubStage.SORT_START)

        d3 = planner.tick(_snap("TaskThree"))
        self.assertEqual(d3.stage, Stage.MOVE_BOX_TO_SHELF)
        self.assertEqual(d3.sub_stage, SubStage.BOX_START)

    def test_terminal_failure_is_sticky(self) -> None:
        planner = LongHorizonPlanner()
        planner.tick(_snap("TaskOne", info="Fall detected"))

        self.assertEqual(planner.stage, Stage.FAILED)
        self.assertEqual(planner.tick(_snap("TaskTwo")).stage, Stage.FAILED)

    def test_terminal_done_is_sticky(self) -> None:
        planner = LongHorizonPlanner()
        planner.tick(_snap("TaskOne", info="task is done"))

        self.assertEqual(planner.stage, Stage.DONE)
        self.assertEqual(planner.tick(_snap("TaskTwo")).stage, Stage.DONE)

    def test_transition_listener_receives_changes_only(self) -> None:
        transitions = []
        planner = LongHorizonPlanner(
            on_transition=lambda previous, target, reason: transitions.append(
                (previous, target, reason)
            )
        )

        planner.tick(_snap("TaskOne"))
        planner.tick(_snap("TaskOne"))

        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0][0:2], (Stage.INIT, Stage.NAVIGATE_TERRAIN))

    def test_sub_stage_advances_over_time(self) -> None:
        planner = LongHorizonPlanner()
        d = planner.tick(_snap("TaskOne", elapsed=0.0))
        self.assertEqual(d.sub_stage, SubStage.TERRAIN_START)

        # After enough time, sub-stage advances
        d = planner.tick(_snap("TaskOne", elapsed=1.0))
        self.assertNotEqual(d.sub_stage, SubStage.TERRAIN_START)

    def test_fall_triggers_recovery(self) -> None:
        planner = LongHorizonPlanner()
        planner.tick(_snap("TaskOne", elapsed=0.0))

        d = planner.tick(
            _snap("TaskOne", elapsed=0.5, imu_pitch=math.radians(80.0))
        )
        self.assertTrue(d.needs_recovery)
        self.assertEqual(d.sub_stage, SubStage.FALL_RECOVERY)

    def test_recovery_resumes_previous_sub_stage(self) -> None:
        planner = LongHorizonPlanner()
        planner.tick(_snap("TaskOne", elapsed=0.0))

        # fall
        d = planner.tick(
            _snap("TaskOne", elapsed=0.3, imu_pitch=math.radians(80.0))
        )
        self.assertTrue(d.needs_recovery)

        # recover — upright + contact + min duration passed
        d = planner.tick(
            _snap("TaskOne", elapsed=0.6, left_contact=True, right_contact=True)
        )
        self.assertFalse(d.needs_recovery)
        self.assertEqual(d.retry_count, 1)


# ---------------------------------------------------------------------------
# Table-driven tests (P0-B additions)
# ---------------------------------------------------------------------------


class TerrainChainAdvanceTests(unittest.TestCase):
    """Table-driven: terrain sub-stage chain advances with independent timing."""

    def test_full_terrain_chain_advances_in_order(self) -> None:
        planner = LongHorizonPlanner()
        planner.tick(_snap("TaskOne", elapsed=0.0))

        # Each sub-stage needs its own time budget
        budgets = [0.1, 0.3, 1.0, 0.3, 0.3, 0.8, 0.3, 1.0]
        elapsed = 0.0
        seen: list[SubStage] = []

        for budget in budgets:
            elapsed += budget + 0.01  # just over budget
            d = planner.tick(_snap("TaskOne", elapsed=elapsed))
            seen.append(d.sub_stage)

        # TERRAIN_START → APPROACH_STAIRS → CLIMBING_STAIRS → ... → TERRAIN_COMPLETE
        expected = [
            SubStage.APPROACH_STAIRS,
            SubStage.CLIMBING_STAIRS,
            SubStage.POST_STAIRS_TRANSITION,
            SubStage.APPROACH_DOWNHILL,
            SubStage.DESCENDING_SLOPE,
            SubStage.POST_SLOPE_TRANSITION,
            SubStage.CROSSING_UNEVEN,
            SubStage.TERRAIN_COMPLETE,
        ]
        self.assertEqual(seen, expected)


class SubStageTimeoutTests(unittest.TestCase):
    """Sub-stage timing: each sub-stage gets an independent time budget."""

    def test_each_sub_stage_advances_with_its_own_budget(self) -> None:
        """Each sub-stage advances after its individual time budget, not accumulated."""
        planner = LongHorizonPlanner()
        planner.tick(_snap("TaskOne", elapsed=0.0))

        # TERRAIN_START budget is 0.1 min
        d = planner.tick(_snap("TaskOne", elapsed=0.15))
        self.assertEqual(d.sub_stage, SubStage.APPROACH_STAIRS)
        self.assertEqual(d.failure_reason, "")

        # APPROACH_STAIRS budget is 0.3 min — need another 0.3 from 0.15
        d = planner.tick(_snap("TaskOne", elapsed=0.50))
        self.assertEqual(d.sub_stage, SubStage.CLIMBING_STAIRS)

        # CLIMBING_STAIRS budget is 1.0 min
        d = planner.tick(_snap("TaskOne", elapsed=1.55))
        self.assertEqual(d.sub_stage, SubStage.POST_STAIRS_TRANSITION)


class RepeatedRecoveryTests(unittest.TestCase):
    """Table-driven: repeated fall/recovery cycles increment retry count."""

    def test_two_falls_then_skip(self) -> None:
        planner = LongHorizonPlanner()
        planner.tick(_snap("TaskOne", elapsed=0.0))

        # First fall + recovery
        d = planner.tick(
            _snap("TaskOne", elapsed=0.3, imu_pitch=math.radians(80.0))
        )
        self.assertTrue(d.needs_recovery)
        self.assertEqual(d.retry_count, 0)  # not yet recovered

        d = planner.tick(
            _snap("TaskOne", elapsed=0.6, left_contact=True, right_contact=True)
        )
        self.assertFalse(d.needs_recovery)
        self.assertEqual(d.retry_count, 1)

        # Second fall
        d = planner.tick(
            _snap("TaskOne", elapsed=1.0, imu_pitch=math.radians(85.0))
        )
        self.assertTrue(d.needs_recovery)

        d = planner.tick(
            _snap("TaskOne", elapsed=1.5, left_contact=True, right_contact=True)
        )
        self.assertFalse(d.needs_recovery)
        self.assertEqual(d.retry_count, 2)

        # Third fall — max retries exceeded
        d = planner.tick(
            _snap("TaskOne", elapsed=2.0, imu_pitch=math.radians(90.0))
        )
        self.assertTrue(d.needs_recovery)

        d = planner.tick(
            _snap("TaskOne", elapsed=2.5, left_contact=True, right_contact=True)
        )
        self.assertFalse(d.needs_recovery)
        self.assertEqual(d.retry_count, 3)
        # Should skip current sub-stage after max retries
        self.assertEqual(d.sub_stage, SubStage.SKIP_CURRENT)


class EpisodeContextTests(unittest.TestCase):
    """Table-driven: episode context drives part counts and task goals."""

    def test_episode_context_propagates_part_count(self) -> None:
        ctx = EpisodeContext.from_params(
            {"task_goal": {"type": "A", "count": 5}},
            task_id="TaskTwo",
        )
        self.assertEqual(ctx.target_part_type, "A")
        self.assertEqual(ctx.target_part_count, 5)

        planner = LongHorizonPlanner(episode_context=ctx)
        d = planner.tick(_snap("TaskTwo", elapsed=0.0))
        self.assertEqual(d.part_target_count, 5)

    def test_episode_context_merges_observation_fields(self) -> None:
        ctx = EpisodeContext(task_id="", target_part_type="", target_part_count=3)
        merged = ctx.merge_observation("TaskTwo", {"type": "B", "count": 2})
        self.assertEqual(merged.task_id, "TaskTwo")
        self.assertEqual(merged.target_part_type, "B")
        self.assertEqual(merged.target_part_count, 2)

    def test_context_does_not_overwrite_with_empty_obs(self) -> None:
        ctx = EpisodeContext.from_params(
            {"task_goal": {"type": "C", "count": 4}},
            task_id="TaskTwo",
        )
        merged = ctx.merge_observation(None, {})
        self.assertEqual(merged.target_part_type, "C")
        self.assertEqual(merged.target_part_count, 4)


class CompletionStatusTests(unittest.TestCase):
    """Table-driven: structured completion produces correct reasons."""

    def test_done_has_reason(self) -> None:
        s = CompletionStatus.done("test")
        self.assertTrue(s.is_complete)
        self.assertFalse(s.is_timeout)
        self.assertEqual(s.reason, "test")

    def test_not_yet_has_reason(self) -> None:
        s = CompletionStatus.not_yet("waiting")
        self.assertFalse(s.is_complete)
        self.assertFalse(s.is_timeout)
        self.assertEqual(s.reason, "waiting")

    def test_timeout_flags_both(self) -> None:
        s = CompletionStatus.timeout("too slow")
        self.assertTrue(s.is_complete)
        self.assertTrue(s.is_timeout)
        self.assertEqual(s.reason, "too slow")


class ObservationDrivenCompletionTests(unittest.TestCase):
    """Observation-driven completion is used when available.

    Each tick advances at most **one** sub-stage.  Observation-based checks
    fire on the tick AFTER the sub-stage is entered.
    """

    def test_verify_grasp_completes_on_next_tick_when_holding(self) -> None:
        """VERIFY_GRASP completes via observation on the tick after entry."""
        planner = LongHorizonPlanner()
        # Walk through sort chain to GRASP_PART
        planner.tick(_snap("TaskTwo", elapsed=0.0))        # SORT_START
        planner.tick(_snap("TaskTwo", elapsed=0.15))       # → SCAN_WORKSPACE
        planner.tick(_snap("TaskTwo", elapsed=0.70))       # → IDENTIFY_TARGET
        planner.tick(_snap("TaskTwo", elapsed=1.05))       # → APPROACH_PART
        planner.tick(_snap("TaskTwo", elapsed=1.60))       # → GRASP_PART

        # Tick to advance GRASP_PART → VERIFY_GRASP (budget 0.5 min met)
        d = planner.tick(_snap("TaskTwo", elapsed=2.15))
        self.assertEqual(d.sub_stage, SubStage.VERIFY_GRASP)

        # Now tick with is_holding=True — VERIFY_GRASP completes via observation
        d = planner.tick(_snap("TaskTwo", elapsed=2.20, is_holding=True))
        self.assertEqual(d.sub_stage, SubStage.MOVE_TO_BOX)

    def test_release_completes_on_next_tick_when_not_holding(self) -> None:
        """RELEASE_PART completes via observation on the tick after entry."""
        planner = LongHorizonPlanner()
        planner.tick(_snap("TaskTwo", elapsed=0.0))
        planner.tick(_snap("TaskTwo", elapsed=0.15))       # → SCAN_WORKSPACE
        planner.tick(_snap("TaskTwo", elapsed=0.70))       # → IDENTIFY_TARGET
        planner.tick(_snap("TaskTwo", elapsed=1.05))       # → APPROACH_PART
        planner.tick(_snap("TaskTwo", elapsed=1.60))       # → GRASP_PART
        planner.tick(_snap("TaskTwo", elapsed=2.15))       # → VERIFY_GRASP
        planner.tick(_snap("TaskTwo", elapsed=2.20, is_holding=True))  # → MOVE_TO_BOX
        planner.tick(_snap("TaskTwo", elapsed=2.75))       # → RELEASE_PART

        # Tick with is_holding=False → RELEASE_PART completes via observation
        # After RELEASE → SORT_COMPLETE, but since part_picked_count (0) < target (3),
        # it loops back to SCAN_WORKSPACE for the next part.
        d = planner.tick(_snap("TaskTwo", elapsed=2.80, is_holding=False))
        self.assertEqual(d.sub_stage, SubStage.SCAN_WORKSPACE)  # looped back for next part


class TaskSwitchTests(unittest.TestCase):
    """Task switching mid-episode updates the stage."""

    def test_task_switch_from_one_to_two(self) -> None:
        planner = LongHorizonPlanner()
        d1 = planner.tick(_snap("TaskOne", elapsed=0.0))
        self.assertEqual(d1.stage, Stage.NAVIGATE_TERRAIN)

        d2 = planner.tick(_snap("TaskTwo", elapsed=1.0))
        self.assertEqual(d2.stage, Stage.SORT_PARTS)

    def test_task_switch_resets_sub_stage(self) -> None:
        planner = LongHorizonPlanner()
        # Progress through terrain
        planner.tick(_snap("TaskOne", elapsed=0.0))
        d = planner.tick(_snap("TaskOne", elapsed=2.0))
        self.assertNotEqual(d.sub_stage, SubStage.TERRAIN_START)

        # Switch to sort
        d = planner.tick(_snap("TaskTwo", elapsed=2.5))
        self.assertEqual(d.stage, Stage.SORT_PARTS)
        self.assertEqual(d.sub_stage, SubStage.SORT_START)


class FailureReasonPropagationTests(unittest.TestCase):
    """Failure reasons propagate to PlanDecision."""

    def test_stage_timeout_sets_failure_reason(self) -> None:
        planner = LongHorizonPlanner()
        d = planner.tick(_snap("TaskOne", elapsed=0.0))
        self.assertEqual(d.failure_reason, "")

        # Exceed stage deadline
        d = planner.tick(_snap("TaskOne", elapsed=10.0))
        self.assertEqual(d.stage, Stage.FAILED)
        self.assertIn("stage timeout", d.failure_reason)

    def test_info_failure_sets_reason(self) -> None:
        planner = LongHorizonPlanner()
        d = planner.tick(
            _snap("TaskOne", info="time limit reached", elapsed=0.5)
        )
        self.assertEqual(d.stage, Stage.FAILED)
        self.assertEqual(d.failure_reason, "time limit reached")


if __name__ == "__main__":
    unittest.main()
