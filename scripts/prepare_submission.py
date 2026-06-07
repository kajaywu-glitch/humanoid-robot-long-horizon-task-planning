from __future__ import annotations

import argparse
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_ROOT = ROOT / "submission"


def git_commit() -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "uncommitted"


def build_archive(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    excluded_parts = {"__pycache__", ".pytest_cache"}

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SUBMISSION_ROOT.rglob("*")):
            if not path.is_file() or any(part in excluded_parts for part in path.parts):
                continue
            archive.write(path, path.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Tongverse submission archive.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "submission.zip",
    )
    args = parser.parse_args()

    if not (SUBMISSION_ROOT / "task_launcher.py").is_file():
        raise SystemExit("Missing official submission/task_launcher.py")

    build_archive(args.output.resolve())
    print(f"Built {args.output.resolve()}")
    print(f"Commit {git_commit()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

