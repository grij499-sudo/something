from __future__ import annotations

from pathlib import Path
import asyncio
import sys
import tempfile
import unittest

from mcp import Client, StdioServerParameters
from server import build_server


class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        (self.root / "README.md").write_text("protocol-check-20261102\n", encoding="utf-8")
        (self.root / ".env").write_text("must-not-read")

    async def assert_workflow(self, client):
        listing = await client.list_tools()
        self.assertEqual({t.name for t in listing.tools}, {"project_info", "list_files", "read_file", "search_text"})
        self.assertTrue(all(t.annotations.read_only_hint for t in listing.tools))
        info = await client.call_tool("project_info", {})
        self.assertFalse(info.is_error)
        self.assertEqual(info.structured_content["project_root"], str(self.root))
        result = await client.call_tool("read_file", {"path": "README.md"})
        self.assertFalse(result.is_error)
        self.assertIn("protocol-check-20261102", result.structured_content["content"])
        blocked = await client.call_tool("read_file", {"path": ".env"})
        self.assertTrue(blocked.is_error)
        invalid = await client.call_tool("list_files", {"limit": 201})
        self.assertTrue(invalid.is_error)
        matches = await client.call_tool("search_text", {"query": "protocol-check"})
        self.assertFalse(matches.is_error)
        self.assertEqual(matches.structured_content["matches"][0]["path"], "README.md")

    async def test_in_memory_sdk_contract(self):
        async with asyncio.timeout(15):
            async with Client(build_server(str(self.root)), raise_exceptions=True, read_timeout_seconds=5) as client:
                await self.assert_workflow(client)

    async def test_real_stdio_auto_and_legacy_clients(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).resolve().parents[1] / "server.py")],
            env={"PROJECT_ROOT": str(self.root)},
        )
        for mode in ("auto", "legacy"):
            with self.subTest(mode=mode):
                async with asyncio.timeout(20):
                    async with Client(params, mode=mode, read_timeout_seconds=5) as client:
                        await self.assert_workflow(client)


if __name__ == "__main__":
    unittest.main()
