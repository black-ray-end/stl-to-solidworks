"""Portable smoke tests; SolidWorks integration requires a licensed Windows host."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare import prepare
from build_model import validate, remove_retraced_spurs
from build_axial import validate as validate_axial
from inspect_mesh import inspect


class WorkflowTest(unittest.TestCase):
    def test_units_output_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.stl"
            trimesh.creation.box(extents=[.1, .016, .012]).export(source)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            out = prepare(source, root / "delivery", "m", .5)
            copied = out / "模型" / "原始.stl"
            self.assertEqual(hashlib.sha256(copied.read_bytes()).hexdigest(), before)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertEqual({p.name for p in out.iterdir()}, {"模型", "视图"})
            self.assertEqual(len(list((out / "视图").glob("*.png"))), 13)
            self.assertFalse(list(out.rglob("*.dxf")))
            data = json.loads((out / "视图" / "坐标与轮廓.json").read_text(encoding="utf-8"))
            self.assertTrue(np.allclose(data["dimensions_mm"], [100, 16, 12], atol=.0001))
            self.assertEqual(len(data["views"]), 6)
            for v in data["views"]:
                self.assertGreater(v["actual_inset_mm"], 0)
                self.assertTrue(v["layer_loops_mm"])
                self.assertFalse(v["sections_generated"])
                self.assertFalse(v["section_segments_mm"])
            with self.assertRaises(FileExistsError):
                prepare(source, out, "m", .5)

    def test_sections_are_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.stl"
            trimesh.creation.box(extents=[20, 10, 5]).export(source)
            out = prepare(source, root / "sections", "mm", .5, sections=True)
            self.assertEqual(len(list((out / "视图").glob("*.png"))), 19)
            data = json.loads((out / "视图" / "坐标与轮廓.json").read_text(encoding="utf-8"))
            for v in data["views"]:
                self.assertTrue(v["sections_generated"])
                self.assertTrue(v["section_segments_mm"])

    def test_invalid_geometry_rejected_before_connecting(self):
        for size in ([0, 1, 1], [1, float("nan"), 1], [-1, 1, 1]):
            with self.assertRaises(ValueError):
                validate({"base": {"type": "box", "size_mm": size}})
        with self.assertRaises(ValueError):
            validate({"base": {"type": "tube", "size_mm": [10, 2, 2], "wall_mm": 1}})
        plan = {"base": {"type": "box", "size_mm": [10, 10, 10]},
                "operations": [{"axis": 2, "side": 1, "depth_mm": 1,
                                "circles": [{"center_mm": [5, 5, 0], "diameter_mm": 2}]}]}
        with self.assertRaises(ValueError):
            validate(plan)

    def test_fast_inspection_reports_real_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "shaft.stl"
            trimesh.creation.box(extents=[20, 10, 6]).export(source)
            report = inspect(source, "mm", axis="X", sections=[0])
            self.assertEqual(report["triangles"], 12)
            self.assertEqual(report["components"], 1)
            self.assertTrue(report["watertight"])
            self.assertEqual(len(report["sections"]), 1)
            self.assertAlmostEqual(report["sections"][0]["loops"][0]["area_mm2"], 60)

    def test_axial_plan_validation(self):
        plan = json.loads((Path(__file__).resolve().parents[1] / "examples" /
                           "stepped_shaft_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(len(validate_axial(plan)), 3)
        plan["stages"][1]["x0_mm"] = 11
        with self.assertRaises(ValueError):
            validate_axial(plan)

    def test_cut_contours_rejected_before_solidworks(self):
        base = {"type": "box", "size_mm": [20, 20, 10]}
        crossed = [[2, 2, 10], [8, 8, 10], [2, 8, 10], [8, 2, 10], [2, 2, 10]]
        with self.assertRaisesRegex(ValueError, "self-intersecting"):
            validate({"base": base, "operations": [
                {"axis": 2, "side": 1, "depth_mm": 1, "loops_mm": [crossed]}]})
        square = [[2, 2, 10], [8, 2, 10], [8, 8, 10], [2, 8, 10], [2, 2, 10]]
        with self.assertRaisesRegex(ValueError, "overlapping"):
            validate({"base": base, "operations": [
                {"axis": 2, "side": 1, "depth_mm": 1, "loops_mm": [square],
                 "circles": [{"center_mm": [5, 5, 10], "diameter_mm": 2}]}]})
        valid = {"base": base, "operations": [
            {"axis": 2, "side": 1, "depth_mm": 1, "loop_mode": "polyline",
             "loops_mm": [square]}]}
        self.assertEqual(validate(valid).tolist(), [20, 20, 10])

    def test_view_name_must_match_sketch_plane(self):
        loop = [[2, 2, 0], [8, 2, 0], [8, 8, 0], [2, 8, 0], [2, 2, 0]]
        op = {"name": "X_plus_outline_2", "axis": 2, "side": -1,
              "depth_mm": 2, "loops_mm": [loop]}
        plan = {"base": {"type": "box", "size_mm": [20, 20, 10]},
                "operations": [op]}
        with self.assertRaisesRegex(ValueError, "X_plus.*Z_minus"):
            validate(plan)
        op["name"] = "Z_minus_outline_2"
        self.assertEqual(validate(plan).tolist(), [20, 20, 10])

    def test_retraced_spur_is_removed_without_changing_plan(self):
        loop = [[2, 2, 10], [8, 2, 10], [7, 3, 10], [8, 2, 10],
                [8, 8, 10], [2, 8, 10], [2, 2, 10]]
        plan = {"base": {"type": "box", "size_mm": [20, 20, 10]},
                "operations": [{"axis": 2, "side": 1, "depth_mm": 1,
                                "loops_mm": [loop]}]}
        cleaned, changes = remove_retraced_spurs(plan)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["removed_point_count"], 2)
        self.assertEqual(len(cleaned["operations"][0]["loops_mm"][0]), 5)
        self.assertEqual(len(plan["operations"][0]["loops_mm"][0]), 7)
        self.assertEqual(validate(cleaned).tolist(), [20, 20, 10])


if __name__ == "__main__":
    unittest.main()
