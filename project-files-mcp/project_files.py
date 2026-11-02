"""Bounded, read-only project access for a trusted local POSIX directory.

The name policy is deliberately conservative, not a general secret scanner.
The service account and the configured root remain part of the trust boundary.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Iterator
from uuid import uuid4


class ProjectFileError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_request", bytes_read: int = 0):
        super().__init__(message)
        self.code = code
        self.bytes_read = bytes_read


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 1_048_576
    max_read_chars: int = 32_768
    max_list_items: int = 200
    max_scan_entries: int = 5_000
    max_depth: int = 16
    max_search_results: int = 100
    max_search_bytes: int = 8_388_608
    max_query_chars: int = 256
    max_scan_seconds: float = 5.0


_BLOCKED_NAMES = {
    "node_modules", "venv", "env", "__pycache__", "vendor", "dist", "build",
    "secrets", "credentials", "private", "auth.json", "authorized_keys",
    "known_hosts", "kubeconfig", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
}
_BLOCKED_PATTERNS = (
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx",
    "credentials.*", "secrets.*", "secret.*", "tokens.*", "token.*",
    "*credential*", "*password*", "*private_key*", "*private-key*",
    "*service-account*.json", "*service_account*.json",
)
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")


class ProjectFiles:
    """No writes, subprocesses, shell, network calls, or tool-selected roots."""

    def __init__(self, root: str | Path, *, limits: Limits | None = None):
        if not str(root).strip() or not Path(root).is_absolute():
            raise ProjectFileError("PROJECT_ROOT must be an explicit absolute directory.")
        if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
            raise ProjectFileError("This service requires POSIX descriptor-relative file access.")
        try:
            self.root = Path(root).resolve(strict=True)
        except OSError as exc:
            raise ProjectFileError("PROJECT_ROOT is not an accessible directory.") from exc
        if self.root == Path(self.root.anchor) or self.root == Path.home().resolve():
            raise ProjectFileError("Choose a project directory, not the filesystem or home root.")
        self.limits = limits or Limits()
        self.instance_id = uuid4().hex
        try:
            self._root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise ProjectFileError("PROJECT_ROOT is not an accessible directory.") from exc

    def close(self) -> None:
        fd = getattr(self, "_root_fd", None)
        if fd is not None:
            os.close(fd)
            self._root_fd = None

    def __del__(self):
        self.close()

    @staticmethod
    def _name_allowed(name: str) -> bool:
        low = name.casefold()
        return (
            not name.startswith(".")
            and low not in _BLOCKED_NAMES
            and not any(fnmatch.fnmatchcase(low, pattern) for pattern in _BLOCKED_PATTERNS)
        )

    def _parts(self, value: str, *, allow_root: bool = False) -> tuple[str, ...]:
        if not isinstance(value, str) or len(value) > 1024 or "\x00" in value or "\\" in value:
            raise ProjectFileError("Use a short relative POSIX path.")
        if allow_root and value in ("", "."):
            return ()
        path = PurePosixPath(value)
        if not value or path.is_absolute() or re.match(r"^[A-Za-z]:", value):
            raise ProjectFileError("Only paths relative to PROJECT_ROOT are accepted.")
        raw_parts = value.split("/")
        if any(part in ("", ".", "..") for part in raw_parts):
            raise ProjectFileError("Empty components, dot components and traversal are denied.")
        if len(path.parts) > 32 or any(not self._name_allowed(p) for p in path.parts):
            raise ProjectFileError("This path is excluded by the project access policy.", code="denied")
        return path.parts

    @staticmethod
    def _bounded_int(value: int, minimum: int, maximum: int, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ProjectFileError(f"{field} must be an integer from {minimum} to {maximum}.")
        return value

    @contextmanager
    def _directory(self, parts: tuple[str, ...]) -> Iterator[int]:
        if self._root_fd is None:
            raise ProjectFileError("The project connection is closed.")
        fd = os.dup(self._root_fd)
        try:
            for part in parts:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        except OSError as exc:
            raise ProjectFileError("Directory is unavailable, excluded or a symbolic link.", code="denied") from exc
        finally:
            os.close(fd)

    def _read_bytes(self, path: str, byte_budget: int | None = None) -> tuple[bytes, os.stat_result]:
        parts = self._parts(path)
        with self._directory(parts[:-1]) as parent:
            try:
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            except OSError as exc:
                raise ProjectFileError("File is unavailable, excluded or a symbolic link.", code="denied") from exc
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise ProjectFileError("Only ordinary files with one hard link are readable.", code="denied")
                if before.st_size > self.limits.max_file_bytes:
                    raise ProjectFileError("File exceeds the configured size limit.", code="file_too_large")
                allowance = self.limits.max_file_bytes if byte_budget is None else byte_budget
                if before.st_size > allowance:
                    raise ProjectFileError("Search byte budget exhausted.", code="byte_budget")
                # Bound reads by the observed size; fstat below detects concurrent changes.
                data = bytearray()
                while len(data) < before.st_size:
                    chunk = os.read(fd, min(65_536, before.st_size - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                after = os.fstat(fd)
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns
                ) or len(data) != before.st_size:
                    raise ProjectFileError("File changed while reading; retry.", code="file_changed", bytes_read=len(data))
                return bytes(data), after
            except OSError as exc:
                raise ProjectFileError("File could not be read.", code="unavailable") from exc
            finally:
                os.close(fd)

    @staticmethod
    def _text(data: bytes) -> str:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectFileError("Only UTF-8 text is supported.", code="not_text") from exc
        if "\x00" in text or _PRIVATE_KEY.search(text):
            raise ProjectFileError("Binary content or a private-key block is excluded.", code="denied")
        return text

    def project_info(self) -> dict:
        return {
            "service": "project-files-mcp", "version": "0.1.0", "instance_id": self.instance_id,
            "project_name": self.root.name, "project_root": str(self.root), "read_only": True,
            "limits": asdict(self.limits),
            "policy": {
                "hidden_paths": "denied", "symbolic_links": "denied", "hard_linked_files": "denied",
                "credential_names": "conservative denylist", "encoding": "UTF-8",
                "note": "Ordinary allowed files may contain secrets. This is not a secret scanner or an OS sandbox.",
            },
        }

    def _scan(self, path: str, recursive: bool, deadline: float) -> tuple[list[dict], list[str], int]:
        parts = self._parts(path, allow_root=True)
        entries: list[dict] = []
        reasons: set[str] = set()
        observed = 0

        def walk(fd: int, prefix: tuple[str, ...], depth: int) -> None:
            nonlocal observed
            if depth > self.limits.max_depth:
                reasons.add("depth_limit")
                return
            children: list[tuple[str, os.stat_result]] = []
            with os.scandir(fd) as iterator:
                for item in iterator:
                    if observed >= self.limits.max_scan_entries:
                        reasons.add("entry_limit")
                        break
                    if time.monotonic() >= deadline:
                        reasons.add("time_limit")
                        break
                    observed += 1
                    if not self._name_allowed(item.name):
                        continue
                    try:
                        st = item.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISDIR(st.st_mode) or (stat.S_ISREG(st.st_mode) and st.st_nlink == 1):
                        children.append((item.name, st))
            for name, st in sorted(children, key=lambda item: item[0]):
                relative = prefix + (name,)
                is_dir = stat.S_ISDIR(st.st_mode)
                entries.append({
                    "path": "/".join(relative), "type": "directory" if is_dir else "file",
                    "size_bytes": None if is_dir else st.st_size, "mtime_ns": st.st_mtime_ns,
                })
                if is_dir and recursive:
                    if observed >= self.limits.max_scan_entries or time.monotonic() >= deadline:
                        reasons.add("entry_limit" if observed >= self.limits.max_scan_entries else "time_limit")
                        continue
                    try:
                        child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    except OSError:
                        continue
                    try:
                        walk(child_fd, relative, depth + 1)
                    finally:
                        os.close(child_fd)

        with self._directory(parts) as directory:
            walk(directory, parts, 0)
        entries.sort(key=lambda item: item["path"])
        return entries, sorted(reasons), observed

    def list_files(self, path: str = ".", *, recursive: bool = False, offset: int = 0, limit: int = 100) -> dict:
        self._bounded_int(offset, 0, self.limits.max_scan_entries, "offset")
        self._bounded_int(limit, 1, self.limits.max_list_items, "limit")
        if not isinstance(recursive, bool):
            raise ProjectFileError("recursive must be boolean.")
        entries, reasons, observed = self._scan(path, recursive, time.monotonic() + self.limits.max_scan_seconds)
        page = entries[offset:offset + limit]
        digest = hashlib.sha256(repr(entries).encode()).hexdigest()
        return {
            "path": path, "entries": page, "offset": offset,
            "next_offset": offset + len(page) if offset + len(page) < len(entries) else None,
            "inventory_sha256": digest, "scan_complete": not reasons, "scan_limit_reasons": reasons,
            "observed_entries": observed,
            "note": "Pagination describes this inventory only. Restart if inventory_sha256 changes. Narrow path when scan_complete is false.",
        }

    def read_file(self, path: str, *, offset: int = 0, limit: int = 16_000, expected_sha256: str | None = None) -> dict:
        self._bounded_int(offset, 0, self.limits.max_file_bytes, "offset")
        self._bounded_int(limit, 1, self.limits.max_read_chars, "limit")
        data, st = self._read_bytes(path)
        text = self._text(data)
        digest = hashlib.sha256(data).hexdigest()
        if expected_sha256 is not None and expected_sha256 != digest:
            raise ProjectFileError("File version changed; restart reading at offset 0.", code="file_changed")
        if offset > len(text):
            raise ProjectFileError("offset is beyond the end of the file.")
        content = text[offset:offset + limit]
        next_offset = offset + len(content)
        return {
            "path": path, "sha256": digest, "file_bytes": len(data), "mtime_ns": st.st_mtime_ns,
            "offset_chars": offset, "returned_chars": len(content), "total_chars": len(text),
            "start_line": text.count("\n", 0, offset) + 1, "content": content,
            "next_offset": next_offset if next_offset < len(text) else None,
            "content_is_untrusted_data": True,
        }

    def search_text(self, query: str, path: str = ".", *, case_sensitive: bool = True, max_results: int = 50) -> dict:
        if not isinstance(query, str) or not 1 <= len(query) <= self.limits.max_query_chars or "\x00" in query:
            raise ProjectFileError("query must be a nonempty, bounded literal string.")
        if "\n" in query or "\r" in query:
            raise ProjectFileError("Search one line at a time.")
        if not isinstance(case_sensitive, bool):
            raise ProjectFileError("case_sensitive must be boolean.")
        self._bounded_int(max_results, 1, self.limits.max_search_results, "max_results")
        deadline = time.monotonic() + self.limits.max_scan_seconds
        entries, reasons, _ = self._scan(path, True, deadline)
        matches: list[dict] = []
        bytes_scanned = files_scanned = skipped = 0
        needle = query if case_sensitive else query.lower()
        for entry in entries:
            if entry["type"] != "file":
                continue
            if time.monotonic() >= deadline:
                reasons.append("time_limit")
                break
            try:
                data, _ = self._read_bytes(entry["path"], self.limits.max_search_bytes - bytes_scanned)
                bytes_scanned += len(data)
                files_scanned += 1
                text = self._text(data)
            except ProjectFileError as exc:
                bytes_scanned += exc.bytes_read
                if exc.code == "byte_budget" or bytes_scanned > self.limits.max_search_bytes:
                    reasons.append("search_byte_limit")
                    break
                skipped += 1
                continue
            for line_number, line in enumerate(text.splitlines(), 1):
                if time.monotonic() >= deadline:
                    reasons.append("time_limit")
                    break
                candidate = line if case_sensitive else line.lower()
                index = candidate.find(needle)
                if index >= 0:
                    # Map a lowercased match back to an original-string offset.
                    # This keeps excerpts useful even for long non-ASCII lines.
                    if not case_sensitive and not line.isascii():
                        lowered_offset = 0
                        for original_index, character in enumerate(line):
                            if lowered_offset + len(character.lower()) > index:
                                index = original_index
                                break
                            lowered_offset += len(character.lower())
                    start = max(0, index - 120)
                    excerpt = line[start:start + 600]
                    matches.append({
                        "path": entry["path"], "line": line_number,
                        "column": index + 1,
                        "excerpt": excerpt, "excerpt_truncated": start > 0 or start + 600 < len(line),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    })
                    if len(matches) >= max_results:
                        reasons.append("result_limit")
                        break
            if len(matches) >= max_results or "time_limit" in reasons:
                break
        return {
            "query": query, "path": path, "case_sensitive": case_sensitive, "matches": matches,
            "files_scanned": files_scanned, "bytes_scanned": bytes_scanned, "skipped_files": skipped,
            "truncated": bool(reasons), "limit_reasons": sorted(set(reasons)),
            "content_is_untrusted_data": True,
        }
