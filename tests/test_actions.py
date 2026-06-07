import unittest

from submission.task_solver.control.actions import ActionFactory, validate_action
from submission.task_solver.models import PlanDecision, Stage


class ActionFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = ActionFactory(
            {
                "arm_idx": list(range(14)),
                "leg_idx": list(range(12)),
                "head_idx": list(range(2)),
            }
        )

    def test_task_one_action_has_official_joint_lengths(self) -> None:
        action = self.factory.for_decision(
            PlanDecision(Stage.NAVIGATE_TERRAIN, "test"),
            "TaskOne",
        )

        self.assertEqual(len(action["arms"]["joint_values"]), 14)
        self.assertEqual(len(action["legs"]["joint_values"]), 12)
        self.assertEqual(len(action["head"]["joint_values"]), 2)
        validate_action(action)

    def test_manipulation_action_contains_pick_command(self) -> None:
        action = self.factory.for_decision(
            PlanDecision(Stage.SORT_PARTS, "test"),
            "TaskTwo",
        )

        self.assertIn("pick", action)
        self.assertIsNone(action["pick"])

    def test_actions_do_not_share_mutable_lists(self) -> None:
        decision = PlanDecision(Stage.NAVIGATE_TERRAIN, "test")
        first = self.factory.for_decision(decision, "TaskOne")
        second = self.factory.for_decision(decision, "TaskOne")

        # Save original values before mutating first.
        second_original = second["arms"]["joint_values"][0]
        first["arms"]["joint_values"][0] = 999.0

        # Second action's joint_values must be independent (not shared).
        self.assertEqual(second["arms"]["joint_values"][0], second_original)
        self.assertEqual(first["arms"]["joint_values"][0], 999.0)

    def test_invalid_pick_is_rejected(self) -> None:
        action = self.factory.for_decision(
            PlanDecision(Stage.SORT_PARTS, "test"),
            "TaskTwo",
        )
        action["pick"] = "both_hands"

        with self.assertRaises(ValueError):
            validate_action(action)

    def test_terrain_action_produces_non_zero_joint_values(self) -> None:
        """Terrain stages use the SinusoidalGait — values must vary over time."""
        action1 = self.factory.for_decision(
            PlanDecision(Stage.NAVIGATE_TERRAIN, "test"),
            "TaskOne",
        )
        action2 = self.factory.for_decision(
            PlanDecision(Stage.NAVIGATE_TERRAIN, "test"),
            "TaskOne",
        )

        # After two ticks the gait phase advances — values should differ.
        self.assertNotEqual(
            action1["arms"]["joint_values"],
            action2["arms"]["joint_values"],
            "Terrain gait should produce varying joint values across steps",
        )

    def test_all_stages_pass_validation(self) -> None:
        for stage in (Stage.NAVIGATE_TERRAIN, Stage.SORT_PARTS, Stage.MOVE_BOX_TO_SHELF):
            action = self.factory.for_decision(PlanDecision(stage, "test"), "TaskTwo")
            try:
                validate_action(action)
            except ValueError as exc:
                self.fail(f"Stage {stage.value} action failed validation: {exc}")


if __name__ == "__main__":
    unittest.main()
