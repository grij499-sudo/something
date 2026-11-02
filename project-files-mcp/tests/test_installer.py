"""Offline checks for release selection and archive installation boundaries."""

import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_tunnel as installer


def release(arch="amd64", payload=b"abc"):
    tag = "v0.0.19"
    name = f"tunnel-client-{tag}-linux-{arch}.zip"
    return {"tag_name": tag, "assets": [{
        "name": name,
        "browser_download_url": f"https://github.com/openai/tunnel-client/releases/download/{tag}/{name}",
        "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
    }]}


def elf(arch="amd64"):
    data = bytearray(64)
    data[:6] = b"\x7fELF\x02\x01"
    data[18:20] = {"amd64": 62, "arm64": 183}[arch].to_bytes(2, "little")
    return bytes(data)


class InstallerTests(unittest.TestCase):
    def test_architecture_selection(self):
        self.assertEqual(installer.linux_arch("Linux", "x86_64"), "amd64")
        self.assertEqual(installer.linux_arch("Linux", "aarch64"), "arm64")
        for system, machine in [("Darwin", "arm64"), ("Linux", "i686")]:
            with self.assertRaises(installer.InstallError):
                installer.linux_arch(system, machine)

    def test_exact_client_asset_selection(self):
        metadata = release()
        metadata["assets"].append({"name": "runtime-v0.0.19-linux-amd64.zip"})
        self.assertEqual(installer.select_asset(metadata, "amd64").name,
                         "tunnel-client-v0.0.19-linux-amd64.zip")
        with self.assertRaises(installer.InstallError):
            installer.select_asset(metadata, "arm64")
        metadata["assets"].append(metadata["assets"][0].copy())
        with self.assertRaises(installer.InstallError):
            installer.select_asset(metadata, "amd64")

    def test_metadata_digest_size_and_url_required(self):
        for key, value in [("digest", None), ("digest", "sha256:bad"),
                           ("size", True), ("size", installer.MAX_ZIP_BYTES + 1),
                           ("browser_download_url", "https://example.com/client.zip")]:
            with self.subTest(key=key, value=value):
                metadata = release()
                metadata["assets"][0][key] = value
                with self.assertRaises(installer.InstallError):
                    installer.select_asset(metadata, "amd64")

    def test_tag_injection_rejected(self):
        metadata = release()
        metadata["tag_name"] = "v0.0.19/../../escape"
        with self.assertRaises(installer.InstallError):
            installer.select_asset(metadata, "amd64")

    def test_redirect_destinations_constrained(self):
        installer.validate_https("https://release-assets.githubusercontent.com/a?signature=x", installer.DOWNLOAD_HOSTS)
        for url in ["http://github.com/a", "https://github.com.evil.test/a",
                    "https://github.com@evil.test/a", "https://user:pass@github.com/a",
                    "https://github.com:444/a", "https://raw.githubusercontent.com/a"]:
            with self.subTest(url=url), self.assertRaises(installer.InstallError):
                installer.validate_https(url, installer.DOWNLOAD_HOSTS)

    def test_download_length_and_digest_verified(self):
        payload = b"abcdef"
        for actual, succeeds in [(payload, True), (b"abcdeX", False), (b"abc", False), (payload + b"x", False)]:
            with self.subTest(actual=actual), tempfile.TemporaryDirectory() as directory:
                asset = installer.select_asset(release(payload=payload), "amd64")
                with patch.object(installer, "open_official", return_value=io.BytesIO(actual)):
                    if succeeds:
                        destination = Path(directory) / "archive.zip"
                        installer.download_verified(asset, destination)
                        self.assertEqual(destination.read_bytes(), payload)
                    else:
                        with self.assertRaises(installer.InstallError):
                            installer.download_verified(asset, Path(directory) / "archive.zip")

    def make_archive(self, directory, entries):
        path = Path(directory) / "client.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in entries:
                archive.writestr(name, data)
        return path

    def test_only_client_extracted(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_archive(directory, [("dist/tunnel-client", elf()), ("README.md", b"ignored")])
            destination = Path(directory) / "installed"
            digest = installer.extract_binary(source, destination, "amd64")
            self.assertEqual(destination.read_bytes(), elf())
            self.assertEqual(digest, hashlib.sha256(elf()).hexdigest())
            self.assertFalse((Path(directory) / "README.md").exists())

    def test_unsafe_archive_paths_rejected(self):
        for name in ["../escape", "/absolute", "folder/../escape", "C:/escape", "a\\escape"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                source = self.make_archive(directory, [("tunnel-client", elf()), (name, b"x")])
                with self.assertRaises(installer.InstallError):
                    installer.extract_binary(source, Path(directory) / "installed", "amd64")

    def test_symlink_archive_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            link = zipfile.ZipInfo("tunnel-client")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            source = self.make_archive(directory, [(link, b"/etc/passwd")])
            with self.assertRaises(installer.InstallError):
                installer.extract_binary(source, Path(directory) / "installed", "amd64")

    def test_ambiguous_or_wrong_architecture_binary_rejected(self):
        for entries in [[("one/tunnel-client", elf()), ("two/tunnel-client", elf())],
                        [("tunnel-client", elf("arm64"))], [("tunnel-client", b"not an executable")]]:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as directory:
                source = self.make_archive(directory, entries)
                with self.assertRaises(installer.InstallError):
                    installer.extract_binary(source, Path(directory) / "installed", "amd64")

    def test_installation_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "real"
            target.mkdir()
            link = base / "linked"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(installer.InstallError):
                installer.ensure_real_directory(link)
            with self.assertRaises(installer.InstallError):
                installer.refuse_symlink(link)

    def test_failed_download_preserves_existing_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            binary_dir = base / ".local" / "bin"
            binary_dir.mkdir(parents=True)
            binary = binary_dir / "tunnel-client"
            binary.write_bytes(b"previous verified client")
            with patch.object(installer, "__file__", str(base / "install_tunnel.py")), \
                 patch.object(installer, "latest_release", return_value=release()), \
                 patch.object(installer.platform, "system", return_value="Linux"), \
                 patch.object(installer.platform, "machine", return_value="x86_64"), \
                 patch.object(installer, "download_verified", side_effect=installer.InstallError("bad digest")):
                with self.assertRaises(installer.InstallError):
                    installer.install()
            self.assertEqual(binary.read_bytes(), b"previous verified client")


if __name__ == "__main__":
    unittest.main()
