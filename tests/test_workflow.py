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
from build_model import validate


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


if __name__ == "__main__":
    unittest.main()
