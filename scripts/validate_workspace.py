from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_LAUNCHER_SHA256 = "77de5eefa047ec5a1e764eda9c2bb80cdb6b93d8ad997b0adfcb546ae18f3abd"
REQUIRED_PATHS = (
    "AGENTS.md",
    "README.md",
    "docs/decision_log.md",
    "docs/agent_handoff.md",
    "docs/experiment_log.md",
    "submission/task_launcher.py",
    "submission/task_solver/task_solver.py",
    "tests/test_task_solver.py",
)


def validate_required_paths(errors: list[str]) -> None:
    for relative_path in REQUIRED_PATHS:
        if not (ROOT / relative_path).is_file():
            errors.append(f"missing required file: {relative_path}")


def validate_official_launcher(errors: list[str]) -> None:
    launcher = ROOT / "submission" / "task_launcher.py"
    if not launcher.is_file():
        return
    digest = hashlib.sha256(launcher.read_bytes()).hexdigest()
    if digest != OFFICIAL_LAUNCHER_SHA256:
        errors.append("submission/task_launcher.py differs from the pinned official version")


def validate_solver_imports(errors: list[str]) -> None:
    solver_root = ROOT / "submission" / "task_solver"
    for path in solver_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if module == "tongverse" or module.startswith("tongverse."):
                    errors.append(
                        f"{path.relative_to(ROOT)} imports simulator internals: {module}"
                    )


def validate_smoke_action(errors: list[str]) -> None:
    sys.path.insert(0, str(ROOT))
    from submission.task_solver.control.actions import validate_action
    from submission.task_solver.task_solver import TaskSolver

    solver = TaskSolver(
        task_params={},
        agent_params={
            "arm_idx": list(range(14)),
            "leg_idx": list(range(12)),
            "head_idx": list(range(2)),
        },
    )
    action = solver.next_action(
        {"extras": {"Current_Task_ID": "TaskTwo", "time(minutes)": 0, "info": ""}}
    )
    try:
        validate_action(action)
    except ValueError as exc:
        errors.append(f"smoke action is invalid: {exc}")


def main() -> int:
    errors: list[str] = []
    validate_required_paths(errors)
    validate_official_launcher(errors)
    validate_solver_imports(errors)
    validate_smoke_action(errors)

    if errors:
        print("Workspace validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Workspace validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

