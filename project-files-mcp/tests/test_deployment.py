"""Checks for credential forwarding and path handling in the local launcher."""
from pathlib import Path
import shlex
import unittest

from connect_tunnel import init_command, mcp_command
from run_mcp import child_environment, SECRET_ENV_NAMES


class DeploymentTests(unittest.TestCase):
    def test_mcp_child_does_not_receive_tunnel_or_openai_keys(self):
        original = {key: "test-secret" for key in SECRET_ENV_NAMES}
        original.update({"PATH": "/usr/bin", "PYTHONPATH": "/unrelated", "PROJECT_ROOT": "/old"})
        result = child_environment("/new project", original)
        for key in SECRET_ENV_NAMES:
            self.assertNotIn(key, result)
        self.assertNotIn("PYTHONPATH", result)
        self.assertEqual(result["PROJECT_ROOT"], "/new project")
        self.assertEqual(result["PATH"], "/usr/bin")
        self.assertEqual(original["CONTROL_PLANE_API_KEY"], "test-secret")

    def test_command_preserves_spaces_and_shell_metacharacters_as_path(self):
        package = Path("/tmp/project's files/$(not-a-command)")
        python = "/tmp/python env/bin/python"
        self.assertEqual(shlex.split(mcp_command(package, python)), [python, str(package / "run_mcp.py")])

    def test_profile_stores_environment_reference_not_key(self):
        args = init_command(Path("/bin/tunnel-client"), Path("/tmp/private profile"),
                            "tunnel_test", "python run_mcp.py")
        self.assertIn("env:CONTROL_PLANE_API_KEY", args)
        self.assertEqual(args[args.index("--profile-dir") + 1], "/tmp/private profile")
        self.assertEqual(args[args.index("--health-listen-addr") + 1], "127.0.0.1:0")


if __name__ == "__main__":
    unittest.main()
