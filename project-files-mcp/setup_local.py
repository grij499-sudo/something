#!/usr/bin/env python3
"""Install this package beside, rather than inside, the selected project."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


PACKAGE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure one project and install the local MCP dependencies.")
    parser.add_argument("--project", required=True, help="Absolute path of the intended project directory")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required.")
    if platform.system() != "Linux":
        parser.error("This deployment package is validated for Linux.")
    root = Path(args.project).expanduser()
    if not root.is_absolute():
        parser.error("--project must be an absolute path.")

    from project_files import ProjectFiles, ProjectFileError
    try:
        access = ProjectFiles(root)
        actual = access.root
        access.close()
    except (OSError, ProjectFileError) as exc:
        parser.error(str(exc))

    python = PACKAGE / ".venv" / "bin" / "python"
    if not python.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(PACKAGE / ".venv")], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "-r", str(PACKAGE / "requirements.txt")], check=True)

    state = PACKAGE / ".local"
    state.mkdir(mode=0o700, exist_ok=True)
    config = {"project_root": str(actual), "schema_version": 1}
    descriptor, temporary = tempfile.mkstemp(prefix="project-", suffix=".json", dir=state)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(config, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, state / "project.json")
    finally:
        Path(temporary).unlink(missing_ok=True)

    print(json.dumps({"local_configuration": "ready", "project_root": str(actual),
                      "python": str(python), "chatgpt_connection": "not yet verified"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Dependency installation failed (exit {exc.returncode}).", file=sys.stderr)
        raise SystemExit(exc.returncode)
