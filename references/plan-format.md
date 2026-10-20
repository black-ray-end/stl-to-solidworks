# 建模方案格式

方案保存在 `模型/建模方案.json`，所有长度单位都是毫米。这里的示例是合成尺寸，不来自用户模型。

```json
{
  "base": {
    "type": "tube",
    "size_mm": [100, 16, 12],
    "wall_mm": 1
  },
  "operations": [
    {
      "name": "Upper_holes",
      "axis": 2,
      "side": 1,
      "depth_mm": 1,
      "circles": [
        {"center_mm": [10, 8, 12], "diameter_mm": 3}
      ]
    },
    {
      "name": "Lower_opening",
      "axis": 2,
      "side": -1,
      "depth_mm": 1,
      "loops_mm": [
        [[30, 3, 0], [40, 3, 0], [45, 6, 0], [40, 9, 0], [30, 9, 0], [30, 3, 0]]
      ]
    }
  ],
  "source_origin_mm": [0, 0, 0],
  "notes": "Synthetic example. Verify spline overshoot and the actual source geometry."
}
```

- `base.type` 为 `box` 或 `tube`。矩形截面位于 X=0，沿正 X 拉伸。`size_mm` 是 X、Y、Z 三个尺寸。
- 管壁等厚。非等厚壳体须改用专用脚本。
- 模型原点归一化为原始 STL 包围盒最小值。记录 `source_origin_mm`，世界点转为建模坐标时减去此值；脚本不擅自转换方案中的点。
- `axis` 为平面法向的坐标轴，X=0、Y=1、Z=2。`side=-1` 对应最小边界，`side=1` 对应最大边界。
- `circles.center_mm` 是三维建模坐标，必须位于该面。每个圆可设置自己的直径。
- `loops_mm` 是三维闭合点列，首尾相同。脚本生成插值样条，不把它当作折线；拟合可能过冲，需要检查。
- 每个操作可选 `"loop_mode": "polyline"`，使同一批轮廓点通过线段连接。默认仍是 `spline`。折线有棱角，适合确认失败是否由样条过冲导致；需核对实际外形后才能交付。
- 同一操作中的多个圆或闭合轮廓不能相交或相切。脚本在连接 SolidWorks 前检查输入轮廓的自交与重叠；这不能保证插值后的样条不会过冲。
- 每个操作形成一个盲切除特征，深度从所选外表面向实体内部延伸。需要贯穿时必须给出正确深度。
- 坐标和尺寸使用实数，不能包含 NaN、Infinity。外壳尺寸必须大于零，壁厚不能超过短边的一半。
- 现有构造器不支持装配体、多个分离实体或任意自由曲面。不能用一个盒子替代用户的复杂拓扑形状。
