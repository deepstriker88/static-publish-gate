import argparse
import json
import sys
from pathlib import Path
from . import inspect, read_approved, read_snapshot, content_check, MAX_ENTRIES, MAX_TOTAL, MAX_FILE

def main(argv=None):
    if (sys.argv[1:] if argv is None else argv) == ['--gui']:
        from .desktop import main as gui_main
        return gui_main()
    p = argparse.ArgumentParser(description="Offline static publication inventory gate", epilog="Use --gui by itself for the optional local desktop interface.")
    p.add_argument("root")
    m = p.add_mutually_exclusive_group()
    m.add_argument("--approved", help="reviewed JSON array of exact relative paths")
    m.add_argument("--snapshot", action="store_true", help="emit SHA-256 snapshot of a passing build")
    m.add_argument("--verify", help="verify reviewed SHA-256 snapshot")
    p.add_argument("--require", action="append", default=[], help="additional required file")
    p.add_argument("--max-entries", type=int, default=MAX_ENTRIES)
    p.add_argument("--max-total-bytes", type=int, default=MAX_TOTAL)
    p.add_argument("--max-file-bytes", type=int, default=MAX_FILE)
    p.add_argument("--html", help="new local HTML report outside the build folder (not with --snapshot)")
    p.add_argument("--inventory", action="store_true", help="include sorted candidate inventory")
    a = p.parse_args(argv)
    try:
        if a.html and (a.snapshot or Path(a.html).resolve().is_relative_to(Path(a.root).resolve())):
            raise ValueError("HTML report must be outside build; snapshot writes JSON only")
        limits = dict(required=("index.html", *a.require), max_entries=a.max_entries,
                      max_total=a.max_total_bytes, max_file=a.max_file_bytes)
        if a.snapshot or a.verify:
            result, snapshot = content_check(a.root, read_snapshot(a.verify) if a.verify else None, **limits)
            if a.snapshot and snapshot is not None:
                print(json.dumps(snapshot, ensure_ascii=True, sort_keys=True))
                return 0
        else:
            result = inspect(a.root, read_approved(a.approved) if a.approved else None, **limits)
        if a.html:
            from . import desktop
            from .desktop_ui import render_report,write_new_bytes
            write_new_bytes(a.html,render_report(desktop,desktop.describe(result,root=a.root)))
    except (OSError, ValueError, RecursionError) as e:
        print(json.dumps({"ok": False, "error": "invalid_input_or_io"}))
        return 2
    if not a.inventory:
        result.pop("inventory")
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["ok"] else 1

if __name__ == "__main__":
    sys.exit(main())
