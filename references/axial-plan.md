# 沿 X 分段的轴类方案

`scripts/build_axial.py` 读取 `模型/建模方案.json`。它适用于沿 X 方向依次相接的圆柱段和固定截面拉伸段，后者可用于法兰或叉形段。每一段会生成一个可编辑的拉伸特征。圆孔由后续切除特征表示。

示例见 [stepped_shaft_plan.json](../examples/stepped_shaft_plan.json)。这是合成尺寸，不能直接用于真实 STL。

```json
{
  "type": "axial_stages",
  "stages": [
    {"name": "shaft", "x0_mm": 0, "x1_mm": 10,
     "center_yz_mm": [15, 15], "diameter_mm": 12},
    {"name": "flange", "x0_mm": 10, "x1_mm": 13,
     "outline_yz_mm": [[0, 0], [30, 0], [30, 30], [0, 30]]}
  ],
  "cuts": [
    {"name": "bore", "axis": 0, "coordinate_mm": 13, "depth_mm": 13,
     "circles": [{"center_mm": [13, 15, 15], "diameter_mm": 4}]}
  ]
}
```

- 各段按 X 从小到大排列，首段从 X=0 开始，相邻段的端点相同。若 STL 原点不同，先记录平移并把方案坐标变到以 X=0 为起点的坐标系；不要改动原始 STL。
- 一段只能包含 `diameter_mm` 加 `center_yz_mm`，或 `outline_yz_mm`。轮廓至少三个点，不能自交。仅支持固定截面的拉伸。厚度沿 X 变化的自由形态须改用专用脚本。
- 每个 `cuts` 在实际 CAD 的平面上作圆并按 `depth_mm` 切入实体。`axis` 为面法向轴，X/Y/Z 分别是 0/1/2。`coordinate_mm` 是该面的坐标，圆心的相应坐标必须相同。可在一个特征中绘制多个圆。
- 数值截面用 `inspect_mesh.py --sections` 提取。报告中的 `point_axes` 说明二维坐标轴。针对圆柱段，优先拟合真实圆和中心位置；针对异形截面，选合理的轮廓点并说明最大简化误差。大段不规则轮廓不能用少数任意点草率替代。
- 当前构造器从现有实体的平面开始拉伸或切除，因此各段必须接触且合并为一个实体。某一段处于悬空、多实体或需要放样时，由 Agent 编写专用建模脚本。

先运行 `python scripts/build_axial.py 目标目录 --year 2024`。它会检验方案，连接目标版本的 SolidWorks，创建原生特征，检查实体并保存重开。失败后查看 `模型/检查结果.json`，修复方案或特征，再用新的目标目录重试。不要把失败零件当作已交付成品。
