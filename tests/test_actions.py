import unittest

from submission.task_solver.control.actions import ActionFactory, validate_action
from submission.task_solver.models import PlanDecision, Stage


class ActionFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory_safe = ActionFactory(
            {
                "arm_idx": list(range(14)),
                "leg_idx": list(range(12)),
                "head_idx": list(range(2)),
            },
            safe_mode=True,
        )
        self.factory_unsafe = ActionFactory(
            {
                "arm_idx": list(range(14)),
                "leg_idx": list(range(12)),
                "head_idx": list(range(2)),
            },
            safe_mode=False,
        )

    def test_safe_mode_all_stages_return_neutral(self) -> None:
        """In safe mode every stage/sub-stage returns a validated neutral action."""
        for stage in (Stage.NAVIGATE_TERRAIN, Stage.SORT_PARTS, Stage.MOVE_BOX_TO_SHELF):
            action = self.factory_safe.for_decision(
                PlanDecision(stage, "safe_test"), "TaskOne"
            )
            validate_action(action)
            self.assertEqual(len(action["arms"]["joint_values"]), 14)
            self.assertEqual(len(action["legs"]["joint_values"]), 12)
            # All joint values must be zero in safe mode
            self.assertTrue(all(v == 0.0 for v in action["arms"]["joint_values"]))
            self.assertTrue(all(v == 0.0 for v in action["legs"]["joint_values"]))

    def test_unsafe_terrain_produces_non_zero_joint_values(self) -> None:
        """Unsafe mode: terrain stages use SinusoidalGait — values vary over time."""
        action1 = self.factory_unsafe.for_decision(
            PlanDecision(Stage.NAVIGATE_TERRAIN, "test"),
            "TaskOne",
        )
        action2 = self.factory_unsafe.for_decision(
            PlanDecision(Stage.NAVIGATE_TERRAIN, "test"),
            "TaskOne",
        )

        # After two ticks the gait phase advances — values should differ.
        self.assertNotEqual(
            action1["arms"]["joint_values"],
            action2["arms"]["joint_values"],
            "Unsafe terrain gait should produce varying joint values across steps",
        )

    def test_actions_do_not_share_mutable_lists(self) -> None:
        decision = PlanDecision(Stage.NAVIGATE_TERRAIN, "test")
        first = self.factory_unsafe.for_decision(decision, "TaskOne")
        second = self.factory_unsafe.for_decision(decision, "TaskOne")

        # Save original values before mutating first.
        second_original = second["arms"]["joint_values"][0]
        first["arms"]["joint_values"][0] = 999.0

        # Second action's joint_values must be independent (not shared).
        self.assertEqual(second["arms"]["joint_values"][0], second_original)
        self.assertEqual(first["arms"]["joint_values"][0], 999.0)

    def test_invalid_pick_is_rejected(self) -> None:
        action = self.factory_safe.for_decision(
            PlanDecision(Stage.SORT_PARTS, "test"),
            "TaskTwo",
        )
        action["pick"] = "both_hands"

        with self.assertRaises(ValueError):
            validate_action(action)

    def test_all_unsafe_stages_pass_validation(self) -> None:
        for stage in (Stage.NAVIGATE_TERRAIN, Stage.SORT_PARTS, Stage.MOVE_BOX_TO_SHELF):
            action = self.factory_unsafe.for_decision(PlanDecision(stage, "test"), "TaskTwo")
            try:
                validate_action(action)
            except ValueError as exc:
                self.fail(f"Stage {stage.value} action failed validation: {exc}")


if __name__ == "__main__":
    unittest.main()
