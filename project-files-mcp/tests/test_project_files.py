from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from project_files import Limits, ProjectFileError, ProjectFiles


class ProjectFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        self.project = ProjectFiles(self.root)
        self.addCleanup(self.project.close)

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def service_with(self, **overrides) -> ProjectFiles:
        service = ProjectFiles(self.root, limits=replace(Limits(), **overrides))
        self.addCleanup(service.close)
        return service

    def test_configuration_requires_one_explicit_project(self):
        for path in ("", ".", "/", str(Path.home())):
            with self.subTest(path=path), self.assertRaises(ProjectFileError):
                ProjectFiles(path)

    def test_unicode_content_and_stable_paging(self):
        content = "项目版本一\n第二行🌊\n"
        self.write("README.md", content)
        first = self.project.read_file("README.md", limit=5)
        second = self.project.read_file("README.md", offset=first["next_offset"], limit=100,
                                        expected_sha256=first["sha256"])
        self.assertEqual(first["content"] + second["content"], content)
        self.assertEqual(first["sha256"], hashlib.sha256(content.encode()).hexdigest())
        self.assertEqual(second["start_line"], 1)
        self.assertIsNone(second["next_offset"])
        self.write("README.md", "changed")
        with self.assertRaisesRegex(ProjectFileError, "version changed"):
            self.project.read_file("README.md", expected_sha256=first["sha256"])

    def test_long_line_can_be_read_without_losing_remainder(self):
        content = "x" * 80_000
        self.write("long.txt", content)
        parts, offset, expected = [], 0, None
        while offset is not None:
            page = self.project.read_file("long.txt", offset=offset, limit=32_768, expected_sha256=expected)
            parts.append(page["content"])
            expected, offset = page["sha256"], page["next_offset"]
        self.assertEqual("".join(parts), content)

    def test_traversal_absolute_and_windows_paths_are_denied(self):
        self.write("safe.txt", "safe")
        for path in ("../outside.txt", "a/../../outside.txt", str(self.root / "safe.txt"),
                     "a/../safe.txt", "C:\\secret.txt", "a\\..\\secret", "a\x00b", "./safe.txt"):
            with self.subTest(path=path), self.assertRaises(ProjectFileError):
                self.project.read_file(path)

    def test_hidden_and_credential_paths_are_excluded_from_all_tools(self):
        for path in (".env", ".env.local", ".git/config", ".ssh/id_rsa", ".codex/auth.json",
                     "config/secrets.json", "config/credentials.json", "key.pem", "id_ed25519", "private/key.txt"):
            self.write(path, "hidden-needle")
            with self.subTest(path=path), self.assertRaises(ProjectFileError):
                self.project.read_file(path)
        self.write("docs/guide.md", "visible-needle")
        items = self.project.list_files(recursive=True)["entries"]
        self.assertEqual({item["path"] for item in items}, {"config", "docs", "docs/guide.md"})
        self.assertEqual(self.project.search_text("hidden-needle")["matches"], [])
        self.assertEqual(len(self.project.search_text("visible-needle")["matches"]), 1)

    def test_file_directory_symlinks_and_hardlinks_are_denied(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("outside secret")
        (self.root / "linked.txt").symlink_to(secret)
        (self.root / "linked-dir").symlink_to(outside, target_is_directory=True)
        os.link(secret, self.root / "hardlinked.txt")
        for path in ("linked.txt", "linked-dir/secret.txt", "hardlinked.txt"):
            with self.subTest(path=path), self.assertRaises(ProjectFileError):
                self.project.read_file(path)
        self.assertEqual(self.project.list_files(recursive=True)["entries"], [])
        self.assertEqual(self.project.search_text("outside secret")["matches"], [])

    def test_swapping_file_for_symlink_before_open_is_denied(self):
        safe = self.write("safe.txt", "ordinary")
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("secret")
        real_open = os.open
        def racing_open(name, flags, *args, **kwargs):
            if name == "safe.txt":
                safe.unlink()
                safe.symlink_to(outside)
            return real_open(name, flags, *args, **kwargs)
        with patch("project_files.os.open", side_effect=racing_open):
            with self.assertRaises(ProjectFileError):
                self.project.read_file("safe.txt")

    def test_nonregular_binary_private_key_and_large_files_are_rejected(self):
        os.mkfifo(self.root / "pipe.txt")
        (self.root / "binary.dat").write_bytes(b"binary\x00stuff")
        (self.root / "nonutf8.txt").write_bytes(b"\xff\xfe")
        self.write("renamed.txt", "-----BEGIN RSA PRIVATE KEY-----\nnot-a-real-key")
        self.write("large.txt", "x" * (1_048_576 + 1))
        for path in ("pipe.txt", "binary.dat", "nonutf8.txt", "renamed.txt", "large.txt"):
            with self.subTest(path=path), self.assertRaises(ProjectFileError):
                self.project.read_file(path)

    def test_listing_is_paginated_and_reports_inventory_changes(self):
        for name in ("c.txt", "a.txt", "b.txt"):
            self.write(name, name)
        first = self.project.list_files(limit=2)
        second = self.project.list_files(limit=2, offset=first["next_offset"])
        self.assertEqual([item["path"] for item in first["entries"] + second["entries"]],
                         ["a.txt", "b.txt", "c.txt"])
        self.assertEqual(first["inventory_sha256"], second["inventory_sha256"])
        self.write("d.txt", "new")
        self.assertNotEqual(first["inventory_sha256"], self.project.list_files()["inventory_sha256"])

    def test_directory_scan_limit_is_explicit(self):
        for i in range(10):
            self.write(f"f{i}.txt", "needle")
        service = self.service_with(max_scan_entries=3)
        listing = service.list_files()
        self.assertLessEqual(listing["observed_entries"], 3)
        self.assertFalse(listing["scan_complete"])
        self.assertIn("entry_limit", listing["scan_limit_reasons"])
        self.assertTrue(service.search_text("needle")["truncated"])

    def test_literal_search_numbers_case_and_long_unicode_excerpts(self):
        self.write("docs/a.md", "title\nNeedle [a-z]+\nlast\n")
        self.write("docs/b.md", "İ" * 700 + " Needle at end")
        result = self.project.search_text("[a-z]+", "docs")
        self.assertEqual(result["matches"][0]["line"], 2)
        self.assertEqual(len(result["matches"]), 1)
        insensitive = self.project.search_text("needle", "docs", case_sensitive=False)
        self.assertEqual(len(insensitive["matches"]), 2)
        self.assertTrue(all("Needle" in m["excerpt"] for m in insensitive["matches"]))
        self.assertEqual(self.project.search_text("needle", "docs")["matches"], [])

    def test_result_and_byte_limits_include_binary_reads(self):
        self.write("a.txt", "hit\nhit\nhit\n")
        result = self.project.search_text("hit", max_results=2)
        self.assertEqual(len(result["matches"]), 2)
        self.assertIn("result_limit", result["limit_reasons"])
        (self.root / "a.txt").write_bytes(b"\x00" * 20)
        self.write("b.txt", "needle" * 10)
        bounded = self.service_with(max_search_bytes=30)
        result = bounded.search_text("needle")
        self.assertEqual(result["bytes_scanned"], 20)
        self.assertIn("search_byte_limit", result["limit_reasons"])
        self.assertEqual(result["matches"], [])

    def test_invalid_bounds_fail_without_scanning(self):
        with self.assertRaises(ProjectFileError):
            self.project.list_files(limit=201)
        with self.assertRaises(ProjectFileError):
            self.project.read_file("x", limit=32_769)
        with self.assertRaises(ProjectFileError):
            self.project.search_text("", max_results=1)
        with self.assertRaises(ProjectFileError):
            self.project.search_text("x", max_results=101)


if __name__ == "__main__":
    unittest.main()
