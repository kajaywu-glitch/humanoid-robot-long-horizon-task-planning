import unittest

from submission.task_solver.models import Stage, SubStage
from submission.task_solver.task_solver import TaskSolver


class TaskSolverTests(unittest.TestCase):
    def test_solver_returns_valid_action_and_tracks_stage(self) -> None:
        solver = TaskSolver(
            task_params={"task_goal": {"type": "A"}},
            agent_params={
                "arm_idx": list(range(14)),
                "leg_idx": list(range(12)),
                "head_idx": list(range(2)),
            },
        )

        action = solver.next_action(
            {
                "extras": {
                    "Current_Task_ID": "TaskTwo",
                    "time(minutes)": 0.1,
                    "info": "",
                }
            }
        )

        self.assertEqual(solver.current_stage, Stage.SORT_PARTS)
        self.assertIn("pick", action)
        self.assertIsNone(action["pick"])
        self.assertEqual(len(action["arms"]["joint_values"]), 14)

    def test_solver_produces_gait_for_terrain(self) -> None:
        solver = TaskSolver(
            task_params={},
            agent_params={
                "arm_idx": list(range(14)),
                "leg_idx": list(range(12)),
                "head_idx": list(range(2)),
            },
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
        # Gait should produce non-zero leg values
        self.assertTrue(
            any(v != 0.0 for v in action["legs"]["joint_values"]),
            "Terrain gait should drive leg joints",
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
