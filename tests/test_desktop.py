import json
import tempfile
import unittest
from pathlib import Path

from static_publish_gate import desktop, inspect
from static_publish_gate.desktop_ui import write_new_json


class DesktopAdapterTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.dist=self.root/"dist";self.dist.mkdir()
        (self.dist/"index.html").write_text("first")

    def run_mode(self,mode,**values):
        return desktop.run({"root":self.dist,"mode":mode,"required":"",**values})

    def test_inventory_matches_core(self):
        r=self.run_mode("Inventory")
        self.assertEqual(r.data,inspect(self.dist))
        self.assertEqual(r.state,"pass")
        self.assertEqual(Path(r.protected_root),self.dist)

    def test_real_example(self):
        r=desktop.demo()
        self.assertEqual(r.state,"review")
        self.assertEqual(r.data["issues"],[{"code":"forbidden_path","path":"assets/app.js.map"}])

    def test_snapshot_verified_then_same_size_change(self):
        r=self.run_mode("Create snapshot")
        self.assertEqual(r.state,"pass")
        p=self.root/"reviewed.json";write_new_json(p,r.snapshot)
        self.assertEqual(self.run_mode("Verify snapshot",manifest=p).state,"pass")
        (self.dist/"index.html").write_text("other")
        changed=self.run_mode("Verify snapshot",manifest=p)
        self.assertEqual(changed.state,"review")
        self.assertIn("content_changed",[x["code"] for x in changed.data["issues"]])

    def test_reviewed_path_list_and_required_path(self):
        p=self.root/"approved.json";p.write_text('["index.html"]')
        self.assertEqual(self.run_mode("Path list",manifest=p).state,"pass")
        (self.dist/"extra.js").write_text("extra")
        self.assertEqual(self.run_mode("Path list",manifest=p).state,"review")
        self.assertEqual(self.run_mode("Inventory",required="missing.js").state,"review")

    def test_missing_reviewed_manifest_refused(self):
        for mode in ("Verify snapshot","Path list"):
            with self.assertRaises(ValueError):self.run_mode(mode)

    def test_no_export_overwrite(self):
        p=self.root/"report.json";p.write_text("original")
        with self.assertRaises(FileExistsError):write_new_json(p,self.run_mode("Inventory").data)
        self.assertEqual(p.read_text(),"original")
