"""Create a new model/views delivery folder without overwriting anything."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from views import export, SCALES


def prepare(source, output, units, inset=1., sections=False):
    source = Path(source).resolve()
    if not source.is_file() or source.suffix.lower() != ".stl":
        raise ValueError("Select an existing STL file")
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    model = out / "模型"
    model.mkdir()
    original = model / "原始.stl"
    shutil.copy2(source, original)
    manifest = {
        "source_filename": source.name,
        "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
        "input_units": units, "geometry_units": "mm", "requested_inset_mm": inset,
        "sections_requested": bool(sections), "status": "preparing"}
    path = model / "项目.json"
    try:
        info = export(original, out / "视图", units, inset, sections=sections)
        manifest.update(bounds_mm=info["bounds_mm"], dimensions_mm=info["dimensions_mm"],
                        watertight=info["watertight"], status="views_ready_model_pending")
    except Exception as exc:
        manifest.update(status="prepare_failed", error=str(exc))
        raise
    finally:
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Views ready; CAD modeling remains: {out}", flush=True)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("--units", required=True, choices=SCALES)
    p.add_argument("--output", required=True)
    p.add_argument("--inset", type=float, default=1.)
    p.add_argument("--sections", action="store_true", help="Also generate section images when needed")
    a = p.parse_args()
    prepare(a.source, a.output, a.units, a.inset, sections=a.sections)
