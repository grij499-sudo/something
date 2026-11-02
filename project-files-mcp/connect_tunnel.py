#!/usr/bin/env python3
"""Attach an existing OpenAI tunnel to this package; never create one implicitly."""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


PACKAGE = Path(__file__).resolve().parent


def mcp_command(package: Path, python: str) -> str:
    return shlex.join([python, str(package / "run_mcp.py")])


def init_command(client: Path, profile_dir: Path, tunnel_id: str, command: str) -> list[str]:
    return [str(client), "init", "--sample", "sample_mcp_stdio_local",
            "--profile", "project-files", "--profile-dir", str(profile_dir),
            "--tunnel-id", tunnel_id, "--mcp-command", command,
            "--control-plane-api-key-ref", "env:CONTROL_PLANE_API_KEY",
            "--health-listen-addr", "127.0.0.1:0", "--force"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect a configured local project through an existing Secure MCP Tunnel.")
    parser.add_argument("--tunnel-id", required=True, help="The real tunnel_id from the Platform tunnel settings")
    args = parser.parse_args()
    if not re.fullmatch(r"tunnel_[A-Za-z0-9_-]+", args.tunnel_id):
        parser.error("Provide an actual tunnel_id beginning with tunnel_.")
    if not (PACKAGE / ".local" / "project.json").is_file():
        parser.error("Run setup_local.py first.")
    client = PACKAGE / ".local" / "bin" / "tunnel-client"
    if not client.is_file():
        parser.error("Run python3 install_tunnel.py first.")
    python = PACKAGE / ".venv" / "bin" / "python"
    if not python.is_file():
        parser.error("The local Python environment is missing; rerun setup_local.py.")

    environment = dict(os.environ)
    key = environment.get("CONTROL_PLANE_API_KEY", "").strip()
    if not key:
        if not sys.stdin.isatty():
            parser.error("Use an interactive local terminal for the private key prompt, or set CONTROL_PLANE_API_KEY securely.")
        key = getpass.getpass("Tunnel runtime API key (hidden input; not saved): ").strip()
    if not key:
        parser.error("A runtime API key is required.")
    environment["CONTROL_PLANE_API_KEY"] = key
    del key

    profile_dir = PACKAGE / ".local" / "tunnels" / args.tunnel_id
    profile_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    command = mcp_command(PACKAGE, str(python))
    subprocess.run(init_command(client, profile_dir, args.tunnel_id, command),
                   env=environment, check=True)
    common = ["--profile", "project-files", "--profile-dir", str(profile_dir)]
    subprocess.run([str(client), "doctor", *common, "--explain"], env=environment, check=True)
    print("Starting the tunnel in this terminal. Keep it open; Ctrl+C disconnects it.", flush=True)
    print("Next: select this Tunnel in ChatGPT and call project_info. Local checks alone do not verify the web connection.", flush=True)
    # Replace this foreground process so Ctrl+C is delivered to tunnel-client directly.
    os.execve(str(client), [str(client), "run", *common], environment)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Tunnel setup stopped (exit {exc.returncode}); no connected state is assumed.", file=sys.stderr)
        raise SystemExit(exc.returncode)
