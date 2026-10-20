"""Build a reviewed feature plan in SolidWorks, defaulting strictly to 2024."""
import argparse
import json
from pathlib import Path
import numpy as np
from sw_api import connect, template_path


def validate(plan):
    base = plan["base"]
    size = np.asarray(base["size_mm"], dtype=float)
    if size.shape != (3,) or not np.isfinite(size).all() or np.any(size <= 0):
        raise ValueError("base.size_mm must contain three positive finite lengths")
    if base["type"] not in ("box", "tube"):
        raise ValueError("Supported bases are box and tube")
    if base["type"] == "tube":
        wall = float(base["wall_mm"])
        if not np.isfinite(wall) or not 0 < wall < min(size[1:]) / 2:
            raise ValueError("Invalid tube wall thickness")
    for op in plan.get("operations", []):
        axis, side = op["axis"], op["side"]
        if axis not in (0, 1, 2) or side not in (-1, 1):
            raise ValueError("Invalid face axis/side")
        depth = float(op["depth_mm"])
        if not np.isfinite(depth) or depth <= 0 or depth > size[axis] + 1e-6:
            raise ValueError("Invalid cut depth")
        circles, loops = op.get("circles", []), op.get("loops_mm", [])
        if not circles and not loops:
            raise ValueError("An operation needs a circle or closed loop")
        points = []
        for c in circles:
            r = float(c["diameter_mm"])
            if not np.isfinite(r) or r <= 0:
                raise ValueError("Invalid circle diameter")
            points.append(c["center_mm"])
        for loop in loops:
            a = np.asarray(loop, dtype=float)
            if a.ndim != 2 or a.shape[1] != 3 or len(a) < 4 or not np.allclose(a[0], a[-1], atol=1e-8, rtol=0):
                raise ValueError("Spline loops need at least four 3D points and identical endpoints")
            points.extend(loop)
        p = np.asarray(points, dtype=float)
        coord = size[axis] if side > 0 else 0.
        if p.ndim != 2 or p.shape[1] != 3 or not np.isfinite(p).all():
            raise ValueError("Invalid sketch coordinates")
        if np.max(np.abs(p[:, axis] - coord)) > 1e-5:
            raise ValueError("Sketch points do not lie on the selected outer plane")
        if np.any(p < -1e-5) or np.any(p > size + 1e-5):
            raise ValueError("Sketch points lie outside the base bounding box")
    return size


def build(folder, year=2024, template=None, detailed=False):
    import pythoncom
    import win32com.client as w
    folder = Path(folder).resolve()
    model = folder / "模型"
    plan = json.loads((model / "建模方案.json").read_text(encoding="utf-8"))
    size = validate(plan)
    native = model / "重建.SLDPRT"
    checkpath = model / "检查结果.json"
    if native.exists() or checkpath.exists():
        raise FileExistsError("Native model or check report exists; use a new target folder")
    report = {"status": "building", "requested_year": year}
    try:
        app, t, revision = connect(year)
        report["solidworks_revision"] = revision
        open_names = set()
        for rawdoc in app.GetDocuments() or []:
            other = t.IModelDoc2(rawdoc._oleobj_)
            other_path = other.GetPathName()
            if other_path:
                open_names.add(Path(other_path).name.lower())
        if native.name.lower() in open_names:
            stem = "重建_" + folder.name
            native = model / (stem + ".SLDPRT")
            index = 2
            while native.name.lower() in open_names or native.exists():
                native = model / (stem + f"_{index}.SLDPRT")
                index += 1
        report["native_file"] = native.name
        raw = app.NewDocument(template_path(app, year, template), 0, 0, 0)
        if raw is None:
            raise RuntimeError("Could not create part from template")
        doc = t.IModelDoc2(raw._oleobj_)
        part = t.IPartDoc(doc._oleobj_)
        sm = doc.SketchManager

        def local(xyz):
            sk = t.ISketch(sm.ActiveSketch._oleobj_)
            transform = np.asarray(sk.ModelToSketchTransform.ArrayData)
            p = np.asarray(xyz, dtype=float) / 1000
            result = p @ transform[:9].reshape(3, 3) + transform[9:12]
            result[:, 2] = 0
            return result

        planes = []
        f = doc.FirstFeature()
        while f is not None:
            f = t.IFeature(f._oleobj_)
            if f.GetTypeName2() == "RefPlane":
                planes.append(f)
            f = f.GetNextFeature()
        if len(planes) < 3:
            raise RuntimeError("Template needs the three standard reference planes")
        doc.ClearSelection2(True)
        if not planes[2].Select2(False, 0):
            raise RuntimeError("Cannot select standard right plane")
        sm.InsertSketch(True)
        sm.AddToDB = True
        _, sy, sz = size
        rings = [[[0, 0, 0], [0, sy, 0], [0, sy, sz], [0, 0, sz]]]
        if plan["base"]["type"] == "tube":
            d = float(plan["base"]["wall_mm"])
            rings.append([[0, d, d], [0, sy - d, d], [0, sy - d, sz - d], [0, d, sz - d]])
        for ring in rings:
            pts = local(ring)
            for i in range(4):
                a, b = pts[i], pts[(i + 1) % 4]
                if sm.CreateLine(*a, *b) is None:
                    raise RuntimeError("Base rectangle failed")
        sm.AddToDB = False
        sm.InsertSketch(True)
        feature = doc.FeatureManager.FeatureExtrusion3(
            True, False, False, 0, 0, float(size[0]) / 1000, 0.,
            False, False, False, False, 0., 0., False, False, False, False,
            True, True, True, 0, 0., False)
        if feature is None:
            raise RuntimeError("Base extrusion failed")
        feature.Name = "Base_" + plan["base"]["type"]
        doc.EditRebuild3()
        bodies = part.GetBodies2(0, False) or []
        if len(bodies) != 1:
            raise RuntimeError("Expected one base solid")
        bbox = np.asarray(bodies[0].GetBodyBox()) * 1000
        if not np.allclose(bbox[:3], 0, atol=.001) or not np.allclose(bbox[3:], size, atol=.001):
            raise RuntimeError("Template plane orientation differs from standard; base coordinates are incorrect")
        names = [feature.Name]
        for index, op in enumerate(plan.get("operations", [])):
            axis, side = op["axis"], op["side"]
            coord = size[axis] / 1000 if side > 0 else 0.
            candidates = []
            for rawface in part.GetBodies2(0, False)[0].GetFaces():
                face = t.IFace2(rawface._oleobj_)
                b = face.GetBox()
                if face.GetSurface().IsPlane and abs(b[axis] - coord) < 1e-7 and abs(b[axis + 3] - coord) < 1e-7:
                    candidates.append(face)
            if not candidates:
                raise RuntimeError(f"No suitable face for operation {index}")
            face = max(candidates, key=lambda f: f.GetArea())
            doc.ClearSelection2(True)
            if not t.IEntity(face._oleobj_).Select4(False, None):
                raise RuntimeError("Cannot select cut plane")
            sm.InsertSketch(True)
            sm.AddToDB = True
            for c in op.get("circles", []):
                p = local([c["center_mm"]])[0]
                if sm.CreateCircleByRadius(*p, float(c["diameter_mm"]) / 2000) is None:
                    raise RuntimeError("Circle creation failed")
            for loop in op.get("loops_mm", []):
                points = local(loop)
                points[-1] = points[0]
                arr = w.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, points.ravel().tolist())
                if sm.CreateSpline2(arr, False) is None:
                    raise RuntimeError("Closed spline creation failed")
            sm.AddToDB = False
            sm.InsertSketch(True)
            depth = float(op["depth_mm"]) / 1000
            cut = doc.FeatureManager.FeatureCut4(
                True, False, False, 0, 0, depth, depth, False, False, False, False,
                0., 0., False, False, False, False, False, True, True,
                False, False, False, 0, 0., False, True)
            if cut is None:
                raise RuntimeError(f"Cut failed at operation {index}")
            cut.Name = op.get("name", f"Cut_{index + 1}")
            names.append(cut.Name)
            doc.EditRebuild3()
            if len(part.GetBodies2(0, False) or []) != 1:
                raise RuntimeError("Cut created disconnected bodies")
        body = t.IBody2(part.GetBodies2(0, False)[0]._oleobj_)
        faults = int(body.Check3.Count)
        if faults:
            raise RuntimeError(f"SolidWorks geometry check found {faults} faults")
        volume = float(body.GetMassProperties(1)[3] * 1e9)
        result = doc.Extension.SaveAs(str(native), 0, 1, None, 0, 0)
        if not result[0] or result[1]:
            raise RuntimeError(f"Native save failed: {result}")
        # Close only this newly created document and reopen in the same checked version.
        # Use the full path: several projects may have the same basename.
        app.CloseDoc(str(native))
        opened, errors, warnings = app.OpenDoc6(str(native), 1, 1, "", 0, 0)
        if opened is None or errors:
            raise RuntimeError(f"Native reopen failed: {errors}")
        if int(warnings) & 128:
            raise RuntimeError("Target was still open after CloseDoc; a real reopen was not verified")
        reopened = t.IPartDoc(opened._oleobj_)
        newbodies = reopened.GetBodies2(0, False) or []
        if len(newbodies) != 1:
            raise RuntimeError("Reopened native model has an unexpected body count")
        feature_names = []
        f = opened.FirstFeature()
        while f is not None:
            f = t.IFeature(f._oleobj_)
            feature_names.append(f.Name)
            f = f.GetNextFeature()
        if not set(names).issubset(feature_names):
            raise RuntimeError("Native feature tree was not preserved")
        report.update(status="native_saved_and_reopened", body_count=1,
                      body_check_faults=faults, volume_mm3=volume, features=names,
                      native_reopened=True, reopen_warnings=int(warnings),
                      notes=plan.get("notes", ""), comparison_status="pending",
                      validation_mode="detailed" if detailed else "standard")
        print(f"Native SolidWorks {year} part saved and reopened: {native}", flush=True)
        # A mesh export is optional. Native checks and local contour review suffice
        # for the standard workflow; export only when a numerical comparison is needed.
        if detailed:
            validation = model / "验证"
            validation.mkdir(exist_ok=True)
            exported = validation / "重建.stl"
            result = opened.Extension.SaveAs(str(exported), 0, 1, None, 0, 0)
            if not result[0] or result[1]:
                raise RuntimeError(f"Validation STL save failed: {result}")
            report["validation_mesh"] = "验证/重建.stl"
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        checkpath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        project_path = model / "项目.json"
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
    parser.add_argument("--detailed", action="store_true", help="Export a mesh for optional numerical comparison")
    args = parser.parse_args()
    build(args.folder, args.year, args.template, detailed=args.detailed)
