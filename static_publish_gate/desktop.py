"""Local GUI adapter; all file policy and content checks remain in the CLI core."""
from pathlib import Path
import tempfile
import sys
from . import inspect, content_check, read_approved, read_snapshot
from .desktop_ui import Field, Result, launch

TITLE="Static Publish Gate"
LEAD="Review the exact local folder before publication: unwanted paths, missing files and reviewed content changes."
LIMIT="Trusted, quiescent build folders only. Not a content secret scanner or security certification."
MORE="""FREE LOCAL TOOL · $0

Inventory checks required index.html, conservative forbidden names/extensions,
links, file/entry/size limits, case and Unicode collisions. Optionally compare
an exact reviewed path list. Snapshot mode produces a candidate SHA-256 map.
Review and protect it outside the build folder before verification.

The verification mode detects changed content even when a filename and size
are unchanged. A snapshot is not approval, a digital signature, or proof of
publisher identity. Never derive the expected pin from unreviewed current
content just before deployment. Use an immutable reviewed build.

No upload, network, crawler, modification, or execution of site content.
The scanner is not a filesystem sandbox and cannot detect every concurrent
directory change, secrets inside HTML/JS, or hosting configuration mistakes.
Use independent secret scanning and host controls. Reports contain relative
paths: review before sharing.

Limits: 5,000 entries, 100 MiB total, 20 MiB/file, 32 directory levels.
This complements static hosting and deployment tooling; it is not http-server.
"""
CONDITIONAL_FIELDS=("manifest",)
FIELDS=(
    Field("root","Build folder","directory"),
    Field("mode","Check mode","choice",choices=("Inventory","Path list","Create snapshot","Verify snapshot"),default="Inventory"),
    Field("manifest","Reviewed JSON","file",optional=True,filters=(("JSON","*.json"),("All files","*"))),
    Field("required","Extra required path","text",optional=True),
)


def visible_for_mode(values):
    fields=("root","mode","required")
    return (*fields,"manifest") if values.get("mode") in ("Path list","Verify snapshot") else fields


def required_for_mode(values):
    return ("manifest",) if values.get("mode") in ("Path list","Verify snapshot") else ()


def describe(data,snapshot=None,mode="Inventory",root=None):
    state="uninspected" if not data["complete"] else ("pass" if data["ok"] else "review")
    title={"uninspected":"Inspection incomplete","pass":"Selected checks passed","review":"Review before publishing"}[state]
    desc="Candidate snapshot ready for independent review." if snapshot else "Checks reflect the selected folder and mode only."
    details=tuple(x["code"].replace("_"," ")+(" · "+str(x["path"]) if "path" in x else "") for x in data["issues"])
    if not details:details=("No findings in the selected inventory/content checks.",)
    return Result(state,title,desc,(("Files",data["files"]),("Size (MiB)",f"{data['bytes']/1048576:.2f}"),("Findings",len(data["issues"]))),details,data,snapshot,str(Path(root).absolute()) if root is not None else None)


def run(values):
    root=values["root"]
    mode=values["mode"]
    manifest=values.get("manifest")
    required=("index.html",)+(tuple([values["required"].strip()]) if values.get("required","").strip() else ())
    if mode=="Inventory":
        data=inspect(root,required=required)
        return describe(data,root=root)
    if mode=="Path list":
        if not manifest:raise ValueError("reviewed path list required")
        return describe(inspect(root,read_approved(manifest),required=required),root=root)
    if mode=="Create snapshot":
        data,snapshot=content_check(root,required=required)
        return describe(data,snapshot,mode,root=root)
    if mode=="Verify snapshot":
        if not manifest:raise ValueError("reviewed snapshot required")
        data,_=content_check(root,read_snapshot(manifest),required=required)
        return describe(data,mode=mode,root=root)
    raise ValueError("invalid mode")


def make_example(root, blocked=False):
    root=Path(root);root.mkdir()
    (root/"assets").mkdir()
    (root/"index.html").write_bytes(b"<!doctype html><title>Example build</title><h1>Example</h1>\n")
    if blocked:
        (root/"assets/app.js.map").write_bytes(b'{"version":3,"sources":[],"mappings":""}\n')
    else:
        (root/"assets/app.js").write_bytes(b"console.log('synthetic example');\n")


def demo():
    with tempfile.TemporaryDirectory(prefix="static-gate-example-") as tmp:
        root=Path(tmp)/"dist";make_example(root,True)
        return run({"root":root,"mode":"Inventory","required":""})


def main():
    try:
        launch(sys.modules[__name__]);return 0
    except ImportError:
        print("Desktop UI needs Python Tkinter. Use the CLI without --gui.",file=sys.stderr);return 2
    except Exception as e:
        if type(e).__name__=="TclError":
            print("Desktop display unavailable. Use the CLI without --gui.",file=sys.stderr);return 2
        raise
