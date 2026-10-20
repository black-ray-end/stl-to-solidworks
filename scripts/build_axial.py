"""Build a staged X-axis part from circles and editable section outlines in SolidWorks."""
import argparse
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from sw_api import connect, template_path


def validate(plan):
    if plan.get("type") != "axial_stages":
        raise ValueError("type must be axial_stages")
    stages = plan.get("stages", [])
    if not stages:
        raise ValueError("At least one stage is required")
    for index, stage in enumerate(stages):
        x0, x1 = float(stage["x0_mm"]), float(stage["x1_mm"])
        if not np.isfinite([x0, x1]).all() or x1 <= x0:
            raise ValueError("Stage X limits must be finite and increasing")
        if index == 0 and abs(x0) > 1e-7:
            raise ValueError("First stage must begin at X=0; record the STL offset separately")
        if index and abs(x0 - float(stages[index - 1]["x1_mm"])) > 1e-5:
            raise ValueError("Stages must be adjacent and ordered")
        circle = "diameter_mm" in stage
        outline = "outline_yz_mm" in stage
        if circle == outline:
            raise ValueError("Each stage needs exactly one diameter or outline")
        if circle:
            center = np.asarray(stage["center_yz_mm"], dtype=float)
            diameter = float(stage["diameter_mm"])
            if center.shape != (2,) or not np.isfinite(center).all() or not np.isfinite(diameter) or diameter <= 0:
                raise ValueError("Invalid circular stage")
        else:
            points = np.asarray(stage["outline_yz_mm"], dtype=float)
            if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all():
                raise ValueError("Invalid stage outline")
            polygon = Polygon(points)
            if not polygon.is_valid or polygon.area <= 0:
                raise ValueError("Stage outline intersects itself or has zero area")
    for operation in plan.get("cuts", []):
        axis = int(operation["axis"])
        coordinate = float(operation["coordinate_mm"])
        depth = float(operation["depth_mm"])
        if axis not in (0, 1, 2) or not np.isfinite([coordinate, depth]).all() or depth <= 0:
            raise ValueError("Invalid cut plane or depth")
        circles = operation.get("circles", [])
        if not circles:
            raise ValueError("A cut requires one or more circles")
        for circle in circles:
            center = np.asarray(circle["center_mm"], dtype=float)
            diameter = float(circle["diameter_mm"])
            if (center.shape != (3,) or not np.isfinite(center).all()
                    or abs(center[axis] - coordinate) > 1e-5
                    or not np.isfinite(diameter) or diameter <= 0):
                raise ValueError("Invalid circle or circle off its sketch plane")
    return stages


def build(folder, year=2024, template=None):
    folder = Path(folder).resolve()
    model_dir = folder / "模型"
    plan = json.loads((model_dir / "建模方案.json").read_text(encoding="utf-8"))
    stages = validate(plan)
    check_path = model_dir / "检查结果.json"
    if check_path.exists():
        raise FileExistsError("Check report exists; build into a new delivery folder")
    report = {"status": "building", "requested_year": year,
              "builder": "build_axial", "comparison_status": "pending"}
    try:
        import win32com.client as win32
        app, types, revision = connect(year)
        report["solidworks_revision"] = revision
        target = model_dir / "重建.SLDPRT"
        open_names = set()
        for raw_other in app.GetDocuments() or []:
            other = types.IModelDoc2(raw_other._oleobj_)
            if other.GetPathName():
                open_names.add(Path(other.GetPathName()).name.lower())
        if target.name.lower() in open_names:
            stem = "重建_" + folder.name
            target = model_dir / (stem + ".SLDPRT")
            suffix = 2
            while target.name.lower() in open_names or target.exists():
                target = model_dir / (stem + f"_{suffix}.SLDPRT")
                suffix += 1
        if target.exists():
            raise FileExistsError(target)
        report["native_file"] = target.name

        raw_doc = app.NewDocument(template_path(app, year, template), 0, 0, 0)
        if raw_doc is None:
            raise RuntimeError("Could not create a part")
        doc = types.IModelDoc2(raw_doc._oleobj_)
        part = types.IPartDoc(doc._oleobj_)
        sketch = doc.SketchManager
        feature_names = []

        def local(world_mm):
            active = types.ISketch(sketch.ActiveSketch._oleobj_)
            transform = np.asarray(active.ModelToSketchTransform.ArrayData)
            xyz = np.asarray(world_mm, dtype=float).reshape(-1, 3) / 1000
            points = xyz @ transform[:9].reshape(3, 3) + transform[9:12]
            points[:, 2] = 0
            return points

        def select_plane(axis, coordinate):
            if axis == 0 and abs(coordinate) < 1e-7 and not feature_names:
                planes = []
                f = doc.FirstFeature()
                while f is not None:
                    f = types.IFeature(f._oleobj_)
                    if f.GetTypeName2() == "RefPlane":
                        planes.append(f)
                    f = f.GetNextFeature()
                doc.ClearSelection2(True)
                if len(planes) < 3 or not planes[2].Select2(False, 0):
                    raise RuntimeError("Cannot select the standard Right Plane")
                return
            bodies = part.GetBodies2(0, False) or []
            if len(bodies) != 1:
                raise RuntimeError("Expected one solid body")
            candidates = []
            for raw_face in bodies[0].GetFaces():
                face = types.IFace2(raw_face._oleobj_)
                box = face.GetBox()
                if (face.GetSurface().IsPlane
                        and abs(box[axis] * 1000 - coordinate) < .02
                        and abs(box[axis + 3] * 1000 - coordinate) < .02):
                    candidates.append(face)
            if not candidates:
                raise RuntimeError(f"No planar CAD face at {'XYZ'[axis]}={coordinate} mm")
            face = max(candidates, key=lambda item: item.GetArea())
            doc.ClearSelection2(True)
            if not types.IEntity(face._oleobj_).Select4(False, None):
                raise RuntimeError("Could not select a planar CAD face")

        def start_sketch(axis, coordinate):
            select_plane(axis, coordinate)
            sketch.InsertSketch(True)
            sketch.AddToDB = True

        def finish_sketch():
            sketch.AddToDB = False
            sketch.InsertSketch(True)

        def add_circle(world_mm, diameter_mm):
            point = local([world_mm])[0]
            if sketch.CreateCircleByRadius(*point, float(diameter_mm) / 2000) is None:
                raise RuntimeError("Circle sketch failed")

        for index, stage in enumerate(stages):
            x0, x1 = float(stage["x0_mm"]), float(stage["x1_mm"])
            start_sketch(0, x0)
            if "diameter_mm" in stage:
                y, z = stage["center_yz_mm"]
                add_circle([x0, y, z], stage["diameter_mm"])
            else:
                yz = np.asarray(stage["outline_yz_mm"], dtype=float)
                xyz = np.column_stack([np.full(len(yz), x0), yz])
                points = local(xyz)
                for i in range(len(points)):
                    if sketch.CreateLine(*points[i], *points[(i + 1) % len(points)]) is None:
                        raise RuntimeError("Stage outline sketch failed")
            finish_sketch()
            feature = doc.FeatureManager.FeatureExtrusion3(
                True, False, False, 0, 0, (x1 - x0) / 1000, 0,
                False, False, False, False, 0, 0, False, False, False, False,
                True, True, True, 0, 0, False)
            if feature is None:
                raise RuntimeError(f"Boss extrusion failed at stage {index + 1}")
            name = stage.get("name", f"Stage_{index + 1}")
            feature.Name = name
            feature_names.append(name)
            doc.EditRebuild3()
            if len(part.GetBodies2(0, False) or []) != 1:
                raise RuntimeError(f"Stage {index + 1} created multiple solid bodies")

        for index, operation in enumerate(plan.get("cuts", [])):
            axis, coordinate = int(operation["axis"]), float(operation["coordinate_mm"])
            start_sketch(axis, coordinate)
            for circle in operation["circles"]:
                add_circle(circle["center_mm"], circle["diameter_mm"])
            finish_sketch()
            depth = float(operation["depth_mm"]) / 1000
            feature = doc.FeatureManager.FeatureCut4(
                True, False, False, 0, 0, depth, depth,
                False, False, False, False, 0, 0, False, False, False,
                False, False, True, True, False, False, False, 0, 0, False, True)
            if feature is None:
                raise RuntimeError(f"Cut failed at operation {index + 1}")
            name = operation.get("name", f"Cut_{index + 1}")
            feature.Name = name
            feature_names.append(name)
            doc.EditRebuild3()
            if len(part.GetBodies2(0, False) or []) != 1:
                raise RuntimeError(f"Cut {index + 1} created multiple solid bodies")

        body = types.IBody2(part.GetBodies2(0, False)[0]._oleobj_)
        faults = int(body.Check3.Count)
        if faults:
            raise RuntimeError(f"SolidWorks body check found {faults} faults")
        volume = float(body.GetMassProperties(1)[3] * 1e9)
        bounds = (np.asarray(body.GetBodyBox()) * 1000).tolist()
        result = doc.Extension.SaveAs(str(target), 0, 1, None, 0, 0)
        if not result[0] or result[1]:
            raise RuntimeError(f"Native save failed: {result}")
        app.CloseDoc(str(target))
        reopened, errors, warnings = app.OpenDoc6(str(target), 1, 1, "", 0, 0)
        if reopened is None or errors or int(warnings) & 128:
            raise RuntimeError(f"Native reopen failed: errors={errors}, warnings={warnings}")
        reloaded = types.IPartDoc(reopened._oleobj_)
        if len(reloaded.GetBodies2(0, False) or []) != 1:
            raise RuntimeError("Reopened model is not one solid")
        names_after_reopen = []
        feature = reopened.FirstFeature()
        while feature is not None:
            feature = types.IFeature(feature._oleobj_)
            names_after_reopen.append(feature.Name)
            feature = feature.GetNextFeature()
        if not set(feature_names).issubset(names_after_reopen):
            raise RuntimeError("Native feature tree was not preserved")
        report.update(status="native_saved_and_reopened", body_count=1,
                      body_check_faults=0, volume_mm3=volume, body_bounds_mm=bounds,
                      features=feature_names, native_reopened=True,
                      reopen_warnings=int(warnings))
        print(f"Native SolidWorks {year} part saved and reopened: {target}", flush=True)
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        check_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        project_path = model_dir / "项目.json"
        if project_path.is_file():
            project = json.loads(project_path.read_text(encoding="utf-8"))
            project["status"] = ("native_ready_local_review_pending"
                                 if report["status"] == "native_saved_and_reopened" else "model_failed")
            if "native_file" in report:
                project["native_file"] = report["native_file"]
            project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--template")
    args = parser.parse_args()
    build(args.folder, args.year, args.template)
