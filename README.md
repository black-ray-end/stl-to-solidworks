# STL to SolidWorks Skill

把拓扑优化后的 STL 转成描图资料，再由 AI 助手在 SolidWorks 中重建可编辑零件。默认优先使用 **SolidWorks 2024**。

**1.1.0 默认采用精简验收。** 合并重复检查，模型保存并通过目标版本重开后先提供文件，再完成一次关键轮廓对照。详细数值报告和额外图片按需生成。

适合板件、方管、规则孔和主要轮廓可以用草图切除表达的简单零件。它不是任意 STL 自动恢复原 CAD 的转换器。建模方案由助手根据视图和 STL 分析生成，本地脚本负责重复的出图、建模与保存。

## 安装为 skill

将整个仓库目录下载并命名为 `stl-to-solidworks`，放入：

```text
Windows: %USERPROFILE%\.codex\skills\stl-to-solidworks
```

目录内应直接有 `SKILL.md`，不要多套一层。在支持读取技能目录的助手中使用；如果未立即出现，重新打开会话。

需要 Python 3.10 或更高版本。建议在虚拟环境安装依赖：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

视图脚本可跨平台运行。SolidWorks 建模脚本需要 Windows、已经安装且可正常运行的 SolidWorks，以及用户自己的许可。软件和许可不包含在本仓库中。无需 API 密钥或付费云渲染。

## 使用

向助手提供 STL，并说明单位、目标目录和软件版本，例如：

> 使用 $stl-to-solidworks。输入是我上传的支架 STL，单位毫米。请先提取各方向 PNG，再使用 SolidWorks 2024 重建完整零件，最后把原始 STL 和原生零件放在“模型”，把图片放在“视图”。

助手会完成视图提取、几何分析、建模方案、SolidWorks 特征建模和检查。重要尺寸无法从网格确认时会询问，不会自行补出隐藏结构。

也可以只生成描图资料：

```powershell
python scripts/prepare.py "part.stl" --units mm --output "output\part" --inset 1
```

`--units` 必填，支持 `mm`、`cm`、`m`、`inch`。`--inset` 为从外边界向内的深度，单位始终是毫米。薄壁件应使深度落在壁厚内。目标目录必须尚不存在。

默认生成 13 张 PNG，包括六方向外观参考 `view.png`、六张该侧薄层投影 `layer.png` 和一张总览。PNG 配有坐标与尺寸。使用 SolidWorks 草图图片时，要按已知尺寸校准。没有 DXF 导入依赖。

内部结构需要确认时，在 prepare 命令末尾加 `--sections`，另外生成六张真实平面截面图。默认不会计算和绘制这些截面。

方案准备好后运行：

```powershell
python scripts/build_model.py "output\part" --year 2024
```

构造器一次完成实体检查、保存、目标版本重开和特征树核对。助手接着核对实际模型的关键尺寸、孔位和主要轮廓，补入同一份检查记录后交付。默认不额外导出验证 STL，也不计算整件投影重合率。

需要详细数值对照时，可在建模命令中加 `--detailed`，然后运行 `python scripts/compare.py "output\part"`。已有模型只需另行导出验证 STL，不必重新建模。尺寸或形状出现具体异常时，会针对异常补查。

方案格式和支持范围见 [references/plan-format.md](references/plan-format.md)。默认构造器支持沿 X 拉伸的长方体/矩形管，以及外侧平面上的圆孔和闭合样条切除。其他形状由助手编写独立建模脚本，不能仅靠现有命令自动完成。

## 交付文件

```text
part/
├─ 模型/
│  ├─ 原始.stl
│  ├─ 重建.SLDPRT
│  ├─ 项目.json
│  ├─ 建模方案.json
│  └─ 检查结果.json
└─ 视图/
   ├─ 总览.png
   ├─ X_plus_view.png
   ├─ X_plus_layer.png
   ├─ ...其他方向...
   └─ 坐标与轮廓.json
```

详细模式下，用于验证的重建 STL 放在 `模型/验证/`，可另生成 `对照检查.json`。失败时会保留状态和已有资料，便于定位问题，不会覆盖原文件。

如果 SolidWorks 中已打开另一个项目的同名零件，本次原生文件会加上项目名后缀。实际文件名记录在项目和检查 JSON 中，避免同名文档导致无法重新打开。

## 精度与版本

STL 中的圆是多边形，拟合为真实圆柱后，体积与面片模型可能略有不同。应检查孔位、厚度、外形和关键截面，不能只凭体积接近认定模型正确。

只生成图片不会生成 SLDPRT。原生零件由实际安装的 SolidWorks 创建。工具会检查实际运行版本、保存后重新打开并检查实体。2025 原生文件不能作为 2024 原生交付，使用 STEP 也不能保留原来的特征树。

本版在 Windows、Python 3.11 和本机 SolidWorks 2024 上进行测试；测试详情见 `TESTING.md`。复杂有机曲面和内部晶格不在默认构造器范围内。


