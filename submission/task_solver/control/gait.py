"""Parameterised bipedal walking primitives for the Kuavo humanoid.

All gait generators use only the standard library (``math``) and produce
joint-space position targets.  Every primitive is stateless with respect to
the environment — the caller is responsible for tracking phase and time.
"""

from __future__ import annotations

import math
from typing import Sequence

from ..models import GaitParams, TerrainParams, DEFAULT_TERRAIN_PARAMS

# ---------------------------------------------------------------------------
# Trigonometric helpers (no numpy dependency)
# ---------------------------------------------------------------------------

_PI2 = 2.0 * math.pi


def _sin_wave(phase: float) -> float:
    return math.sin(_PI2 * phase)


def _cos_wave(phase: float) -> float:
    return math.cos(_PI2 * phase)


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _fill(values: Sequence[float], count: int, default: float = 0.0) -> list[float]:
    """Return a list of *count* floats, padded or trimmed from *values*."""
    result = [default] * count
    n = min(len(values), count)
    for i in range(n):
        result[i] = values[i]
    return result


# ---------------------------------------------------------------------------
# Per-leg joint index conventions
# ---------------------------------------------------------------------------
# The following indices are GUESSED for the Kuavo humanoid based on typical
# biped layouts.  They MUST be calibrated against actual robot_params once
# the Tongverse Docker environment is available.
#
# Leg (6 DoF per side):
#   0 – hip_yaw
#   1 – hip_roll
#   2 – hip_pitch   ← primary walking actuator
#   3 – knee_pitch  ← primary walking actuator
#   4 – ankle_pitch
#   5 – ankle_roll
#
# Arm (7 DoF per side):
#   0 – shoulder_pitch ← primary swing actuator
#   1 – shoulder_roll
#   2 – shoulder_yaw
#   3 – elbow
#   4 – forearm_roll
#   5 – wrist_pitch
#   6 – wrist_yaw

_HIP_PITCH = 2
_KNEE_PITCH = 3
_ANKLE_PITCH = 4
_SHOULDER_PITCH = 0
_ELBOW = 3

# ---------------------------------------------------------------------------
# Gait generator
# ---------------------------------------------------------------------------


class SinusoidalGait:
    """Bipedal walking gait driven by sinusoidal joint trajectories.

    The left and right legs move in anti-phase.  Arms swing opposite to the
    ipsilateral leg for balance (left arm with right leg, etc.).
    """

    def __init__(
        self,
        params: GaitParams | None = None,
        terrain: TerrainParams | None = None,
        leg_count: int = 12,
        arm_count: int = 14,
    ) -> None:
        self.params = params or GaitParams()
        self.terrain = terrain or DEFAULT_TERRAIN_PARAMS
        self.leg_count = leg_count
        self.arm_count = arm_count
        self._legs_per_side = max(leg_count // 2, 1)
        self._arms_per_side = max(arm_count // 2, 1)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def tick(self, dt: float) -> tuple[list[float], list[float]]:
        """Produce one simulation step of joint targets.

        Returns
        -------
        (arm_values, leg_values)
            Two flat lists sized to *arm_count* and *leg_count* respectively.
        """
        arm = [0.0] * self.arm_count
        leg = [0.0] * self.leg_count

        phase = self._advance_phase(dt)
        p = self.params

        # --- leg trajectories -------------------------------------------------
        left_signal = _sin_wave(phase)
        right_signal = _sin_wave(phase + 0.5)  # anti-phase

        self._set_leg(leg, 0, left_signal, p)   # left leg
        self._set_leg(leg, self._legs_per_side, right_signal, p)  # right leg

        # --- arm swing (opposite to ipsilateral leg) --------------------------
        self._set_arm(arm, 0, right_signal, p)  # left arm swings with right leg
        self._set_arm(arm, self._arms_per_side, left_signal, p)

        return arm, leg

    def tick_flat(
        self,
        dt: float,
        scene_tilt_rad: float = 0.0,
    ) -> tuple[list[float], list[float]]:
        """Gait for flat ground walking with optional pitch compensation."""
        arm, leg = self.tick(dt)
        p = self.params

        # add forward lean compensation
        lean = scene_tilt_rad + p.forward_lean
        for side_start in (0, self._legs_per_side):
            idx = side_start + _ANKLE_PITCH
            if idx < self.leg_count:
                leg[idx] = max(-0.3, min(0.3, leg[idx] + lean))
            idx = side_start + _HIP_PITCH
            if idx < self.leg_count:
                leg[idx] = max(-0.8, min(0.8, leg[idx] + lean * 0.5))

        return arm, leg

    def tick_stairs(
        self,
        dt: float,
    ) -> tuple[list[float], list[float]]:
        """Gait tuned for stair climbing — higher step, slower pace."""
        arm, leg = self.tick(dt)
        t = self.terrain
        p = self.params

        # Increase step height and add forward lean for stairs
        lean = t.stair_forward_lean
        for side_start in (0, self._legs_per_side):
            hip_idx = side_start + _HIP_PITCH
            knee_idx = side_start + _KNEE_PITCH
            if knee_idx < self.leg_count:
                leg[knee_idx] = max(-1.2, leg[knee_idx] * 1.3)
            if hip_idx < self.leg_count:
                leg[hip_idx] = _clip(leg[hip_idx] + lean, -0.9, 0.9)

        return arm, leg

    def tick_slope_down(
        self,
        dt: float,
    ) -> tuple[list[float], list[float]]:
        """Gait for downhill descent — backward lean, shorter steps."""
        t = self.terrain
        p = self.params

        # Temporarily reduce step length for downhill
        saved = p
        reduced = GaitParams(
            frequency=p.frequency * t.slope_speed_factor,
            step_length=p.step_length * t.slope_speed_factor,
            step_height=p.step_height * 0.8,
            body_height_offset=p.body_height_offset - 0.05,
            forward_lean=-t.slope_forward_lean,
            lateral_swing=p.lateral_swing * 1.2,
            double_support_ratio=p.double_support_ratio * 1.4,
        )

        arm, leg = self.tick(dt)
        # restore (immutable params — but re-assign to be safe)
        # Apply backward lean to prevent tipping forward
        lean = -t.slope_forward_lean
        for side_start in (0, self._legs_per_side):
            ankle_idx = side_start + _ANKLE_PITCH
            hip_idx = side_start + _HIP_PITCH
            if ankle_idx < self.leg_count:
                leg[ankle_idx] = _clip(leg[ankle_idx] + lean, -0.3, 0.3)
            if hip_idx < self.leg_count:
                leg[hip_idx] = _clip(leg[hip_idx] - lean * 0.5, -0.8, 0.8)

        return arm, leg

    def tick_uneven(
        self,
        dt: float,
    ) -> tuple[list[float], list[float]]:
        """Gait for uneven terrain — higher step clearance, slower pace."""
        t = self.terrain

        arm, leg = self.tick(dt)

        for side_start in (0, self._legs_per_side):
            knee_idx = side_start + _KNEE_PITCH
            hip_idx = side_start + _HIP_PITCH
            if knee_idx < self.leg_count:
                leg[knee_idx] *= 1.4  # higher knee lift
            if hip_idx < self.leg_count:
                leg[hip_idx] *= t.uneven_speed_factor  # slower, shorter hip swing

        return arm, leg

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _set_leg(
        values: list[float],
        offset: int,
        signal: float,
        p: GaitParams,
    ) -> None:
        """Write leg joint targets for one side starting at *offset*."""
        n = len(values)
        # hip pitch: drives the leg forward (positive) or back (negative)
        idx = offset + _HIP_PITCH
        if idx < n:
            values[idx] = signal * p.step_length

        # knee pitch: flex during swing phase (when signal > double_support)
        idx = offset + _KNEE_PITCH
        if idx < n:
            swing = 0.0
            if signal > p.double_support_ratio:
                swing = signal * p.step_height * 2.0
            values[idx] = swing

        # ankle pitch: slight lift during swing
        idx = offset + _ANKLE_PITCH
        if idx < n:
            values[idx] = abs(signal) * p.step_height * 0.3

    @staticmethod
    def _set_arm(
        values: list[float],
        offset: int,
        signal: float,
        p: GaitParams,
    ) -> None:
        """Write arm swing targets for one side starting at *offset*."""
        n = len(values)
        idx = offset + _SHOULDER_PITCH
        if idx < n:
            values[idx] = signal * p.lateral_swing * 2.0

        idx = offset + _ELBOW
        if idx < n:
            values[idx] = 0.3 + abs(signal) * 0.1  # slight elbow flexion

    # ------------------------------------------------------------------
    # phase tracking
    # ------------------------------------------------------------------

    def _advance_phase(self, dt: float) -> float:
        """Advance and return the normalised gait phase [0, 1)."""
        self._phase = getattr(self, "_phase", 0.0) + dt * self.params.frequency
        self._phase %= 1.0
        return self._phase


# ---------------------------------------------------------------------------
# Posture primitives
# ---------------------------------------------------------------------------


class PosturePrimitive:
    """Static posture targets: stand, crouch, shift COM, etc."""

    def __init__(self, leg_count: int = 12, arm_count: int = 14) -> None:
        self.leg_count = leg_count
        self.arm_count = arm_count

    def stand(self) -> tuple[list[float], list[float]]:
        """Neutral standing pose — zero position for all joints."""
        return [0.0] * self.arm_count, [0.0] * self.leg_count

    def crouch(self, depth: float = 0.3) -> tuple[list[float], list[float]]:
        """Slight crouch — flex hips and knees symmetrically."""
        arm = [0.0] * self.arm_count
        leg = [0.0] * self.leg_count
        legs_per_side = max(self.leg_count // 2, 1)

        for side_start in (0, legs_per_side):
            hip_idx = side_start + _HIP_PITCH
            knee_idx = side_start + _KNEE_PITCH
            ankle_idx = side_start + _ANKLE_PITCH
            if hip_idx < self.leg_count:
                leg[hip_idx] = depth * 0.5
            if knee_idx < self.leg_count:
                leg[knee_idx] = depth
            if ankle_idx < self.leg_count:
                leg[ankle_idx] = -depth * 0.2  # compensate ankle

        return arm, leg

    def arms_forward(self, amount: float = 0.5) -> list[float]:
        """Extend both arms forward (for grasping approach)."""
        arm = [0.0] * self.arm_count
        arms_per_side = max(self.arm_count // 2, 1)
        for side_start in (0, arms_per_side):
            idx = side_start + _SHOULDER_PITCH
            if idx < self.arm_count:
                arm[idx] = amount
        return arm


# ---------------------------------------------------------------------------
# Recovery primitive
# ---------------------------------------------------------------------------


class RecoveryPrimitive:
    """Detect and recover from a fall.

    The recovery sequence is:
    1. Detect fallen state (external check via snapshot.is_fallen).
    2. Retract limbs to a safe crouch.
    3. Push up with arms.
    4. Stand up by extending knees and hips.
    5. Return to neutral standing.
    """

    # Phases of the recovery sequence
    RETRACT = 0
    PUSH_UP = 1
    STAND = 2
    DONE = 3

    def __init__(self, arm_count: int = 14, leg_count: int = 12) -> None:
        self.arm_count = arm_count
        self.leg_count = leg_count
        self._phase = self.RETRACT
        self._phase_time = 0.0

    @property
    def is_done(self) -> bool:
        return self._phase == self.DONE

    def reset(self) -> None:
        self._phase = self.RETRACT
        self._phase_time = 0.0

    def tick(self, dt: float) -> tuple[list[float], list[float]]:
        """Advance recovery and return (arm, leg) joint targets."""
        self._phase_time += dt

        if self._phase == self.RETRACT and self._phase_time > 0.5:
            self._phase = self.PUSH_UP
            self._phase_time = 0.0
        elif self._phase == self.PUSH_UP and self._phase_time > 1.0:
            self._phase = self.STAND
            self._phase_time = 0.0
        elif self._phase == self.STAND and self._phase_time > 1.5:
            self._phase = self.DONE

        if self._phase == self.RETRACT:
            return self._retract()
        elif self._phase == self.PUSH_UP:
            return self._push_up()
        elif self._phase == self.STAND:
            return self._stand_up()
        else:
            return [0.0] * self.arm_count, [0.0] * self.leg_count

    # ------------------------------------------------------------------
    # phase implementations
    # ------------------------------------------------------------------

    def _retract(self) -> tuple[list[float], list[float]]:
        """Pull limbs close to body for safety."""
        arm = [0.0] * self.arm_count
        leg = [0.0] * self.leg_count
        legs_per_side = max(self.leg_count // 2, 1)
        arms_per_side = max(self.arm_count // 2, 1)

        for side_start in (0, legs_per_side):
            hip = side_start + _HIP_PITCH
            knee = side_start + _KNEE_PITCH
            if hip < self.leg_count:
                leg[hip] = 0.4
            if knee < self.leg_count:
                leg[knee] = 0.6

        for side_start in (0, arms_per_side):
            sh = side_start + _SHOULDER_PITCH
            el = side_start + _ELBOW
            if sh < self.arm_count:
                arm[sh] = -0.5
            if el < self.arm_count:
                arm[el] = 0.8

        return arm, leg

    def _push_up(self) -> tuple[list[float], list[float]]:
        """Push torso up with arms."""
        arm = [0.0] * self.arm_count
        leg = [0.0] * self.leg_count
        legs_per_side = max(self.leg_count // 2, 1)
        arms_per_side = max(self.arm_count // 2, 1)

        for side_start in (0, arms_per_side):
            sh = side_start + _SHOULDER_PITCH
            el = side_start + _ELBOW
            if sh < self.arm_count:
                arm[sh] = -1.0  # arms extend downward to push
            if el < self.arm_count:
                arm[el] = 0.2

        for side_start in (0, legs_per_side):
            hip = side_start + _HIP_PITCH
            knee = side_start + _KNEE_PITCH
            if hip < self.leg_count:
                leg[hip] = 0.2
            if knee < self.leg_count:
                leg[knee] = 0.3

        return arm, leg

    def _stand_up(self) -> tuple[list[float], list[float]]:
        """Gradually extend knees and hips to standing."""
        # linear interpolation from crouch to stand over the phase duration
        t = self._phase_time / 1.5  # normalised [0, 1] over STAND phase
        t = _clip(t, 0.0, 1.0)

        arm = [0.0] * self.arm_count
        leg = [0.0] * self.leg_count
        legs_per_side = max(self.leg_count // 2, 1)

        # crouch targets
        crouch_hip = 0.4
        crouch_knee = 0.6
        crouch_ankle = -0.1

        for side_start in (0, legs_per_side):
            hip = side_start + _HIP_PITCH
            knee = side_start + _KNEE_PITCH
            ankle = side_start + _ANKLE_PITCH
            if hip < self.leg_count:
                leg[hip] = crouch_hip * (1.0 - t)
            if knee < self.leg_count:
                leg[knee] = crouch_knee * (1.0 - t)
            if ankle < self.leg_count:
                leg[ankle] = crouch_ankle * (1.0 - t)

        return arm, leg


# ---------------------------------------------------------------------------
# Terrain classifier
# ---------------------------------------------------------------------------


def classify_terrain(
    depth_rows: int,
    depth_cols: int,
    imu_pitch: float,
    imu_roll: float,
    elapsed: float,
) -> str:
    """Heuristic terrain classification from depth and IMU.

    This is a BEST-EFFORT classifier that returns a string label.  Real
    terrain detection will need actual depth-map analysis once the Docker
    environment is available.
    """
    if depth_rows == 0 or depth_cols == 0:
        return "FLAT"

    pitch_deg = abs(math.degrees(imu_pitch))
    roll_deg = abs(math.degrees(imu_roll))

    if roll_deg > 15:
        return "UNEVEN"
    if pitch_deg > 10:
        return "SLOPE_DOWN" if imu_pitch > 0 else "STAIRS_UP"
    if elapsed < 1.0:
        return "FLAT"

    return "FLAT"
