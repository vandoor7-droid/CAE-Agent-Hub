# CalculiX 迁移工程（木柱超声 TOF）

木柱超声仿真项目（Z00 基准工况）从 Abaqus 迁移到 CalculiX 的配套脚本与流程。
工程记录在 [`../docs/calculix-ultrasonic-migration.md`](../docs/calculix-ultrasonic-migration.md)，
MCP 工具在 [`../MCP/CalculiX/`](../MCP/CalculiX/)，技能在 [`../Skill/calculix/`](../Skill/calculix/)。

**本目录只提交代码；算例结果与中间文件一律只在本地。** `results/` 已被根 `.gitignore` 忽略。

## 环境

- `ccx` 2.23 静态版：`D:\ccx_work\bin\ccx.exe`
- Python ≥3.10（脚本只用标准库）
- 算例工作目录必须是 ASCII 路径：`D:\ccx_work\z00\`（ccx 对中文路径不友好）

## 目录

| 路径 | 内容 |
| --- | --- |
| `scripts/make_ccx_inp.py` | Abaqus 导出 deck → 扁平 CalculiX deck（分段、自动匹配传感器、`--frd-mode`） |
| `scripts/run_parallel.py` | 多源并行跑 TOF 算例，合并 `tof_ccx_all.csv`（带 `.done` 断点标记） |
| `scripts/run_campaign.py` | 单线程旧版扫源脚本（保留作参考） |
| `scripts/parse_dat_history.py` | 解析 `.dat` 时间历程，检测首到（TOF） |
| `scripts/compare_tof.py` | 与 Abaqus 参考逐路径对照，输出 markdown 报告 |
| `scripts/frd_to_dat.py` | `.frd` → 帧数据 |
| `scripts/export_viewer_case.py` | 导出查看器用 `result_mesh.json` |
| `scripts/restart_probe.py` | 断点续算可行性探针 |
| `scripts/clean_intermediates.py` | 清理 `.rout/.frd/.inp` 等大件中间文件 |
| `results/` | **本地**：`src01/`、`all/`、`fine/` 的 csv 与对照报告 |

## 流程

```bash
# 0. 参考数据（Abaqus 306 条路径）
#    D:\文档\木结构超声仿真_20260809\tof\Z00_tof.csv

# 1. 粗网 8 段 TOF deck（5 mm，21.6 万节点 / 20.7 万单元）
python scripts/make_ccx_inp.py D:/ccx_work/z00/Z00_coarse.inp \
    D:/ccx_work/z00/Z00_coarse_tof8.inp \
    --dt 1.2e-7 --time 2.2e-4 --segments 8 --frd-mode none --print-freq 1

# 2. 18 个激励源全扫（306 条路径）；--sources 必须含 1，否则合并时丢 17 行
python scripts/run_parallel.py --base D:/ccx_work/z00/Z00_coarse_tof8.inp \
    --work D:/ccx_work/z00/campaign --jobs 4 --sources 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18

# 3. 对照
python scripts/compare_tof.py --ref "D:/文档/木结构超声仿真_20260809/tof/Z00_tof.csv" \
    --ccx D:/ccx_work/z00/campaign/tof_ccx_all.csv --out results/all/compare_all.md

# 4. 2.5 mm 细网单源校核（dt 取粗网临界步长的一半；4 段）
python scripts/make_ccx_inp.py D:/ccx_work/z00/Z00.inp \
    D:/ccx_work/z00/Z00_fine_tof4.inp \
    --dt 6.3e-8 --time 2.2e-4 --segments 4 --src SRC --frd-mode none --print-freq 1
python scripts/run_parallel.py --base D:/ccx_work/z00/Z00_fine_tof4.inp \
    --work D:/ccx_work/z00/campaign_fine --jobs 1 --sources 1

# 5. 清中间件（默认 dry-run，确认后加 --apply）
python scripts/clean_intermediates.py D:/ccx_work/z00/campaign
```

## 产物与体积（决定什么时候清）

| 产物 | 量级 | 去留 |
| --- | --- | --- |
| `*.rout`（断点续算） | 粗网 ≈570 MB/段；细网 ≈2.9 GB/段 | 跑完即删，`run_parallel.py` 成功时自动删 |
| `*.frd`（场输出） | 34–173 MB | 只在校核帧数据时需要，删 |
| `*.inp`（每源 deck） | 25 MB（粗）/ 129 MB（细） | 可由底 deck 一条命令再生，删 |
| `*.dat`（时间历程） | 2 MB/源 | 保留（重算对照要用） |
| `tof_ccx_all.csv` / 报告 | 几十 KB | 保留在 `results/`（本地，不入库） |

## 判定口径

- 单条路径：\|Δ\| ≤5% 为目标，≤10% 可接受；
- 快轴组（参考视速度 ≥1000 m/s）参考均值 1558 m/s、慢轴 721 m/s，各允许 ±10%；
- TOF 检测规则与 Abaqus 参考脚本 `abaqus/export_all_paths.py` 逐字一致
  （`u_r = u1·cosθ + u2·sinθ`，阈值 `5%·max|u_r|`，其后 10 点中 ≥5 点越阈）。
