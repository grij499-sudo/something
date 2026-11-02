#!/usr/bin/env python3
"""Launch the configured stdio MCP server; stdout belongs to the MCP protocol."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


PACKAGE = Path(__file__).resolve().parent
SECRET_ENV_NAMES = (
    "CONTROL_PLANE_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY",
    "OPENAI_ADMIN_KEY", "OPENAI_ADMIN_API_KEY",
)


def child_environment(root: str, source: dict[str, str]) -> dict[str, str]:
    environment = dict(source)
    for name in SECRET_ENV_NAMES:
        environment.pop(name, None)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PROJECT_ROOT"] = root
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


def main() -> int:
    try:
        config = json.loads((PACKAGE / ".local" / "project.json").read_text(encoding="utf-8"))
        root = config["project_root"]
        if not isinstance(root, str) or not Path(root).is_absolute():
            raise ValueError("Invalid project_root")
    except (OSError, ValueError, KeyError, TypeError):
        print("Run setup_local.py --project /absolute/project/path first.", file=sys.stderr)
        return 2
    python = PACKAGE / ".venv" / "bin" / "python"
    if not python.is_file():
        print("Local Python environment is missing; rerun setup_local.py.", file=sys.stderr)
        return 2
    os.execve(str(python), [str(python), str(PACKAGE / "server.py")],
              child_environment(root, dict(os.environ)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
