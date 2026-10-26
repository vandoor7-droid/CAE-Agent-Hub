# 工作区索引 · CalculiX fork

这个目录既是 DSH 工作区，也是 `vandoor7-droid/CAE-Agent-Hub` 的 `calculix` 分支本地仓库。

- 仓库来历、上游差异、快速上手：见 [`README-CALCULIX.md`](README-CALCULIX.md)
- 迁移数据/流程：见 [`migration/README.md`](migration/README.md) 与
  [`docs/calculix-ultrasonic-migration.md`](docs/calculix-ultrasonic-migration.md)
- 2026-10-26 起另原样镜像上游 **Abaqus / ANSYS / COMSOL** 的 MCP 与 Skill（逐字节复制、
  未做任何改动；见下方目录表与 `README-CALCULIX.md`）

## 目录

| 路径 | 是否入库 | 内容 |
| --- | --- | --- |
| `MCP/CalculiX/` | ✅ | CalculiX MCP server、工具、示例、测试 |
| `Skill/calculix/` | ✅ | 3 个 CalculiX 工作流技能 |
| `MCP/Abaqus/`、`MCP/Abaqus（2020）/`、`MCP/abaqus mcp（2020）` | ✅ | 上游 Abaqus MCP 原样镜像 |
| `MCP/Ansys/` | ✅ | 上游 ANSYS Fluent / Workbench / AEDT / PyAnsys MCP 原样镜像 |
| `MCP/COMSOL/` | ✅ | 上游 COMSOL MCP 原样镜像 |
| `Skill/abaqus/`、`Skill/Ansys/`、`Skill/comsol/` | ✅ | 上游对应技能原样镜像 |
| `docs/` | ✅ | 工程笔记（Abaqus→CalculiX 迁移、TOF、可视化） |
| `patches/viewer-fe-mesh/` | ✅ | 查看器支持 FE 网格的补丁与基准脚本 |
| `migration/` | ✅ 代码 | 迁移脚本；`migration/results/` 是**本地结果**，被忽略 |
| `.dsh/` | ❌ | 本机 DSH 配置：`mcp.yml`（calculix MCP）、`skills/`（技能副本） |
| `.local/` | ❌ | 本机工具与临时清单（gh 推送助手、清理脚本、manifest） |
| `每周总结/` | ❌ | 每周总结归档（个人文件，不随仓库走） |

## 本地环境要点

- CalculiX 2.23 静态版：`D:\ccx_work\bin\ccx.exe`；算例产物一律放 ASCII 路径 `D:\ccx_work\`。
- MCP：`.dsh/mcp.yml` 注册 `calculix`（8 个工具），新的 DSH 会话生效。
- 依赖坑：`mcp<1.8` 依赖 `pydantic._internal._typing_extra.eval_type_backport`，pydantic ≥2.12 已删除该符号，
  因此 `MCP/CalculiX/pyproject.toml` 里固定了 `pydantic<2.12`。
- 本机 git 直连 github 时常被重置；`.local/tools/gh_push.py` 走 GitHub Git Data API 推送，
  提交的 tree/parent/作者/时间与本地一致，因此远端 SHA 与本地相同。
