# Static Publish Gate

## Desktop quick start

Build or obtain the reviewed `static-publish-gate.pyz` file. On Windows with
Python installed, open PowerShell in its directory and run:

    py static-publish-gate.pyz --gui

On Linux/macOS:

    python3 static-publish-gate.pyz --gui

Choose local inputs, click Run check, or Try example to run a real synthetic
fixture. View report shows the selected findings; Save report writes a new JSON or script-free HTML file
only. The interface never uploads inputs or launches a payment flow. Tkinter
must be available in your Python installation (it is optional on some Linux
distributions). If unavailable or on a headless machine, use the existing CLI.
The CLI needs no GUI dependencies. The GUI is a desktop interface, not a mobile
browser inspector. Free local edition; no paid plan or subscription.


Check the exact local folder you intend to publish for unwanted files, missing
entry points, symlinks, naming collisions and excessive size before deployment.
It is not a web server, crawler, content scanner or security certification.

## Quick start (Python 3.10+)
From this directory:
    python3 build_zipapp.py /tmp/static-publish-gate.pyz
    python3 /tmp/static-publish-gate.pyz ./dist --inventory

Exit 0 means the declared inventory rules pass; 1 means findings or an incomplete
scan; 2 means invalid input or I/O configuration failure. JSON is printed to stdout.

## Common examples
    python3 /tmp/static-publish-gate.pyz ./dist --approved approved.json --require assets/app.js
    python3 /tmp/static-publish-gate.pyz ./dist --max-total-bytes 10485760

The approved JSON must be a manually reviewed array of exact relative file names,
e.g. ["assets/app.js","index.html"]. Keep this file outside the publish directory.
Approval/snapshot input must be a regular file, not a symbolic link or FIFO.
The inventory is a candidate list, not automatic approval. Changed hashed asset
names require explicit re-review. No manifest is required for basic checks.

## Verify reviewed content before publishing
    python3 /tmp/static-publish-gate.pyz ./dist --snapshot > approved-content.json
    python3 /tmp/static-publish-gate.pyz ./dist --verify approved-content.json

Review the files before approving the snapshot; store it outside the dist folder
and protect it from modification. Verify the exact immutable artifact immediately
before upload. A snapshot is not a digital signature or proof of publisher identity.
The JSON uses exact relative paths and lowercase SHA-256 hashes. Snapshot generation
fails if the folder violates the inventory policy. No automatic approval.

## Security and limitations
Run on a quiescent build folder that you control, with no concurrent writers.
Default mode examines only file metadata and directory entries. Optional snapshot
mode reads file contents locally in bounded chunks to compute SHA-256. No content
is printed, no network requests, no server, no modifications to the target.
Symlinks, hardlinks and non-regular files are rejected. Dotfiles except a root .well-known directory,
selected configuration/backup/database/key extensions and source maps are blocked
conservatively; legitimate exceptions are not supported in this MVP. The policy
is not exhaustive. It cannot detect secrets inside HTML/JS, host routing, permission exposure, or
races between inspection and deployment. Default metadata mode cannot detect
content changes under the same name; use --snapshot and --verify for that. Use independent secret scanning, host controls
and immutable build artifacts. Snapshot mode compares initial and final file
metadata to detect common same-size modifications during the scan; it is not a
filesystem sandbox and cannot guarantee detection of concurrent directory changes.
Never use this as the sole security gate.
Limits: 5,000 entries, 100 MiB total, 20 MiB/file, 32 directory levels; limits
may be lowered only. Reports contain local relative paths; avoid public logs.
An incomplete scan never passes. Use a clean, smaller build directory if capped.

## Human-readable local report

    python3 static-publish-gate.pyz ./dist --inventory --html ./publish-report.html

The command writes a new script-free HTML report and preserves the CLI JSON and exit code.
Choose a new filename outside inspected input folders; reports are not signed approvals.


## Installation and support

Extract the complete download ZIP; Windows uses the provided launcher or `py -3 -I -B static-publish-gate.pyz --gui`. The CLI does not need Tkinter.

Use synthetic or redacted inputs in bug reports. Optional support: https://buymeacoffee.com/eztoolgo (no entitlement or subscription).

## License

MIT; see LICENSE.

## Download and run

Download the versioned local ZIP from the GitHub release, extract the full archive and open index.html. No account or subscription is required.
