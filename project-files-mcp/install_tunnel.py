#!/usr/bin/env python3
"""Install the official Linux tunnel-client into this package's .local/bin.

Only unauthenticated HTTPS requests are made. No tunnel, key, or system service
is created. The release API digest is checked before any executable is installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


LATEST_URL = "https://api.github.com/repos/openai/tunnel-client/releases/latest"
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_ZIP_BYTES = 128 * 1024 * 1024
MAX_BINARY_BYTES = 256 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 180
DOWNLOAD_HOSTS = frozenset({
    "github.com", "release-assets.githubusercontent.com",
    "objects.githubusercontent.com", "github-releases.githubusercontent.com",
})


class InstallError(RuntimeError):
    """A validation or installation failure safe to report without credentials."""


@dataclass(frozen=True)
class Asset:
    version: str
    arch: str
    name: str
    url: str
    sha256: str
    size: int


def linux_arch(system: str, machine: str) -> str:
    if system != "Linux":
        raise InstallError("This installer supports Linux only.")
    aliases = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
    if machine.lower() not in aliases:
        raise InstallError("Unsupported Linux architecture: " + machine)
    return aliases[machine.lower()]


def validate_https(url: str, hosts: frozenset[str]) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (parsed.scheme == "https" and parsed.hostname in hosts
                 and parsed.port in (None, 443) and parsed.username is None
                 and parsed.password is None and not parsed.fragment)
    except ValueError as exc:
        raise InstallError("Invalid download URL.") from exc
    if not valid:
        raise InstallError("Refused non-official or non-HTTPS download location.")


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def __init__(self, hosts: frozenset[str]):
        super().__init__()
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_https(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_official(url: str, hosts: frozenset[str]):
    validate_https(url, hosts)
    request = urllib.request.Request(url, headers={
        "User-Agent": "project-files-mcp-installer/1",
        "Accept-Encoding": "identity",
    })
    opener = urllib.request.build_opener(OfficialRedirects(hosts))
    response = opener.open(request, timeout=30)
    validate_https(response.geturl(), hosts)
    return response


def latest_release() -> dict:
    with open_official(LATEST_URL, frozenset({"api.github.com"})) as response:
        payload = response.read(MAX_METADATA_BYTES + 1)
    if len(payload) > MAX_METADATA_BYTES:
        raise InstallError("Release metadata exceeds the size limit.")
    try:
        release = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise InstallError("Release metadata is not valid JSON.") from exc
    if not isinstance(release, dict):
        raise InstallError("Release metadata is not an object.")
    return release


def select_asset(release: dict, arch: str) -> Asset:
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", tag):
        raise InstallError("Unexpected release tag; inspect the official release manually.")
    if arch not in {"amd64", "arm64"}:
        raise InstallError("Unsupported architecture.")
    name = f"tunnel-client-{tag}-linux-{arch}.zip"
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise InstallError("Release has no asset list.")
    matches = [item for item in assets if isinstance(item, dict) and item.get("name") == name]
    if len(matches) != 1:
        raise InstallError("Official release must contain exactly one matching asset: " + name)
    entry = matches[0]
    expected_url = f"https://github.com/openai/tunnel-client/releases/download/{tag}/{name}"
    if entry.get("browser_download_url") != expected_url:
        raise InstallError("Asset URL does not match the official repository and release.")
    digest = entry.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise InstallError("Official API SHA256 digest is missing; installation stopped.")
    size = entry.get("size")
    if type(size) is not int or not 0 < size <= MAX_ZIP_BYTES:
        raise InstallError("Asset size is missing or exceeds the download limit.")
    return Asset(tag, arch, name, expected_url, digest[7:].lower(), size)


def download_verified(asset: Asset, destination: Path) -> None:
    digest = hashlib.sha256()
    total = 0
    deadline = time.monotonic() + MAX_DOWNLOAD_SECONDS
    with open_official(asset.url, DOWNLOAD_HOSTS) as response, destination.open("xb") as output:
        while True:
            if time.monotonic() > deadline:
                raise InstallError("Asset download exceeded the time limit.")
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > min(asset.size, MAX_ZIP_BYTES):
                raise InstallError("Downloaded asset exceeds the expected size.")
            output.write(chunk)
            digest.update(chunk)
    if total != asset.size:
        raise InstallError("Downloaded asset length does not match official metadata.")
    if digest.hexdigest() != asset.sha256:
        raise InstallError("Downloaded asset failed the official SHA256 check.")


def validate_elf(header: bytes, arch: str) -> None:
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[4:6] != b"\x02\x01":
        raise InstallError("Archive does not contain a 64-bit little-endian Linux ELF binary.")
    expected_machine = {"amd64": 62, "arm64": 183}[arch]
    if int.from_bytes(header[18:20], "little") != expected_machine:
        raise InstallError("Binary architecture does not match this host.")


def extract_binary(archive_path: Path, destination: Path, arch: str) -> str:
    """Read one validated regular member; never extract archive paths."""
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > 64:
            raise InstallError("Unexpected number of archive members.")
        candidates = []
        for member in members:
            name = member.orig_filename
            parts = name.rstrip("/").split("/")
            if (not name or name.startswith("/") or "\\" in name or "\x00" in name
                    or ":" in name or any(p in {"", ".", ".."} for p in parts)):
                raise InstallError("Archive contains an unsafe member path.")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise InstallError("Archive contains a symbolic link.")
            if not member.is_dir() and PurePosixPath(name).name == "tunnel-client":
                if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                    raise InstallError("Client archive member is not a regular file.")
                candidates.append(member)
        if len(candidates) != 1:
            raise InstallError("Archive must contain exactly one tunnel-client executable.")
        member = candidates[0]
        if not 20 <= member.file_size <= MAX_BINARY_BYTES:
            raise InstallError("Executable exceeds the allowed size or is incomplete.")
        if member.flag_bits & 1:
            raise InstallError("Encrypted executable archives are not supported.")
        digest = hashlib.sha256()
        total = 0
        with archive.open(member) as source, destination.open("xb") as output:
            first = source.read(64 * 1024)
            validate_elf(first, arch)
            chunk = first
            while chunk:
                total += len(chunk)
                if total > min(member.file_size, MAX_BINARY_BYTES):
                    raise InstallError("Executable exceeds its declared size.")
                output.write(chunk)
                digest.update(chunk)
                chunk = source.read(64 * 1024)
        if total != member.file_size:
            raise InstallError("Executable archive member is truncated.")
        return digest.hexdigest()


def ensure_real_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    if path.is_symlink() or not path.is_dir():
        raise InstallError("Installation directory must be a real directory: " + str(path))


def refuse_symlink(path: Path) -> None:
    if path.is_symlink():
        raise InstallError("Refused to replace a symbolic link: " + str(path))
    if path.exists() and not path.is_file():
        raise InstallError("Installation target is not a regular file: " + str(path))


def install() -> dict:
    root = Path(__file__).resolve().parent
    local_dir = root / ".local"
    bin_dir = local_dir / "bin"
    arch = linux_arch(platform.system(), platform.machine())
    asset = select_asset(latest_release(), arch)
    ensure_real_directory(local_dir)
    ensure_real_directory(bin_dir)
    target = bin_dir / "tunnel-client"
    record_path = local_dir / "tunnel-client-install.json"
    refuse_symlink(target)
    refuse_symlink(record_path)
    with tempfile.TemporaryDirectory(prefix="tunnel-install-", dir=local_dir) as temporary:
        temp = Path(temporary)
        archive = temp / "client.zip"
        binary = temp / "tunnel-client"
        download_verified(asset, archive)
        binary_sha = extract_binary(archive, binary, arch)
        binary.chmod(0o755)
        record = {
            "version": asset.version,
            "architecture": arch,
            "asset": asset.name,
            "source_url": asset.url,
            "archive_sha256": asset.sha256,
            "binary_sha256": binary_sha,
            "binary_path": str(target),
            "installed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        staged_record = temp / "installation.json"
        staged_record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        staged_record.chmod(0o600)
        refuse_symlink(target)
        refuse_symlink(record_path)
        os.replace(binary, target)
        os.replace(staged_record, record_path)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = install()
    except urllib.error.HTTPError as exc:
        print(f"Installation failed: official download returned HTTP {exc.code}.", file=sys.stderr)
        return 1
    except urllib.error.URLError:
        print("Installation failed: cannot reach the official HTTPS endpoint. Check network access.", file=sys.stderr)
        return 1
    except (InstallError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        print("Installation failed: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
