import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from static_publish_gate import inspect, read_approved, path_valid

class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "dist"
        self.root.mkdir()
        self.put("index.html")
    def put(self, name, body=b"x"):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    def codes(self, **kwargs):
        return {x["code"] for x in inspect(self.root, **kwargs)["issues"]}
    def test_clean(self):
        self.put("assets/app.js")
        self.assertTrue(inspect(self.root)["ok"])
    def test_hidden(self):
        self.put(".env", b"not-a-real-secret")
        self.assertIn("forbidden_path", self.codes())
    def test_git(self):
        self.put(".git/config")
        self.assertIn("forbidden_path", self.codes())
    def test_source_map(self):
        self.put("app.js.MAP")
        self.assertIn("forbidden_path", self.codes())
    def test_backup(self):
        self.put("index.html.bak")
        self.assertIn("forbidden_path", self.codes())
    def test_well_known(self):
        self.put(".well-known/security.txt")
        self.assertTrue(inspect(self.root)["ok"])
    def test_well_known_file(self):
        self.put(".well-known")
        self.assertIn("forbidden_path", self.codes())
    def test_nested_dot(self):
        self.put("assets/.well-known/test")
        self.assertIn("forbidden_path", self.codes())
    def test_symlink(self):
        (self.root / "external").symlink_to(self.root.parent)
        self.assertIn("symlink", self.codes())
    def test_root_symlink(self):
        target = self.root.parent / "link"
        target.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            inspect(target)
    def test_fifo(self):
        if not hasattr(os, "mkfifo"): self.skipTest("POSIX only")
        os.mkfifo(self.root / "pipe")
        self.assertIn("special_file", self.codes())
    def test_case(self):
        self.put("APP.js")
        self.put("app.js")
        if len(list(self.root.glob("*"))) != 3: self.skipTest("case-insensitive FS")
        self.assertIn("case_or_unicode_collision", self.codes())
    def test_missing_required(self):
        (self.root / "index.html").unlink()
        self.assertIn("required_missing", self.codes())
    def test_approved(self):
        self.put("new.js")
        self.assertEqual(self.codes(approved={"index.html", "old.js"}),
                         {"unapproved_file", "approved_file_missing"})
    def test_exact_approved(self):
        self.assertTrue(inspect(self.root, approved={"index.html"})["ok"])
    def test_size(self):
        self.put("big.js", b"1234")
        self.assertIn("file_size_limit", self.codes(max_file=3))
    def test_total(self):
        self.put("big.js", b"1234")
        self.assertFalse(inspect(self.root, max_total=3)["complete"])
    def test_entry_limit(self):
        self.put("a")
        r = inspect(self.root, max_entries=1)
        self.assertFalse(r["complete"])
        self.assertFalse(r["ok"])
    def test_depth(self):
        self.put("/".join(["d"]*34+["file"]))
        self.assertIn("depth_limit", self.codes())
    def test_manifest(self):
        p = self.root.parent / "approved.json"
        p.write_text('["index.html"]')
        self.assertEqual(read_approved(p), {"index.html"})
        for bad in ['["../x"]', '["a","a"]', '{"a":1}', '["C:\\\\x"]']:
            p.write_text(bad)
            with self.assertRaises(ValueError):
                read_approved(p)
    def test_path(self):
        for x in ["", "/a", "a//b", "a/../b", "a\\b", "x\n", "x.", "x ", "C:x"]:
            self.assertFalse(path_valid(x), x)
    def test_bounds(self):
        with self.assertRaises(ValueError):
            inspect(self.root, max_entries=5001)
    def test_cli(self):
        p = subprocess.run([sys.executable, "-m", "static_publish_gate", str(self.root)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("inventory", json.loads(p.stdout))
        self.put(".env", b"FAKE_TEST_VALUE")
        p = subprocess.run([sys.executable, "-m", "static_publish_gate", str(self.root)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("FAKE_TEST_VALUE", p.stdout)
    def test_bad_input(self):
        p = subprocess.run([sys.executable, "-m", "static_publish_gate", str(self.root/"absent")],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertFalse(json.loads(p.stdout)["ok"])

if __name__ == "__main__":
    unittest.main()
