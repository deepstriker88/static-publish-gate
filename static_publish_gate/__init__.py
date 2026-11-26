"""Inspect a static publication directory; optionally verify bounded content hashes."""
import hashlib
import json
import re
import os
from pathlib import Path
import stat
import unicodedata

MAX_ENTRIES = 5000
MAX_TOTAL = 100 * 1024 * 1024
MAX_FILE = 20 * 1024 * 1024
MAX_DEPTH = 32
MAX_MANIFEST = 8 * 1024 * 1024
WINDOWS_RESERVED = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {f"{prefix}{digit}" for prefix in ("com", "lpt") for digit in "123456789¹²³"}
DENIED_NAMES = {"node_modules", "package.json", "package-lock.json", "pnpm-lock.yaml",
                "yarn.lock", "dockerfile", "docker-compose.yml", "compose.yml",
                "id_rsa", "id_ed25519", "credentials.json", "secrets.json",
                "thumbs.db", "desktop.ini"}
DENIED_SUFFIXES = (".map", ".pem", ".key", ".p12", ".pfx", ".bak", ".old",
                   ".sql", ".sqlite", ".sqlite3", ".db", ".log", ".swp", "~")

def path_valid(s):
    if not isinstance(s, str) or not s or len(s) > 1024 or len(json.dumps(s, ensure_ascii=True)) > 1026 or "\\" in s:
        return False
    return all(p not in ("", ".", "..") and not any(
        unicodedata.category(c).startswith("C") or c in '<>:"|?*' for c in p
    ) and not p.endswith((" ", ".")) and p.split(".")[0].rstrip(" ").casefold() not in WINDOWS_RESERVED for p in s.split("/"))

def _read_manifest(path):
    """Bounded regular-file read; reject symlinks, FIFO and changed file metadata."""
    path = Path(path)
    before = path.lstat()
    if is_link(before) or not stat.S_ISREG(before.st_mode) or before.st_size > MAX_MANIFEST:
        raise ValueError("invalid manifest file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as f:
        opened = os.fstat(f.fileno())
        if not stat.S_ISREG(opened.st_mode) or _fingerprint(opened) != _fingerprint(before):
            raise ValueError("manifest changed before reading")
        raw = f.read(MAX_MANIFEST + 1)
        if (len(raw) > MAX_MANIFEST or len(raw) != before.st_size
                or _fingerprint(os.fstat(f.fileno())) != _fingerprint(before)
                or _fingerprint(path.lstat()) != _fingerprint(before)):
            raise ValueError("manifest changed or exceeds limit")
    return raw


def read_approved(path):
    data = json.loads(_read_manifest(path))
    if not isinstance(data, list) or len(data) > MAX_ENTRIES or not all(map(path_valid, data)):
        raise ValueError("approved manifest must be an array of safe relative paths")
    if len(set(data)) != len(data):
        raise ValueError("duplicate approved paths")
    return set(data)

def is_link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)

def inspect(root, approved=None, required=("index.html",), max_entries=MAX_ENTRIES,
            max_total=MAX_TOTAL, max_file=MAX_FILE, *, _fingerprints=None):
    for value, hard in ((max_entries, MAX_ENTRIES), (max_total, MAX_TOTAL), (max_file, MAX_FILE)):
        if type(value) is not int or not 1 <= value <= hard:
            raise ValueError("limits must be positive and within hard caps")
    if not isinstance(required, (list, tuple, set, frozenset)) or len(required) > MAX_ENTRIES or not all(map(path_valid, required)):
        raise ValueError("invalid required path")
    if approved is not None:
        if not isinstance(approved, (list, tuple, set, frozenset)) or len(approved) > MAX_ENTRIES or not all(map(path_valid, approved)):
            raise ValueError("invalid approved paths")
        if len(set(approved)) != len(approved):
            raise ValueError("duplicate approved paths")
        approved = set(approved)
    root = Path(root)
    issues, files, seen = [], {}, {}
    count = total = 0
    complete = True

    def fail(code, path=None):
        item = {"code": code}
        if path is not None:
            item["path"] = path
        issues.append(item)

    def denied(name, prefix):
        n = name.casefold()
        return (n in DENIED_NAMES or n.endswith(DENIED_SUFFIXES)
                or (n.startswith(".") and not (name == ".well-known" and not prefix)))

    try:
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or is_link(info):
            raise ValueError("root must be a real directory, not a symlink")
    except OSError as e:
        raise ValueError("cannot access root directory") from e
    stack = [(root, "", 0)]
    while stack and complete:
        directory, prefix, depth = stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    if count > max_entries:
                        fail("entry_limit")
                        complete = False
                        break
                    rel = f"{prefix}/{entry.name}" if prefix else entry.name
                    if not path_valid(rel):
                        fail("unsafe_path", rel)
                        continue
                    key = unicodedata.normalize("NFC", rel).casefold()
                    if key in seen and seen[key] != rel:
                        fail("case_or_unicode_collision", rel)
                    seen[key] = rel
                    if denied(entry.name, prefix):
                        fail("forbidden_path", rel)
                        continue
                    try:
                        mode = entry.stat(follow_symlinks=False)
                    except OSError:
                        fail("unreadable_entry", rel)
                        complete = False
                        break
                    if is_link(mode):
                        fail("symlink", rel)
                    elif stat.S_ISDIR(mode.st_mode):
                        if depth >= MAX_DEPTH:
                            fail("depth_limit", rel)
                            complete = False
                            break
                        stack.append((Path(entry.path), rel, depth + 1))
                    elif stat.S_ISREG(mode.st_mode):
                        if mode.st_nlink != 1:
                            fail("hardlink", rel)
                            continue
                        if rel == ".well-known":
                            fail("forbidden_path", rel)
                            continue
                        files[rel] = mode.st_size
                        if _fingerprints is not None:
                            _fingerprints[rel] = _fingerprint(mode)
                        total += mode.st_size
                        if mode.st_size > max_file:
                            fail("file_size_limit", rel)
                        if total > max_total:
                            fail("total_size_limit")
                            complete = False
                            break
                    else:
                        fail("special_file", rel)
        except OSError:
            fail("unreadable_directory", prefix or ".")
            complete = False
    if complete:
        for path in sorted(set(required) - files.keys()):
            fail("required_missing", path)
        if approved is not None:
            for path in sorted(files.keys() - approved):
                fail("unapproved_file", path)
            for path in sorted(approved - files.keys()):
                fail("approved_file_missing", path)
    return {"ok": complete and not issues, "complete": complete,
            "entries": min(count, max_entries), "files": len(files), "bytes": total,
            "issues": sorted(issues, key=lambda x: (x["code"], x.get("path", ""))),
            "inventory": sorted(files)}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result

def read_snapshot(path):
    data = json.loads(_read_manifest(path), object_pairs_hook=_unique_pairs)
    if (not isinstance(data, dict) or set(data) != {"version", "sha256"}
            or type(data["version"]) is not int or data["version"] != 1):
        raise ValueError("invalid snapshot")
    hashes = data["sha256"]
    if not isinstance(hashes, dict) or len(hashes) > MAX_ENTRIES or not all(
        path_valid(k) and isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)
        for k, v in hashes.items()
    ):
        raise ValueError("invalid hashes")
    return hashes

def _fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)

def _hash_file(path, max_bytes, expected_fingerprint=None):
    before = path.lstat()
    if is_link(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("unsafe file")
    if expected_fingerprint is not None and _fingerprint(before) != expected_fingerprint:
        raise ValueError("file changed since inventory")
    if before.st_size > max_bytes:
        raise ValueError("file size changed or too large")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if _fingerprint(opened) != _fingerprint(before) or not stat.S_ISREG(opened.st_mode):
            raise ValueError("file changed before reading")
        digest = hashlib.sha256()
        consumed = 0
        while True:
            data = os.read(fd, min(65536, before.st_size - consumed + 1))
            if not data:
                break
            consumed += len(data)
            if consumed > before.st_size:
                raise ValueError("file grew while reading")
            digest.update(data)
        if (consumed != before.st_size or _fingerprint(os.fstat(fd)) != _fingerprint(before)
                or _fingerprint(path.lstat()) != _fingerprint(before)):
            raise ValueError("file changed while reading")
        return digest.hexdigest(), consumed
    finally:
        os.close(fd)

def content_check(root, expected=None, **limits):
    """Trusted, quiescent build directory only; this is not a filesystem sandbox."""
    if expected is not None and (not isinstance(expected, dict) or len(expected) > MAX_ENTRIES or not all(
        path_valid(k) and isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) for k, v in expected.items()
    )):
        raise ValueError("invalid expected hashes")
    initial = {}
    result = inspect(root, approved=set(expected) if expected is not None else None, _fingerprints=initial, **limits)
    if not result["ok"]:
        return result, None
    remaining = limits.get("max_total", MAX_TOTAL)
    max_file = limits.get("max_file", MAX_FILE)
    hashes = {}
    for rel in result["inventory"]:
        try:
            digest, length = _hash_file(Path(root) / rel, min(remaining, max_file), initial[rel])
        except (OSError, ValueError):
            result["issues"].append({"code": "hash_io_or_changed", "path": rel})
            result["complete"] = False
            break
        remaining -= length
        hashes[rel] = digest
        if expected is not None and digest != expected[rel]:
            result["issues"].append({"code": "content_changed", "path": rel})
    # Repeat the metadata inspection to detect common additions/removals during hashing.
    final = {}
    after = inspect(root, approved=set(result["inventory"]), _fingerprints=final, **limits)
    if (not after["ok"] or initial != final or after["bytes"] != result["bytes"]
            or result["bytes"] != limits.get("max_total", MAX_TOTAL) - remaining):
        result["issues"].append({"code": "inventory_changed_during_hash"})
        result["complete"] = False
    result["ok"] = result["complete"] and not result["issues"]
    return result, {"version": 1, "sha256": hashes} if result["ok"] else None
