from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


# ---------------------------------------------------------------------------
# Top-level stages
# ---------------------------------------------------------------------------


class Stage(str, Enum):
    INIT = "INIT"
    NAVIGATE_TERRAIN = "NAVIGATE_TERRAIN"
    SORT_PARTS = "SORT_PARTS"
    MOVE_BOX_TO_SHELF = "MOVE_BOX_TO_SHELF"
    DONE = "DONE"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Sub-stages — fine-grained control within each top-level stage
# ---------------------------------------------------------------------------


class SubStage(str, Enum):
    # Common
    IDLE = "IDLE"
    INITIALIZING = "INITIALIZING"

    # NAVIGATE_TERRAIN sub-chain
    TERRAIN_START = "TERRAIN_START"
    APPROACH_STAIRS = "APPROACH_STAIRS"
    CLIMBING_STAIRS = "CLIMBING_STAIRS"
    POST_STAIRS_TRANSITION = "POST_STAIRS_TRANSITION"
    APPROACH_DOWNHILL = "APPROACH_DOWNHILL"
    DESCENDING_SLOPE = "DESCENDING_SLOPE"
    POST_SLOPE_TRANSITION = "POST_SLOPE_TRANSITION"
    CROSSING_UNEVEN = "CROSSING_UNEVEN"
    TERRAIN_COMPLETE = "TERRAIN_COMPLETE"

    # SORT_PARTS sub-chain
    SORT_START = "SORT_START"
    SCAN_WORKSPACE = "SCAN_WORKSPACE"
    IDENTIFY_TARGET = "IDENTIFY_TARGET"
    APPROACH_PART = "APPROACH_PART"
    GRASP_PART = "GRASP_PART"
    VERIFY_GRASP = "VERIFY_GRASP"
    MOVE_TO_BOX = "MOVE_TO_BOX"
    RELEASE_PART = "RELEASE_PART"
    SORT_COMPLETE = "SORT_COMPLETE"

    # MOVE_BOX_TO_SHELF sub-chain
    BOX_START = "BOX_START"
    APPROACH_BOX = "APPROACH_BOX"
    LIFT_BOX = "LIFT_BOX"
    NAVIGATE_TO_SHELF = "NAVIGATE_TO_SHELF"
    ALIGN_SHELF = "ALIGN_SHELF"
    PLACE_BOX = "PLACE_BOX"
    STABILIZE = "STABILIZE"
    BOX_COMPLETE = "BOX_COMPLETE"

    # Recovery / failure sub-states
    FALL_RECOVERY = "FALL_RECOVERY"
    TIMEOUT_ABORT = "TIMEOUT_ABORT"
    SKIP_CURRENT = "SKIP_CURRENT"


# ---------------------------------------------------------------------------
# Terrain type classification
# ---------------------------------------------------------------------------


class TerrainType(str, Enum):
    FLAT = "FLAT"
    STAIRS_UP = "STAIRS_UP"
    SLOPE_DOWN = "SLOPE_DOWN"
    UNEVEN = "UNEVEN"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Gait parameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GaitParams:
    """Parameters for sinusoidal walking-gait generation.

    All values are expressed in a unit-less control space; scaling to
    joint radians is the responsibility of the action factory.
    """

    frequency: float = 1.5
    step_length: float = 0.35
    step_height: float = 0.15
    body_height_offset: float = 0.0
    lateral_swing: float = 0.05
    forward_lean: float = 0.0
    double_support_ratio: float = 0.1

    def validate(self) -> None:
        if self.frequency <= 0:
            raise ValueError("frequency must be positive")
        if self.step_length < 0:
            raise ValueError("step_length must be non-negative")
        if not 0 <= self.double_support_ratio < 0.5:
            raise ValueError("double_support_ratio must be in [0, 0.5)")


@dataclass(frozen=True)
class TerrainParams:
    """Terrain-specific parameter overrides."""

    stair_step_height: float = 0.12
    stair_step_depth: float = 0.25
    stair_forward_lean: float = 0.15

    slope_angle_deg: float = 15.0
    slope_forward_lean: float = 0.20
    slope_speed_factor: float = 0.6

    uneven_step_reduction: float = 0.5
    uneven_step_height_increase: float = 0.08
    uneven_speed_factor: float = 0.4

    @property
    def slope_angle_rad(self) -> float:
        return math.radians(self.slope_angle_deg)


DEFAULT_TERRAIN_PARAMS = TerrainParams()


# ---------------------------------------------------------------------------
# Observation snapshot (extended)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SceneSnapshot:
    task_id: str | None
    elapsed_minutes: float
    info: str

    # scores and goals
    scores: Mapping[str, Any] = field(default_factory=dict)
    task_goal: Mapping[str, Any] = field(default_factory=dict)

    # robot body state
    robot_position: tuple[float, ...] = ()
    robot_orientation: tuple[float, ...] = ()
    robot_velocity: tuple[float, ...] = ()

    # IMU-derived attitude (radians) — pitch > 0 means robot tilts forward
    imu_pitch: float = 0.0
    imu_roll: float = 0.0

    # foot contact — True when foot is in contact with ground
    left_foot_contact: bool = True
    right_foot_contact: bool = True

    # manipulation
    is_holding_object: bool = False
    held_object_name: str = ""

    # camera availability / dimensions
    has_rgb: bool = False
    has_depth: bool = False
    rgb_shape: tuple[int, int] = (0, 0)
    depth_shape: tuple[int, int] = (0, 0)

    # convenience
    @property
    def is_fallen(self) -> bool:
        """Heuristic: robot is likely fallen if pitch or roll exceeds ~60 deg."""
        fall_threshold = math.radians(60.0)
        return abs(self.imu_pitch) > fall_threshold or abs(self.imu_roll) > fall_threshold

    @property
    def robot_has_ground_contact(self) -> bool:
        return self.left_foot_contact or self.right_foot_contact


# ---------------------------------------------------------------------------
# Planner output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanDecision:
    stage: Stage
    reason: str
    sub_stage: SubStage = SubStage.IDLE
    terrain: TerrainType = TerrainType.UNKNOWN
    needs_recovery: bool = False
    retry_count: int = 0
    part_picked_count: int = 0
    part_target_count: int = 3
    failure_reason: str = ""


# ---------------------------------------------------------------------------
# Telemetry record (writable, not frozen)
# ---------------------------------------------------------------------------


@dataclass
class TelemetryRecord:
    action_index: int
    elapsed_minutes: float
    stage: Stage
    sub_stage: SubStage
    reason: str
    joint_count: int
    pick_command: str | None
    fall_detected: bool
    extra: Mapping[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Episode context — merged from task_params + observation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EpisodeContext:
    """Normalized per-episode context from ``task_params`` and first observation.

    This is the single source of truth for the planner.  Fields that cannot
    be determined from the available data default to safe values.
    """

    task_id: str = ""
    target_part_type: str = ""   # "A", "B", "C", etc.
    target_part_count: int = 3
    max_episode_minutes: float = 20.0

    @classmethod
    def from_params(
        cls,
        task_params: Mapping[str, Any],
        task_id: str | None = None,
    ) -> EpisodeContext:
        """Build context from the launcher-provided *task_params* dict."""
        params = dict(task_params) if isinstance(task_params, Mapping) else {}
        goal = params.get("task_goal") if isinstance(params.get("task_goal"), Mapping) else {}
        return cls(
            task_id=task_id or "",
            target_part_type=str(goal.get("type", "")),
            target_part_count=_safe_int(goal.get("count"), 3),
            max_episode_minutes=_safe_float(params.get("max_episode_minutes"), 20.0),
        )

    def merge_observation(self, task_id: str | None, task_goal: Mapping[str, Any]) -> EpisodeContext:
        """Return a new context enriched with per-frame observation fields."""
        new_task_id = task_id or self.task_id
        goal = dict(task_goal) if isinstance(task_goal, Mapping) else {}
        return EpisodeContext(
            task_id=new_task_id,
            target_part_type=str(goal.get("type", self.target_part_type)) or self.target_part_type,
            target_part_count=_safe_int(goal.get("count"), self.target_part_count),
            max_episode_minutes=self.max_episode_minutes,
        )


# ---------------------------------------------------------------------------
# Structured completion / failure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompletionStatus:
    """Structured result of a sub-stage completion check.

    This replaces a bare boolean so that each completion (or non-completion)
    carries a human-readable reason that can be logged and audited.
    """

    is_complete: bool
    reason: str = ""
    is_timeout: bool = False

    @classmethod
    def done(cls, reason: str) -> CompletionStatus:
        return cls(is_complete=True, reason=reason)

    @classmethod
    def not_yet(cls, reason: str = "") -> CompletionStatus:
        return cls(is_complete=False, reason=reason)

    @classmethod
    def timeout(cls, reason: str) -> CompletionStatus:
        return cls(is_complete=True, reason=reason, is_timeout=True)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
