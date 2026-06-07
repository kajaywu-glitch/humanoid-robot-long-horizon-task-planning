from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..models import EpisodeContext, SceneSnapshot


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _tuple_of_floats(value: Any) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    try:
        return tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return ()


def _bool_or(value: Any, default: bool) -> bool:
    try:
        return bool(value)
    except (TypeError, ValueError):
        return default


def _str_or(value: Any, default: str) -> str:
    if value is None:
        return default
    try:
        return str(value)
    except (TypeError, ValueError):
        return default


def _shape_from_image(image: Any) -> tuple[int, int]:
    """Best-effort extraction of (height, width) from a nested sequence or
    array-like image buffer."""
    if not isinstance(image, Sequence) or isinstance(image, (str, bytes)):
        return (0, 0)
    try:
        # Try 2D shape: rows of columns
        if len(image) > 0 and isinstance(image[0], Sequence) and not isinstance(image[0], (str, bytes)):
            return (len(image), len(image[0]))
        # Treat as 1D buffer — caller will need to know actual shape
        return (len(image), 1)
    except (TypeError, IndexError):
        return (0, 0)


class ObservationParser:
    """Parse a raw Tongverse observation dict into a safe :class:`SceneSnapshot`.

    Every field that is missing or unreadable is replaced with a well-defined
    default so that downstream planners and controllers never crash on
    incomplete observations.

    When *episode_context* is provided, task-level fields (part type, count)
    are merged into the snapshot's ``task_goal`` so the planner has a single
    source of truth regardless of whether the launcher communicates targets
    through ``task_params`` or per-frame observation.
    """

    def parse(
        self,
        obs: Mapping[str, Any] | None,
        episode_context: EpisodeContext | None = None,
    ) -> SceneSnapshot:
        observation = _mapping(obs)
        extras = _mapping(observation.get("extras"))
        robot = _mapping(observation.get("Kuavo"))
        body_state = _mapping(robot.get("body_state"))
        imu = _mapping(robot.get("imu"))
        feet = _mapping(robot.get("feet"))
        camera = _mapping(observation.get("camera"))

        elapsed = self._parse_elapsed(extras)
        task_id = self._parse_task_id(extras)
        task_goal = _mapping(extras.get("task_goal"))

        # Merge episode-level params into task_goal so the planner sees them
        # even when the environment only delivers them via task_params.
        if episode_context is not None:
            merged = dict(task_goal)
            if not merged.get("type") and episode_context.target_part_type:
                merged["type"] = episode_context.target_part_type
            if not merged.get("count") and episode_context.target_part_count:
                merged["count"] = episode_context.target_part_count
            task_goal = merged

        return SceneSnapshot(
            task_id=task_id,
            elapsed_minutes=elapsed,
            info=str(extras.get("info") or ""),
            scores=_mapping(extras.get("scores")),
            task_goal=task_goal,
            robot_position=_tuple_of_floats(body_state.get("world_position")),
            robot_orientation=_tuple_of_floats(body_state.get("world_orient")),
            robot_velocity=_tuple_of_floats(body_state.get("world_velocity")),
            imu_pitch=self._safe_float(imu.get("pitch"), 0.0),
            imu_roll=self._safe_float(imu.get("roll"), 0.0),
            left_foot_contact=_bool_or(feet.get("left_contact"), True),
            right_foot_contact=_bool_or(feet.get("right_contact"), True),
            is_holding_object=bool(observation.get("pick", False)),
            held_object_name=_str_or(observation.get("held_object"), ""),
            has_rgb=camera.get("rgb") is not None,
            has_depth=camera.get("depth") is not None,
            rgb_shape=_shape_from_image(camera.get("rgb")),
            depth_shape=_shape_from_image(camera.get("depth")),
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_elapsed(extras: Mapping[str, Any]) -> float:
        try:
            return float(extras.get("time(minutes)", 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _parse_task_id(extras: Mapping[str, Any]) -> str | None:
        raw = extras.get("Current_Task_ID")
        return str(raw) if raw is not None else None

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
