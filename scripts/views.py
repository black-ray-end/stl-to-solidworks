"""Generate orthographic PNGs and numeric tracing contours. No CAD dependency."""
import argparse
import json
from pathlib import Path
import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection, LineCollection

SCALES = {"mm": 1., "cm": 10., "m": 1000., "inch": 25.4}
VIEWS = [
    ("X_plus", 0, 1, 2, -1, 1), ("X_minus", 0, -1, 2, 1, 1),
    ("Y_plus", 1, 1, 2, 1, 0), ("Y_minus", 1, -1, 2, -1, 0),
    ("Z_plus", 2, 1, 0, 1, 1), ("Z_minus", 2, -1, 0, -1, 1)]


def load_mesh(source, units):
    mesh = trimesh.load(str(source), force="mesh", process=True)
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
        raise ValueError("Input has no triangle mesh")
    if not np.isfinite(mesh.vertices).all():
        raise ValueError("Input has nonfinite coordinates")
    mesh.apply_scale(SCALES[units])
    if np.any(mesh.extents <= 0):
        raise ValueError("All three dimensions must be positive")
    return mesh


def export(source, output, units, inset=1., sections=False):
    if not np.isfinite(inset) or inset <= 0:
        raise ValueError("Inset must be positive, in mm")
    mesh = load_mesh(source, units)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    triangles = mesh.triangles
    bounds = mesh.bounds
    report = {
        "units": "mm", "bounds_mm": bounds.tolist(),
        "dimensions_mm": mesh.extents.tolist(),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "volume_mm3": float(abs(mesh.volume)) if mesh.is_watertight and mesh.is_winding_consistent else None,
        "triangle_count": len(mesh.faces),
        "renderer": "depth-sorted triangle reference, not exact hidden-line removal",
        "views": []}
    fig_all, axes = plt.subplots(6, 2, figsize=(17, 17))
    for row, (name, axis, sign, u, usign, v) in enumerate(VIEWS):
        print(f"Rendering {name}", flush=True)
        xy = np.stack([triangles[:, :, u] * usign, triangles[:, :, v]], axis=-1)
        low = xy.reshape(-1, 2).min(axis=0)
        high = xy.reshape(-1, 2).max(axis=0)
        xy -= low
        width, height = high - low
        depth = min(inset, float(mesh.extents[axis]) * .49)
        coord = bounds[1, axis] - depth if sign > 0 else bounds[0, axis] + depth
        origin = np.zeros(3)
        normal = np.zeros(3)
        origin[axis] = coord
        normal[axis] = 1
        section = np.empty((0, 2, 2))
        if sections:
            segments = trimesh.intersections.mesh_plane(mesh, normal, origin)
            section = np.stack([segments[:, :, u] * usign, segments[:, :, v]], axis=-1) - low
        layer = trimesh.intersections.slice_mesh_plane(mesh, normal * sign, origin, cap=False)
        t = layer.triangles
        polygons = [Polygon(p) for p in np.stack([t[:, :, u] * usign, t[:, :, v]], axis=-1) - low]
        geometry = unary_union([p for p in polygons if p.area > 1e-10])
        loops = []
        for poly in getattr(geometry, "geoms", [geometry]):
            if poly.geom_type == "Polygon":
                loops.extend(np.asarray(r.coords) for r in [poly.exterior, *poly.interiors])
        order = np.argsort(triangles.mean(axis=1)[:, axis] * sign)
        shade = .4 + .5 * np.abs(mesh.face_normals[:, axis])
        colors = np.column_stack([shade * .58, shade * .70, shade * .80, np.ones(len(shade))])

        def draw(ax, mode):
            if mode == "view":
                ax.add_collection(PolyCollection(xy[order], facecolors=colors[order], edgecolors="none"))
            elif mode == "section":
                ax.add_collection(LineCollection(section, colors="#172d46", linewidths=.6))
            else:
                ax.add_collection(LineCollection(loops, colors="#172d46", linewidths=.6))
            margin = max(width, height) * .02
            ax.set(xlim=(-margin, width + margin), ylim=(-margin, height + margin),
                   xlabel=f"{'-' if usign < 0 else '+'}{'XYZ'[u]} (mm)",
                   ylabel=f"+{'XYZ'[v]} (mm)",
                   title=f"{name} {mode} | {width:.3f} x {height:.3f} mm")
            ax.set_aspect("equal")
            ax.grid(alpha=.15)

        modes = ("view", "layer", "section") if sections else ("view", "layer")
        for col, mode in enumerate(modes):
            if col < 2:
                draw(axes[row, col], mode)
            f, ax = plt.subplots(figsize=(5, 13) if height > 2 * width else (13, 5))
            draw(ax, mode)
            f.tight_layout()
            f.savefig(out / f"{name}_{mode}.png", dpi=180)
            plt.close(f)
        report["views"].append({
            "name": name, "axis": axis, "side": sign, "u_axis": u, "u_sign": usign, "v_axis": v,
            "projection_origin_mm": low.tolist(), "size_mm": [float(width), float(height)],
            "section_coordinate_mm": float(coord), "actual_inset_mm": depth,
            "sections_generated": bool(sections),
            "layer_loops_mm": [p.tolist() for p in loops],
            "section_segments_mm": section.tolist()})
    fig_all.tight_layout()
    fig_all.savefig(out / "总览.png", dpi=120)
    plt.close(fig_all)
    (out / "坐标与轮廓.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("--units", required=True, choices=SCALES)
    p.add_argument("--output", required=True)
    p.add_argument("--inset", type=float, default=1.)
    p.add_argument("--sections", action="store_true", help="Also compute and render six plane sections")
    a = p.parse_args()
    export(a.source, a.output, a.units, a.inset, sections=a.sections)
