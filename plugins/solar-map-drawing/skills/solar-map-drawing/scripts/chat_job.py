"""Use chat attachments with the bundled solar renderer; no model API calls.

The chat agent still identifies/traces geometry, arranges callouts and checks the
proof. This adapter manages session files and runtime setup, not map recognition.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
WO = re.compile(r"\bWO[-_ ]?(\d+)(?:[-_ ]([A-Z])(?=[^A-Z0-9]|$))?", re.I)


def pdf_module():
    try:
        return importlib.import_module("pymupdf")
    except ImportError:
        return importlib.import_module("fitz")


def runtime(install_missing=False, dependency_dir=None):
    """Install only missing packages, into session storage, when requested."""
    if dependency_dir:
        dependency_dir = Path(dependency_dir).resolve()
        if dependency_dir.exists():
            sys.path.insert(0, str(dependency_dir))
    missing = []
    for module, package in ((None, "PyMuPDF>=1.24,<2"), ("PIL", "Pillow>=10,<13")):
        try:
            pdf_module() if module is None else importlib.import_module(module)
        except ImportError:
            missing.append(package)
    if missing and install_missing:
        if dependency_dir is None:
            raise ValueError("Choose a writable session --dependency-dir for runtime setup")
        dependency_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                            "--no-input", "--target", str(dependency_dir), *missing],
                           check=True, stdout=sys.stderr)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "This chat could not obtain the PDF/image packages. Use a host with "
                "PyMuPDF and Pillow already available or permitted package access. "
                "The map has not been rendered; no API key is needed."
            ) from exc
        if str(dependency_dir) not in sys.path:
            sys.path.insert(0, str(dependency_dir))
        importlib.invalidate_caches()
    try:
        fitz = pdf_module()
        pil = importlib.import_module("PIL")
        if not hasattr(fitz, "open") or not hasattr(fitz, "Font"):
            raise ImportError("The installed fitz module is not PyMuPDF")
    except ImportError as exc:
        raise RuntimeError(
            "This chat needs a Python file-execution tool with PyMuPDF and Pillow. "
            "Use session-local dependency setup if package access is available. "
            "Otherwise continue in a file-capable Work/Codex chat; no API key is needed."
        ) from exc
    for name in ("north-arrow.json", "leader-arrow-2.json", "placard-profiles.json"):
        if not (SKILL/"assets"/name).is_file():
            raise RuntimeError(f"Incomplete installed skill: assets/{name} is missing")
    if not (SKILL/'scripts/placard_layout.py').is_file():raise RuntimeError('Incomplete installed skill: scripts/placard_layout.py is missing')
    return {"python":sys.version.split()[0], "pymupdf":getattr(fitz, "VersionBind", "unknown"),
            "pillow":pil.__version__, "model_api_required":False}


def workbench():
    spec = importlib.util.spec_from_file_location("solar_chat_workbench", SKILL/"scripts/map_workbench.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_order(value):
    match = re.fullmatch(r"(?:WO[-_ ]?)?(\d+)", value, re.I)
    if not match:
        raise ValueError("Work order must look like WO-288781")
    return "WO-"+match.group(1)


def prepare(source, workspace=None, work_order=None):
    """Copy exactly the selected attachment and inspect once per content hash."""
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError("The selected attachment is not readable in this chat")
    if source.suffix.lower() != ".pdf":
        raise ValueError("Chat preparation expects the attached PDF; use workbench for other formats")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    workspace = Path(workspace).resolve() if workspace else Path(tempfile.mkdtemp(prefix="solar-map-chat-"))
    job = workspace/"jobs"/digest[:16]
    input_dir = job/"input"
    input_dir.mkdir(parents=True, exist_ok=True)
    copied = input_dir/source.name
    if not copied.exists() or hashlib.sha256(copied.read_bytes()).hexdigest() != digest:
        shutil.copyfile(source, copied)
    inspection = job/"inspection"
    wb = workbench()
    order_scan=job/'order-layout-candidates.json'
    candidate_order=normalize_order(work_order) if work_order else ('WO-'+WO.search(source.stem).group(1) if WO.search(source.stem) else None)
    if candidate_order and not order_scan.exists():
        wb.write_json(order_scan,wb.placard_tools().analyze_order_pdf(copied,candidate_order))
    if not (inspection/"pages.json").exists():
        wb.inspect_source(copied, inspection)
    pages = wb.read_json(inspection/"pages.json")
    filename_match = WO.search(source.stem)
    candidates = sorted({"WO-"+m.group(1) for p in pages for m in WO.finditer(p["text"])})
    if work_order:
        order, evidence = normalize_order(work_order), "Explicit work order supplied for this attachment"
    elif filename_match:
        order, evidence = "WO-"+filename_match.group(1), "Attached PDF filename; verify against order page"
    elif len(candidates) == 1:
        order, evidence = candidates[0], "Only work order number in extracted PDF text; verify visually"
    else:
        order, evidence = None, None
    if order and not order_scan.exists():wb.write_json(order_scan,wb.placard_tools().analyze_order_pdf(copied,order))
    order_candidates=wb.read_json(order_scan) if order_scan.exists() else {'items':[]}
    state = {"version":2, "sha256":digest, "source":"input/"+copied.name,
             "job":{"work_order":order, "work_order_evidence":evidence},
             "work_order_candidates":candidates, "inspection":"inspection/pages.json",
             "layout_mode":"size_first_placard_zones","order_layout_candidates":"order-layout-candidates.json" if order_scan.exists() else None}
    wb.write_json(job/"job.json", state)
    return {"job_dir":str(job), "source":str(copied), "inspection":str(inspection),
            "work_order":order, "work_order_candidates":candidates,
            "needs_work_order_confirmation":order is None,
            "order_layout_candidates":order_candidates['items'],
            "next":"Confirm each map item's ordered size/SKU from the sales-order row, then plan its physical cutline, warning, working and footer zones before fitting geometry or callouts. Review all contact sheets and source warning wording; render complete placards on one order artboard."}


def render(scene, delivery, preview=None, diagnostics=None, mode=None):
    scene, delivery = Path(scene).resolve(), Path(delivery).resolve()
    preview = Path(preview).resolve() if preview else scene.parent/"qa"/"preview.png"
    report = workbench().render(scene, delivery, preview=preview, diagnostics=diagnostics, mode=mode)
    svg = delivery/report["output_filename"]
    # Only an actual generated file can be offered as a chat download.
    if not svg.is_file() or svg.stat().st_size == 0:
        raise RuntimeError("Renderer did not create the SVG attachment")
    return {"svg":str(svg), "preview":str(preview), "review_required":True,
            "report":report}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-missing", action="store_true", help="Set up missing packages in session storage")
    parser.add_argument("--dependency-dir", help="Session-local package directory, reused across commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    prep = sub.add_parser("prepare")
    prep.add_argument("source", help="Actual path of the PDF attached to this chat")
    prep.add_argument("--workspace", help="Writable session storage, outside the installed plugin")
    prep.add_argument("--work-order", help="Source-confirmed WO when attachment name/text is ambiguous")
    draw = sub.add_parser("render")
    draw.add_argument("scene")
    draw.add_argument("--delivery", required=True, help="Directory exposed as chat downloads")
    draw.add_argument("--preview", help="Internal visual review image")
    draw.add_argument("--diagnostics", help="Internal comparison directory for new geometry")
    draw.add_argument("--mode", choices=('map-only','map-labeled','finished'), help="Output scope selected by the invoked skill")
    args = parser.parse_args(argv)
    try:
        info = runtime(args.install_missing, args.dependency_dir)
        if args.command == "doctor":
            result = info
        elif args.command == "prepare":
            result = prepare(args.source, args.workspace, args.work_order)
        else:
            result = render(args.scene, args.delivery, args.preview, args.diagnostics, args.mode)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status":"blocked", "error":str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
