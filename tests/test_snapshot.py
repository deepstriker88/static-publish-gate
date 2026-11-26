import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import static_publish_gate as gate
from static_publish_gate import content_check, read_snapshot, inspect, path_valid

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "dist"
        self.root.mkdir()
        self.file = self.root / "index.html"
        self.file.write_bytes(b"original")
    def baseline(self):
        result, snapshot = content_check(self.root)
        self.assertTrue(result["ok"])
        return snapshot
    def test_sha(self):
        self.assertEqual(self.baseline()["sha256"]["index.html"], hashlib.sha256(b"original").hexdigest())
    def test_same_size_changed(self):
        before = self.baseline()
        self.file.write_bytes(b"modified")
        result, snapshot = content_check(self.root, before["sha256"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"], [{"code":"content_changed","path":"index.html"}])
        self.assertIsNone(snapshot)
    def test_verify_clean(self):
        before = self.baseline()
        self.assertTrue(content_check(self.root, before["sha256"])[0]["ok"])
    def test_new_file(self):
        before = self.baseline()
        (self.root / "new.js").touch()
        self.assertFalse(content_check(self.root, before["sha256"])[0]["ok"])
    def test_deleted_file(self):
        p = self.root / "app.js"
        p.touch()
        before = self.baseline()
        p.unlink()
        self.assertFalse(content_check(self.root, before["sha256"])[0]["ok"])
    def test_empty_file(self):
        self.file.write_bytes(b"")
        self.assertEqual(self.baseline()["sha256"]["index.html"], hashlib.sha256(b"").hexdigest())
    def test_deterministic(self):
        self.assertEqual(self.baseline(), self.baseline())
    def test_no_hash_for_rejected_folder(self):
        (self.root / ".env").touch()
        result, snapshot = content_check(self.root)
        self.assertFalse(result["ok"])
        self.assertIsNone(snapshot)
    def test_hardlink(self):
        os.link(self.file, self.root / "copy.html")
        self.assertIn("hardlink", {x["code"] for x in inspect(self.root)["issues"]})
    def test_reserved(self):
        for name in ("CON", "nul.txt", "COM¹.js", "assets/LPT9", "PRN .txt"):
            self.assertFalse(path_valid(name), name)
    def test_escaped_path_bound(self):
        self.assertFalse(path_valid("😀" * 100))
        self.assertTrue(path_valid("assets/한글.js"))
    def test_manifest_validation(self):
        p = self.root.parent / "snapshot.json"
        p.write_text(json.dumps(self.baseline()))
        self.assertEqual(read_snapshot(p), self.baseline()["sha256"])
        for value in ('{"version":1,"version":1,"sha256":{}}', '{"version":true,"sha256":{}}',
                      '{"version":1,"sha256":{"../x":"bad"}}', '{"version":1,"sha256":{"index.html":1}}'):
            p.write_text(value)
            with self.assertRaises(ValueError):
                read_snapshot(p)
    def test_cli_round_trip(self):
        cmd = [sys.executable, "-m", "static_publish_gate", str(self.root)]
        first = subprocess.run(cmd+["--snapshot"], capture_output=True, text=True)
        self.assertEqual(first.returncode, 0)
        p = self.root.parent / "snapshot.json"
        p.write_text(first.stdout)
        self.assertEqual(subprocess.run(cmd+["--verify", str(p)], capture_output=True).returncode, 0)
        self.file.write_bytes(b"modified")
        self.assertEqual(subprocess.run(cmd+["--verify", str(p)], capture_output=True).returncode, 1)
    def test_manifest_is_regular_not_link_or_fifo(self):
        p = self.root.parent / "snapshot.json"
        p.write_text(json.dumps(self.baseline()))
        link = self.root.parent / "link.json"
        link.symlink_to(p)
        with self.assertRaises(ValueError): read_snapshot(link)
        if hasattr(os, "mkfifo"):
            fifo = self.root.parent / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(ValueError): read_snapshot(fifo)
    def test_reject_same_size_file_changed_after_its_hash(self):
        later = self.root / "z.js"
        later.write_bytes(b"other")
        original = gate._hash_file
        def change_after_hash(path, maximum, expected=None):
            result = original(path, maximum, expected)
            if path.name == "z.js":
                self.file.write_bytes(b"modified")
            return result
        with patch("static_publish_gate._hash_file", side_effect=change_after_hash):
            result, snap = content_check(self.root)
        self.assertFalse(result["ok"])
        self.assertIsNone(snap)
        self.assertIn("inventory_changed_during_hash",{i["code"] for i in result["issues"]})
    def test_reject_file_changed_between_inventory_and_hash(self):
        original=gate._hash_file
        def changed(path,maximum,expected=None):
            path.write_bytes(b"modified")
            return original(path,maximum,expected)
        with patch("static_publish_gate._hash_file",side_effect=changed):
            result, snap=content_check(self.root)
        self.assertFalse(result["ok"])
        self.assertIsNone(snap)
    def test_direct_api_invalid_policy(self):
        for approved in ("index.html", {"index.html":True}, ["index.html","index.html"]):
            with self.assertRaises(ValueError): inspect(self.root,approved=approved)
        with self.assertRaises(ValueError):inspect(self.root,required="index.html")
        with self.assertRaises(ValueError):content_check(self.root,expected={"index.html":"bad"})
    def test_limits(self):
        result, snap = content_check(self.root, max_total=7)
        self.assertFalse(result["ok"])
        self.assertIsNone(snap)
    def test_nonempty_exact_limit(self):
        self.assertTrue(content_check(self.root, max_total=8, max_file=8)[0]["ok"])
if __name__ == "__main__":
    unittest.main()
