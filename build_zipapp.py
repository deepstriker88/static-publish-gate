"""Build an exclusive-output, reproducible standalone Python zipapp."""
from io import BytesIO
from pathlib import Path
import os
import sys
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


def build(output):
    root = Path(__file__).resolve().parent
    files = {"__main__.py": b"from static_publish_gate.__main__ import main\nraise SystemExit(main())\n"}
    for name in ("__init__.py", "__main__.py", "desktop.py", "desktop_ui.py"):
        files[f"static_publish_gate/{name}"] = (root / "static_publish_gate" / name).read_bytes()
    files["LICENSE"] = (root / "LICENSE").read_bytes()
    data = BytesIO()
    data.write(b"#!/usr/bin/env python3\n")
    with ZipFile(data, "w") as archive:
        for name, body in sorted(files.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, body, compresslevel=9)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o700)
    with os.fdopen(fd, "wb") as f:
        f.write(data.getvalue())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python build_zipapp.py NEW_OUTPUT.pyz")
    build(sys.argv[1])
