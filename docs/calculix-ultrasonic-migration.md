# 木柱超声场：Abaqus → CalculiX 显式动力学迁移笔记

本文记录把一例木柱超声仿真从 Abaqus 迁到开源 CalculiX（ccx）时踩到的坑、验证方法与
可复现的命令。所有数字均来自本机实测（ccx 2.23 静态构建，Windows，32 核 / 31 GB）。

## 1. 模型与工况

| 项 | 值 |
| --- | --- |
| 几何 | 木柱 φ220 × H300 mm，内部空洞 r12 × h40 mm |
| 材料 | 木材，E = 1340 MPa，ν = 0.3，ρ = 6e-10 t/mm³ |
| 单元 | C3D8R；细网 1,127,850 节点 / 1,101,180 单元（2.5 mm），粗网 215,585 节点 / 207,374 单元（5 mm） |
| 激励 | 50 kHz 五周期汉宁窗，U1 = 1e-4 mm，作用于柱面一点，方向沿径向 |
| 时长 | 0.22 ms（TOF 扫描）/ 0.3 ms（场输出） |
| 观测 | 18 个周向传感器，两两 17 条路径 |

## 2. Abaqus 到 CalculiX 的扁平化

Abaqus 的 part/instance 两层结构在 ccx 里没有对应物，导出后要压成单层：

- `*NODE` / `*ELEMENT` 直接展开，删掉 instance 名；
- `*NSET` / `*ELSET` 每行**最多 16 项**，超出报
  `*ERROR in splitline: there should not be more than 16 entries in a line`；
- `*SOLID SECTION` / `*MATERIAL` / `*ELASTIC` / `*DENSITY` 可原样搬运；
- `*AMPLITUDE` 表（101 点）原样搬运。

**重划网格会让节点集失效。** 粗网是在 `*NODE`/`*ELEMENT` 替换后由 ccx 重新求解的，
Abaqus 导出的 `SENSOR_01..18` 集合在新网格上为空。做法是转换时按坐标就近匹配：
以名义半径 R = 110 mm、高度 Z0 = 150 mm 取 18 个周向点，在网格上找最近节点，
5 mm 粗网的最大偏差约 2.5 mm（半个单元）。转换器遇到空 `SENSOR_*` 集合会自动走这条路。

## 3. 显式积分的三个坑

### 3.1 时间步超过 Courant 限制会**静默**退化成隐式

`*DYNAMIC, DIRECT, EXPLICIT=2` 并不是"永远显式"。当 `dt` 大于临界步长时，ccx 会改用
PaStiX 稀疏直接求解器——不报错、不警告，只是突然变慢并吃掉几个 GB 内存；单元数上百万时
直接崩。

判定特征：

- stdout 出现 `Determining the structure of the matrix` 与
  `Using up to 1 cpu(s) for setting up the structure of the matrix`；
- 内存从 ~2.4 GB 跳到 8 GB 以上；
- 每步耗时从亚秒级变成秒级。

本模型 5 mm 网格的临界步长约 1.265e-7 s，取 `dt = 1.2e-7 s` 稳定；换成 2.5e-7 s 就会退化。

### 3.2 `*STEP` 默认 `INC=100`

不写 `INC=` 时每步只允许 100 个增量，长时程会在中途以
`*ERROR in nonlingeo: max. # of increments reached` 结束，而且 `.dat` 里只有前 100 块。
必须显式写 `*STEP, NAME=..., NLGEOM=NO, INC=<预计增量数 + 余量>`。

### 3.3 `*NODE FILE` 的 `FREQUENCY` 会连带压制 `.dat`

`*NODE PRINT` 的 `FREQUENCY` 只管自己的输出，但只要同一个 step 里有
`*NODE FILE, FREQUENCY=N`，`.dat` 的 `*NODE PRINT` 块也会按 N 抽稀——即使 `*NODE PRINT`
写了 `FREQUENCY=1`。实测 1,843 步的算例只留下 3 块。

要每增量都拿到 `.dat` 时间历史：**不要**在 step 里写 `*NODE FILE`（或用
`frd-mode none` 生成 deck），场输出另跑一次带 `*NODE FILE` 的作业。

## 4. 断点续算

ccx 的 `*RESTART` 是 **step 粒度**的：

```text
*RESTART, WRITE, FREQUENCY=1     # 写在 *STEP 内，每步结束把状态写进 <job>.rout
...
*RESTART, READ, STEP=k           # 续算 deck 的**第一行**，读 <job>.rin
```

续算时作业名可以不同，但必须把上一次的 `<job>.rout` **改名**成新作业名的 `<newjob>.rin`。

一个 `*STEP` 跑满整个 0.22 ms 的写法拿不到中途检查点，所以要主动切段：

1. 把 `[0, T]` 均分成 N 段，每段一个 `*DYNAMIC` step，段内 `*RESTART, WRITE`；
2. 每段的 `*AMPLITUDE` 按**累计时间**平移（第 i 段的表取 `amp(t - t0)`），否则激励会在每段开头重放；
3. `.dat` 的 time 是跨 step 累计的（实测 step1 0.1 µs … step4 2.0 µs），TOF 解析不需要加偏移。

实测验证（25 增量、5 段 vs 一次跑完）：

- 分段与单段的逐增量位移差 `max|Δu| = 4.6e-23 mm`（相对 6.4e-17，机器精度）；
- 跑完前 2 段后改名 `.rin`、以 `*RESTART, READ, STEP=2` 续完 3 段，末态与一次跑完**完全相同**。

代价：`.rout` 很大，215k 节点的粗网约 **570 MB/段**（8 段约 4.5 GB）。作业跑完要删掉，
否则 18 个源的扫描会占掉几十 GB。段数建议 8：每 ~2.5 min 一个检查点，网格重读的额外开销约 13%。

## 5. 时间历史与 TOF

`.dat` 里每个增量一块：

```text
 displacements (vx,vy,vz) for set SENSORS and time  0.1200000E-06
                                    <-- 空行不算块结束
      7311  0.000000E+00  0.000000E+00  0.000000E+00
```

解析时注意块头后有一个空行，不能拿空行当终止符。

TOF 检测规则（与 Abaqus 侧脚本一致）：传感器 `rec` 的观测方向
`ur = u1·cosθ + u2·sinθ`，`θ = 2π(rec-1)/18`；阈值取 `0.05·max|ur|`，
要求其后 10 个点里有 ≥5 个超过阈值，取第一次越阈值的时刻。

## 6. 结果可视化

查看器（`viewer/peridigm.html`）吃的是 `result_mesh.json`：

```text
nodes:    [{label, coordinates:[x,y,z], displacement:[ux,uy,uz]}]        # deformed 可省
elements: [{label, type:"C3D8R", connectivity:[8 个节点], mises: |u| 均值}]
fieldRanges / fieldLabel / deformationScale / timeMs
```

要点：

- **不要在 JSON 里重复存 `deformed`**：它等于 `coordinates + scale·displacement`，前端可以现算。
  实测 65.4 MB → 56.7 MB（−13%）。
- 查看器只画外表面，20.7 万单元展开成 124 万面片后要去掉内部面，剩下 16,226 个边界四边形。
- 去重的实现影响很大：用"排序后拼字符串"当键，20.7 万单元要 661 ms；改成"按最小节点号分桶 + 整数比较"
  后 188 ms（3.5×），面数完全一致（16,226）。
- `peridigm.html` 原本的校验只接受材料点结果（`representation === "material-points"` 且不允许 `elements`），
  有限元结果会被拒；放开该限制后即可直接显示 ccx 的 FE 网格。
- **变形倍数默认 1:1（`deformationScale = 1`）**。超声场的位移只有 1e-5 mm 量级，柱高 300 mm，
  真实比例下肉眼看不到形变；把它放大会让柱子上的网格看起来像刺猬，容易被误读成真实几何。
  因此 `viewer_case.py` 默认不放大，需要示意图时才显式加 `--auto-scale`（让最大位移占对角线 6%）
  或 `--deformation-scale N`，并在图注里写明倍数。色标与 `mises` 字段与倍数无关。

导出命令：

```bash
python MCP/CalculiX/tools/viewer_case.py \
    --inp  run.inp --frd run.frd \
    --out-dir viewer/dist/run \
    --dt 1.2e-7 --time 2.2e-4
# 然后在浏览器打开
#   viewer/peridigm.html?result=/run/result_mesh.json
```

## 7. 实测数字汇总

| 项 | 数值 |
| --- | --- |
| 粗网显式求解 | 2,500 步 / 1,077 s（0.43 s/步，含输出） |
| 5 mm 网格临界步长 | ≈1.265e-7 s；取 1.2e-7 s |
| 分段一致性（5 段 vs 单段） | max\|Δu\| = 4.6e-23 mm |
| 中断续算一致性 | 末态差异 0 |
| `.rout` 体积 | ≈570 MB/段（215k 节点） |
| `result_mesh.json`（20.7 万单元） | 56.7 MB（省掉 `deformed` 后） |
| 表面提取 | 124 万面片 → 16,226 边界四边形 |
| 去重耗时 | 661 ms → 188 ms（3.5×） |
| JSON 解析（56 MB） | ≈206 ms |

## 8. 首个激励源的对照结果

1 号激励源、17 条路径，与 Abaqus 参考到时（`Z00_tof.csv`）逐条对照：

| 分组 | 路径数 | 相对偏差中位数 | 最大 |
| --- | --- | --- | --- |
| 快轴（参考波速 ≥1000 m/s） | 9 | **0.78%** | 10.12% |
| 慢轴（参考波速 <1000 m/s） | 8 | ≈40% | 51.74% |

快轴的 9 条路径偏差在 ±1% 量级，说明粗网的直接路径到时已经可以复现；慢轴 8 条系统性偏早
（ccx 的"首到"比参考早 33–98 µs），解释是这些路径在参考模型里属于绕空洞的绕射分支，
5 mm 网格既解析不出空洞附近的慢速绕射，也会让更快的体波先到。下一步用 2.5 mm 细网做同一个
激励源的校核，才能把"网格分辨率"和"物理机理"分开。
