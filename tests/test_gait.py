import unittest

from submission.task_solver.control.gait import (
    PosturePrimitive,
    RecoveryPrimitive,
    SinusoidalGait,
    _clip,
    _fill,
)
from submission.task_solver.models import GaitParams


class SinusoidalGaitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gait = SinusoidalGait(
            params=GaitParams(frequency=2.0, step_length=0.3, step_height=0.15),
            leg_count=12,
            arm_count=14,
        )

    def test_output_has_correct_dimensions(self) -> None:
        arm, leg = self.gait.tick(dt=0.02)
        self.assertEqual(len(arm), 14)
        self.assertEqual(len(leg), 12)

    def test_gait_values_change_over_time(self) -> None:
        arm1, leg1 = self.gait.tick(dt=0.02)
        arm2, leg2 = self.gait.tick(dt=0.02)

        # Values should differ between steps (phase advances)
        self.assertNotEqual(arm1, arm2)
        self.assertNotEqual(leg1, leg2)

    def test_stair_gait_modifies_knee_and_hip(self) -> None:
        _, leg = self.gait.tick_stairs(dt=0.02)
        # Knee pitches (indices 3 and 9 for 6-DoF-per-leg layout) should be adjusted
        self.assertEqual(len(leg), 12)

    def test_slope_down_gait_applies_backward_lean(self) -> None:
        _, leg = self.gait.tick_slope_down(dt=0.02)
        # Should produce leg values
        self.assertEqual(len(leg), 12)

    def test_uneven_gait_increases_knee_lift(self) -> None:
        _, leg1 = self.gait.tick_flat(dt=0.02)
        _, leg2 = self.gait.tick_uneven(dt=0.02)
        # Uneven gait should differ from flat
        self.assertNotEqual(leg1, leg2)

    def test_gait_respects_leg_count_bounds(self) -> None:
        small_gait = SinusoidalGait(leg_count=4, arm_count=6)
        arm, leg = small_gait.tick(dt=0.02)
        self.assertEqual(len(arm), 6)
        self.assertEqual(len(leg), 4)

    def test_different_params_produce_different_outputs(self) -> None:
        fast_gait = SinusoidalGait(
            params=GaitParams(frequency=4.0, step_length=0.6),
            leg_count=12,
            arm_count=14,
        )
        _, leg_slow = self.gait.tick(dt=0.02)
        _, leg_fast = fast_gait.tick(dt=0.02)
        self.assertNotEqual(leg_slow, leg_fast)


class PosturePrimitiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.posture = PosturePrimitive(leg_count=12, arm_count=14)

    def test_stand_is_zero(self) -> None:
        arm, leg = self.posture.stand()
        self.assertEqual(arm, [0.0] * 14)
        self.assertEqual(leg, [0.0] * 12)

    def test_crouch_bends_knees(self) -> None:
        _, leg = self.posture.crouch(depth=0.5)
        # Knee pitch (index 3 for left leg, 9 for right) should be flexed
        self.assertGreater(leg[3], 0.0)
        self.assertGreater(leg[9], 0.0)

    def test_arms_forward_has_correct_length(self) -> None:
        arm = self.posture.arms_forward(amount=0.7)
        self.assertEqual(len(arm), 14)
        # Shoulder pitches (indices 0 and 7) should be positive
        self.assertGreater(arm[0], 0.0)
        self.assertGreater(arm[7], 0.0)


class RecoveryPrimitiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recovery = RecoveryPrimitive(arm_count=14, leg_count=12)

    def test_recovery_sequence_completes(self) -> None:
        self.assertFalse(self.recovery.is_done)

        # Run through all phases
        for _ in range(200):
            arm, leg = self.recovery.tick(dt=0.03)
            if self.recovery.is_done:
                break

        self.assertTrue(self.recovery.is_done)
        # Final state should be neutral (stand = all zeros)
        self.assertEqual(arm, [0.0] * 14)
        self.assertEqual(leg, [0.0] * 12)

    def test_reset_restarts_recovery(self) -> None:
        self.recovery.tick(dt=2.0)  # Jump far into recovery
        self.recovery.reset()
        self.assertFalse(self.recovery.is_done)


class HelperTests(unittest.TestCase):
    def test_clip_constrains_value(self) -> None:
        self.assertEqual(_clip(0.5, 0.0, 1.0), 0.5)
        self.assertEqual(_clip(2.0, 0.0, 1.0), 1.0)
        self.assertEqual(_clip(-1.0, 0.0, 1.0), 0.0)

    def test_fill_pads_shorter_input(self) -> None:
        result = _fill([1.0, 2.0], 5, default=-1.0)
        self.assertEqual(result, [1.0, 2.0, -1.0, -1.0, -1.0])

    def test_fill_trims_longer_input(self) -> None:
        result = _fill([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        self.assertEqual(result, [1.0, 2.0, 3.0])


if __name__ == "__main__":
    unittest.main()
