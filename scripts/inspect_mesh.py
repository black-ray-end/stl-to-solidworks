"""Fast, text-first STL inspection for an agent planning native CAD features."""
import argparse
import json
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Polygon

AXES = {"X": 0, "Y": 1, "Z": 2}
SCALES = {"mm": 1., "cm": 10., "m": 1000., "inch": 25.4}


def inspect(source, units, axis="X", sections=(), tolerance=.15, max_points=80):
    mesh = trimesh.load(str(source), force="mesh", process=True)
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
        raise ValueError("Input has no triangle mesh")
    if not np.isfinite(mesh.vertices).all():
        raise ValueError("Input has nonfinite coordinates")
    mesh.apply_scale(SCALES[units])
    if np.any(mesh.extents <= 0):
        raise ValueError("All three dimensions must be positive")
    axis = axis.upper()
    if axis not in AXES:
        raise ValueError("axis must be X, Y or Z")
    if tolerance < 0 or not np.isfinite(tolerance):
        raise ValueError("simplification tolerance must be nonnegative")
    idx = AXES[axis]
    cross = [i for i in range(3) if i != idx]
    levels, counts = np.unique(np.round(mesh.vertices[:, idx], 3), return_counts=True)
    prominent = sorted(zip(levels, counts), key=lambda item: (-item[1], item[0]))[:30]
    report = {
        "source": Path(source).name,
        "units": "mm",
        "triangles": int(len(mesh.faces)),
        "components": int(len(mesh.split(only_watertight=False))),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "bounds_mm": mesh.bounds.tolist(),
        "dimensions_mm": mesh.extents.tolist(),
        "volume_mm3": float(abs(mesh.volume)) if mesh.is_watertight and mesh.is_winding_consistent else None,
        "axis": axis,
        "prominent_vertex_levels_mm": [[float(x), int(n)] for x, n in prominent],
        "sections": [],
    }
    for position in sections:
        position = float(position)
        if not mesh.bounds[0, idx] < position < mesh.bounds[1, idx]:
            raise ValueError(f"Section {position} lies outside the mesh")
        origin = np.zeros(3)
        normal = np.zeros(3)
        origin[idx] = position
        normal[idx] = 1
        section = mesh.section(plane_origin=origin, plane_normal=normal)
        loops = []
        if section is not None:
            for line in section.discrete:
                polygon = Polygon(line[:, cross])
                if abs(polygon.area) < 1e-6:
                    continue
                simplified = polygon.simplify(tolerance, preserve_topology=True)
                points = np.asarray(simplified.exterior.coords[:-1], dtype=float)
                if len(points) > max_points:
                    points = points[np.linspace(0, len(points) - 1, max_points).astype(int)]
                loops.append({
                    "area_mm2": float(abs(polygon.area)),
                    "bounds_mm": list(map(float, polygon.bounds)),
                    "points_mm": points.round(5).tolist(),
                })
        report["sections"].append({
            "coordinate_mm": position,
            "point_axes": ["XYZ"[i] for i in cross],
            "loops": sorted(loops, key=lambda loop: -loop["area_mm2"]),
        })
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("--units", required=True, choices=SCALES)
    parser.add_argument("--axis", default="X", choices=AXES)
    parser.add_argument("--sections", nargs="*", type=float, default=[])
    parser.add_argument("--simplify", type=float, default=.15)
    parser.add_argument("--output", help="Optional full JSON report path")
    args = parser.parse_args()
    result = inspect(args.source, args.units, args.axis, args.sections, args.simplify)
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {key: result[key] for key in (
        "triangles", "components", "watertight", "dimensions_mm", "volume_mm3",
        "axis", "prominent_vertex_levels_mm")}
    summary["sections"] = [{"coordinate_mm": item["coordinate_mm"],
                            "loop_areas_mm2": [round(loop["area_mm2"], 2) for loop in item["loops"]]}
                           for item in result["sections"]]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
