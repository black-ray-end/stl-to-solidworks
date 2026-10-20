# STL to SolidWorks Skill

把 STL 转成尺寸、截面和描图资料，再由本地编码 Agent 判断结构，在 SolidWorks 中重建可编辑零件。默认优先使用 **SolidWorks 2024**。Codex、Claude Code 或其他能读取本地文件并调用本机软件的 Agent 均可按 `SKILL.md` 执行。

**1.2.0 增加快速网格检查和轴类建模器。** Agent 先看数值和关键截面，再选普通建模器、轴类建模器或编写本次零件的专用脚本。模型保存并通过目标版本重开后先提供文件，再完成一次关键轮廓对照。

适合板件、方管、分段轴、规则孔和能用草图表示主要轮廓的零件。任意自由曲面或复杂内部结构仍需 Agent 编写专用建模代码，必要时请用户提供尺寸。它不会自动恢复原设计历史。

## 安装为 skill

将整个仓库目录下载并命名为 `stl-to-solidworks`，放入：

```text
Windows: %USERPROFILE%\.codex\skills\stl-to-solidworks
```

目录内应直接有 `SKILL.md`，不要多套一层。在支持读取技能目录的助手中使用；如果未立即出现，重新打开会话。

使用其他编码 Agent 时，把仓库放在该 Agent 可读取的本地目录，要求它先读取仓库根目录的 `SKILL.md`，再提供 STL 路径、单位、输出目录和 SolidWorks 版本。该 Agent 需要能运行 Python、访问本机文件，并能调用已安装的 SolidWorks；仅有网页聊天界面无法直接创建本地 SLDPRT。

需要 Python 3.10 或更高版本。建议在虚拟环境安装依赖：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

视图脚本可跨平台运行。SolidWorks 建模脚本需要 Windows、已经安装且可正常运行的 SolidWorks，以及用户自己的许可。软件和许可不包含在本仓库中。无需 API 密钥或付费云渲染。

## 使用

向本地 Agent 提供 STL，并说明单位、目标目录和软件版本。例如：

> 使用 $stl-to-solidworks。输入是我上传的支架 STL，单位毫米。请先提取各方向 PNG，再使用 SolidWorks 2024 重建完整零件，最后把原始 STL 和原生零件放在“模型”，把图片放在“视图”。

Agent 应按 `SKILL.md` 读取实际 STL，判断应使用哪个建模器。重要尺寸无法从网格确认时会询问，不会自行补出隐藏结构。只把仓库文件放进目录而没有可执行本地任务的 Agent，不会自动生成 SLDPRT。

先取简短的数值报告，必要时仅分析指定截面：

```powershell
python scripts/inspect_mesh.py "part.stl" --units mm --axis X
python scripts/inspect_mesh.py "part.stl" --units mm --axis X --sections 10 30 --output "sections.json"
```

也可以只生成描图资料：

```powershell
python scripts/prepare.py "part.stl" --units mm --output "output\part" --inset 1
```

`--units` 必填，支持 `mm`、`cm`、`m`、`inch`。`--inset` 为从外边界向内的深度，单位始终是毫米。薄壁件应使深度落在壁厚内。目标目录必须尚不存在。

默认生成 13 张 PNG，包括六方向外观参考 `view.png`、六张该侧薄层投影 `layer.png` 和一张总览。PNG 配有坐标与尺寸。使用 SolidWorks 草图图片时，要按已知尺寸校准。没有 DXF 导入依赖。

内部结构需要确认时，在 prepare 命令末尾加 `--sections`，另外生成六张真实平面截面图。默认不会计算和绘制这些截面。

普通板件或矩形管方案准备好后运行：

```powershell
python scripts/build_model.py "output\part" --year 2024
```

分段轴、法兰和可按固定截面拉伸的轴段使用 [轴类方案格式](references/axial-plan.md) 与：

```powershell
python scripts/build_axial.py "output\part" --year 2024
```

其他零件由 Agent 在本次输出的 `模型` 目录编写专用脚本，并按相同规则保存、重开和检查。刚好能运行脚本，不代表形状正确；关键孔与轮廓需要对实际 CAD 再看一次。

构造器一次完成实体检查、保存、目标版本重开和特征树核对。助手接着核对实际模型的关键尺寸、孔位和主要轮廓，补入同一份检查记录后交付。默认不额外导出验证 STL，也不计算整件投影重合率。

普通建模器需要详细数值对照时，可加 `--detailed`，然后运行 `python scripts/compare.py "output\part"`。轴类建模器默认不导出验证 STL；需要对照时从已打开的原生模型另行导出，不必重新建模。尺寸或形状出现具体异常时，只针对异常补查。

普通方案格式见 [references/plan-format.md](references/plan-format.md)。示例方案仅为合成尺寸。Agent 必须从用户的 STL 重新提取自己的尺寸、孔位和轮廓。

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

本版在 Windows、Python 3.11 和本机 SolidWorks 2024 上进行测试；测试详情见 `TESTING.md`。复杂有机曲面和内部晶格仍需要专用处理。不同 Agent 的建模判断也需要逐件核对。

