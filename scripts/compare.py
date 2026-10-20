"""Coarse geometry checks; local hole/section checks remain an explicit review."""
import argparse
import json
from pathlib import Path
import numpy as np
from views import load_mesh


def compare(folder):
    folder = Path(folder)
    model = folder / "模型"
    if not (model / "验证" / "重建.stl").is_file():
        raise FileNotFoundError(
            "Numerical comparison needs a validation mesh. Use --detailed when building, "
            "or export a validation STL from the existing native model; do not rebuild solely for this check.")
    project = json.loads((model / "项目.json").read_text(encoding="utf-8"))
    source = load_mesh(model / "原始.stl", project["input_units"])
    rebuilt = load_mesh(model / "验证" / "重建.stl", "mm")
    extents_error = np.abs(source.extents - rebuilt.extents)
    report = {
        "scope": "Bounding dimensions and volume only; review holes and local sections separately",
        "source_dimensions_mm": source.extents.tolist(),
        "rebuilt_dimensions_mm": rebuilt.extents.tolist(),
        "dimension_error_mm": extents_error.tolist(),
        "dimensions_match_within_0_01_mm": bool(np.max(extents_error) <= .01),
        "source_origin_mm": source.bounds[0].tolist(),
        "rebuilt_origin_mm": rebuilt.bounds[0].tolist(),
        "source_watertight": bool(source.is_watertight),
        "rebuilt_watertight": bool(rebuilt.is_watertight),
        "source_winding_consistent": bool(source.is_winding_consistent),
        "rebuilt_winding_consistent": bool(rebuilt.is_winding_consistent)}
    if all((source.is_watertight, source.is_winding_consistent, rebuilt.is_watertight, rebuilt.is_winding_consistent)):
        report.update(source_volume_mm3=float(abs(source.volume)),
                      rebuilt_mesh_volume_mm3=float(abs(rebuilt.volume)),
                      volume_change_percent=float(100 * (abs(rebuilt.volume / source.volume) - 1)))
        native_check = model / "检查结果.json"
        if native_check.is_file():
            native = json.loads(native_check.read_text(encoding="utf-8"))
            if native.get("volume_mm3") is not None:
                report["native_solid_volume_mm3"] = native["volume_mm3"]
                report["native_vs_source_mesh_volume_change_percent"] = 100 * (native["volume_mm3"] / abs(source.volume) - 1)
    (model / "对照检查.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["dimensions_match_within_0_01_mm"]:
        raise RuntimeError("Dimension mismatch. Check geometry and STL export units; no automatic rescaling applied.")
    if not rebuilt.is_watertight:
        raise RuntimeError("Exported rebuilt mesh is not watertight")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder")
    compare(p.parse_args().folder)
