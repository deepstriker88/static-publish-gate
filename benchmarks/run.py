"""Synthetic maximum-entry/content benchmark, no external dependencies."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import statistics

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        archive=root/"gate.pyz"
        subprocess.run([sys.executable,str(ROOT/"build_zipapp.py"),str(archive)],check=True,timeout=10)
        dist=root/"dist";dist.mkdir()
        (dist/"index.html").write_bytes(b"example")
        data=b"x"*20000
        for i in range(4999):
            (dist/f"asset-{i:04d}.js").write_bytes(data)
        manifest=root/"snapshot.json"
        snapshot_times=[];verify_times=[]
        for i in range(3):
            start=time.monotonic()
            result=subprocess.run([sys.executable,str(archive),str(dist),"--snapshot"],capture_output=True,check=True,timeout=15)
            snapshot_times.append(time.monotonic()-start)
            snap=json.loads(result.stdout)
            assert len(snap["sha256"])==5000
            manifest.write_bytes(result.stdout)
            start=time.monotonic()
            verified=subprocess.run([sys.executable,str(archive),str(dist),"--verify",str(manifest)],capture_output=True,check=True,timeout=15)
            verify_times.append(time.monotonic()-start)
            assert json.loads(verified.stdout)["ok"]
        rss=None
        try:
            import resource
            rss=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            if sys.platform=="darwin":rss/=1024
        except ImportError:
            pass
        print(json.dumps({"files":5000,"input_bytes":len(data)*4999+7,"package_bytes":archive.stat().st_size,
             "snapshot_seconds":snapshot_times,"verify_seconds":verify_times,
             "snapshot_median":statistics.median(snapshot_times),"verify_median":statistics.median(verify_times),
             "peak_child_rss_kib":rss,"python":sys.version.split()[0]},indent=2))


if __name__=="__main__":main()
