import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


class PackageTests(unittest.TestCase):
    def test_reproducible_and_packaged_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            a,b=root/"a.pyz",root/"b.pyz"
            for target in (a,b):
                subprocess.run([sys.executable,"build_zipapp.py",str(target)],check=True,timeout=10)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            with zipfile.ZipFile(a) as z:
                self.assertEqual(set(z.namelist()),{"LICENSE", "__main__.py","static_publish_gate/__init__.py","static_publish_gate/__main__.py","static_publish_gate/desktop.py","static_publish_gate/desktop_ui.py"})
            build=root/"dist";build.mkdir();(build/"index.html").write_text("original")
            p=subprocess.run([sys.executable,str(a),str(build),"--snapshot"],capture_output=True,timeout=10)
            self.assertEqual(p.returncode,0,p.stderr)
            approved=root/"approved.json";approved.write_bytes(p.stdout)
            self.assertEqual(len(json.loads(p.stdout)["sha256"]),1)
            def verify():
                return subprocess.run([sys.executable,str(a),str(build),"--verify",str(approved)],capture_output=True,timeout=10)
            self.assertEqual(verify().returncode,0)
            (build/"index.html").write_text("modified")
            result=verify()
            self.assertEqual(result.returncode,1)
            self.assertIn("content_changed",result.stdout.decode())
            original=a.read_bytes()
            self.assertNotEqual(subprocess.run([sys.executable,"build_zipapp.py",str(a)],capture_output=True,timeout=10).returncode,0)
            self.assertEqual(original,a.read_bytes())
