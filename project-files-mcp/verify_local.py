#!/usr/bin/env python3
"""Verify the configured MCP launcher without printing project file contents."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters


PACKAGE = Path(__file__).resolve().parent


async def verify(file_path: str | None) -> dict:
    params = StdioServerParameters(command=sys.executable, args=[str(PACKAGE / "run_mcp.py")])
    async with asyncio.timeout(30):
        async with Client(params, mode="legacy", read_timeout_seconds=10) as client:
            tools = await client.list_tools()
            expected = {"project_info", "list_files", "read_file", "search_text"}
            if {tool.name for tool in tools.tools} != expected:
                raise RuntimeError("Unexpected MCP tool inventory.")
            info = await client.call_tool("project_info", {})
            if info.is_error or not info.structured_content:
                raise RuntimeError("project_info failed.")
            listing = await client.call_tool("list_files", {"limit": 5})
            if listing.is_error:
                raise RuntimeError("list_files failed.")
            for path in ("../outside.txt", ".env"):
                blocked = await client.call_tool("read_file", {"path": path})
                if not blocked.is_error:
                    raise RuntimeError("An excluded path was unexpectedly accepted.")
            output = {"local_mcp": "verified", "project_root": info.structured_content["project_root"],
                      "tools": sorted(expected), "path_restrictions": "verified",
                      "chatgpt_tunnel": "must still be verified from ChatGPT"}
            if file_path:
                result = await client.call_tool("read_file", {"path": file_path, "limit": 100})
                if result.is_error or not result.structured_content:
                    raise RuntimeError("The requested verification file could not be read.")
                output["file"] = {"path": file_path, "sha256": result.structured_content["sha256"]}
            return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="Optional relative UTF-8 file path to verify; contents are not printed")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(verify(args.file)), ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, TimeoutError, OSError) as exc:
        print(f"Local MCP verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
