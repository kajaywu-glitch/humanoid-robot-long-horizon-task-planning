import unittest

from submission.task_solver.models import SceneSnapshot, Stage, SubStage
from submission.task_solver.planner.fsm import LongHorizonPlanner


class LongHorizonPlannerTests(unittest.TestCase):
    def test_maps_environment_tasks_to_stages(self) -> None:
        planner = LongHorizonPlanner()

        d1 = planner.tick(self.snapshot("TaskOne"))
        self.assertEqual(d1.stage, Stage.NAVIGATE_TERRAIN)
        self.assertEqual(d1.sub_stage, SubStage.TERRAIN_START)

        d2 = planner.tick(self.snapshot("TaskTwo"))
        self.assertEqual(d2.stage, Stage.SORT_PARTS)
        self.assertEqual(d2.sub_stage, SubStage.SORT_START)

        d3 = planner.tick(self.snapshot("TaskThree"))
        self.assertEqual(d3.stage, Stage.MOVE_BOX_TO_SHELF)
        self.assertEqual(d3.sub_stage, SubStage.BOX_START)

    def test_terminal_failure_is_sticky(self) -> None:
        planner = LongHorizonPlanner()
        planner.tick(self.snapshot("TaskOne", info="Fall detected"))

        self.assertEqual(planner.stage, Stage.FAILED)
        self.assertEqual(planner.tick(self.snapshot("TaskTwo")).stage, Stage.FAILED)

    def test_terminal_done_is_sticky(self) -> None:
        planner = LongHorizonPlanner()
        planner.tick(self.snapshot("TaskOne", info="task is done"))

        self.assertEqual(planner.stage, Stage.DONE)
        self.assertEqual(planner.tick(self.snapshot("TaskTwo")).stage, Stage.DONE)

    def test_transition_listener_receives_changes_only(self) -> None:
        transitions = []
        planner = LongHorizonPlanner(
            on_transition=lambda previous, target, reason: transitions.append(
                (previous, target, reason)
            )
        )

        planner.tick(self.snapshot("TaskOne"))
        planner.tick(self.snapshot("TaskOne"))

        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0][0:2], (Stage.INIT, Stage.NAVIGATE_TERRAIN))

    def test_sub_stage_advances_over_time(self) -> None:
        planner = LongHorizonPlanner()
        # Start TaskOne
        d = planner.tick(self.snapshot("TaskOne", elapsed=0.0))
        self.assertEqual(d.sub_stage, SubStage.TERRAIN_START)

        # After enough time, sub-stage advances
        d = planner.tick(self.snapshot("TaskOne", elapsed=1.0))
        # Should have advanced past TERRAIN_START and APPROACH_STAIRS
        self.assertNotEqual(d.sub_stage, SubStage.TERRAIN_START)

    def test_fall_triggers_recovery(self) -> None:
        planner = LongHorizonPlanner()
        planner.tick(self.snapshot("TaskOne", elapsed=0.0))

        # Simulate a fallen robot via IMU
        import math
        snap = SceneSnapshot(
            task_id="TaskOne",
            elapsed_minutes=0.5,
            info="",
            imu_pitch=math.radians(80.0),
            imu_roll=0.0,
        )
        d = planner.tick(snap)
        self.assertTrue(d.needs_recovery)
        self.assertEqual(d.sub_stage, SubStage.FALL_RECOVERY)

    def test_recovery_resumes_previous_sub_stage(self) -> None:
        planner = LongHorizonPlanner()
        planner.tick(self.snapshot("TaskOne", elapsed=0.0))

        # fall
        import math
        fallen = SceneSnapshot(
            task_id="TaskOne", elapsed_minutes=0.3, info="",
            imu_pitch=math.radians(80.0), imu_roll=0.0,
        )
        d = planner.tick(fallen)
        self.assertTrue(d.needs_recovery)

        # recover
        upright = SceneSnapshot(
            task_id="TaskOne", elapsed_minutes=0.6, info="",
            imu_pitch=0.0, imu_roll=0.0,
            left_foot_contact=True, right_foot_contact=True,
        )
        d = planner.tick(upright)
        self.assertFalse(d.needs_recovery)
        self.assertEqual(d.retry_count, 1)

    @staticmethod
    def snapshot(
        task_id: str,
        info: str = "",
        elapsed: float = 0.0,
    ) -> SceneSnapshot:
        return SceneSnapshot(
            task_id=task_id,
            elapsed_minutes=elapsed,
            info=info,
        )


if __name__ == "__main__":
    unittest.main()
