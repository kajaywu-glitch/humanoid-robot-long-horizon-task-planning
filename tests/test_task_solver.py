import unittest

from submission.task_solver.models import Stage, SubStage
from submission.task_solver.task_solver import TaskSolver


class TaskSolverTests(unittest.TestCase):
    def test_solver_returns_neutral_action_in_safe_mode(self) -> None:
        """Safe mode (default): all actions are neutral regardless of stage."""
        solver = TaskSolver(
            task_params={"task_goal": {"type": "A"}},
            agent_params={
                "arm_idx": list(range(14)),
                "leg_idx": list(range(12)),
                "head_idx": list(range(2)),
            },
            safe_mode=True,
        )

        action1 = solver.next_action(
            {
                "extras": {
                    "Current_Task_ID": "TaskTwo",
                    "time(minutes)": 0.1,
                    "info": "",
                }
            }
        )

        self.assertEqual(solver.current_stage, Stage.SORT_PARTS)
        self.assertIn("pick", action1)
        self.assertIsNone(action1["pick"])
        self.assertEqual(len(action1["arms"]["joint_values"]), 14)

        # In safe mode, terrain action must also be neutral
        action2 = solver.next_action(
            {
                "extras": {
                    "Current_Task_ID": "TaskOne",
                    "time(minutes)": 0.0,
                    "info": "",
                }
            }
        )
        # All joint values should be zero in safe mode
        self.assertTrue(all(v == 0.0 for v in action2["legs"]["joint_values"]),
                        "Safe mode must produce zero leg values")

    def test_unsafe_mode_produces_gait_for_terrain(self) -> None:
        """Unsafe mode: terrain stages produce non-zero gait values."""
        solver = TaskSolver(
            task_params={},
            agent_params={
                "arm_idx": list(range(14)),
                "leg_idx": list(range(12)),
                "head_idx": list(range(2)),
            },
            safe_mode=False,
        )

        action = solver.next_action(
            {
                "extras": {
                    "Current_Task_ID": "TaskOne",
                    "time(minutes)": 0.0,
                    "info": "",
                }
            }
        )

        self.assertEqual(solver.current_stage, Stage.NAVIGATE_TERRAIN)
        self.assertEqual(len(action["legs"]["joint_values"]), 12)
        # Gait should produce non-zero leg values in unsafe mode
        self.assertTrue(
            any(v != 0.0 for v in action["legs"]["joint_values"]),
            "Unsafe mode terrain gait should drive leg joints",
        )

    def test_telemetry_tracks_actions(self) -> None:
        solver = TaskSolver(
            task_params={},
            agent_params={
                "arm_idx": list(range(14)),
                "leg_idx": list(range(12)),
                "head_idx": list(range(2)),
            },
        )

        solver.next_action(
            {"extras": {"Current_Task_ID": "TaskOne", "time(minutes)": 0.0, "info": ""}}
        )
        solver.next_action(
            {"extras": {"Current_Task_ID": "TaskOne", "time(minutes)": 0.1, "info": ""}}
        )

        counts = solver.telemetry.counts_by_type()
        self.assertGreaterEqual(counts.get("action", 0), 2)
        self.assertGreaterEqual(counts.get("transition", 0), 1)

    def test_solver_handles_malformed_obs_gracefully(self) -> None:
        solver = TaskSolver(task_params={}, agent_params={})
        action = solver.next_action({})

        # Should return a valid action even on bad input
        self.assertIn("arms", action)
        self.assertIn("legs", action)
        self.assertIn("head", action)


if __name__ == "__main__":
    unittest.main()
