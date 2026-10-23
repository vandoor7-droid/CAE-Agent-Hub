# CAE-Agent-Hub · CalculiX fork

This fork keeps **only the CalculiX-related part** of
[CAE-Agent-Hub](https://github.com/Cai-aa/CAE-Agent-Hub): the CalculiX MCP server,
the CalculiX skills, the engineering notes from migrating an Abaqus ultrasonic
model to CalculiX, and the viewer patches that were needed to display the result.

The upstream repository carries several MCP servers (Peridigm, …), demo models
and a material-point viewer; none of that is needed to run or inspect a CalculiX
job, so it is not mirrored here.

## Layout

```text
MCP/CalculiX/            CalculiX MCP server (FastMCP), tools, examples, tests
Skill/calculix/          workflow skill: inspect → modify → solve → read → export
docs/                    engineering notes
patches/viewer-fe-mesh/  viewer changes for FE results + a reproducible benchmark
migration/               ultrasonic TOF migration scripts (results stay local)
```

## What is different from upstream

| change | file |
| --- | --- |
| new tool: export a `.frd` frame as a viewer `result_mesh.json` | `MCP/CalculiX/tools/viewer_case.py` |
| engineering notes: Abaqus → CalculiX explicit dynamics, restart, TOF, viewer | `docs/calculix-ultrasonic-migration.md` |
| viewer: render full FE meshes, 3.5× faster surface extraction, smaller JSON | `patches/viewer-fe-mesh/` |

## Quick start

```bash
# 1. calculate: solve a deck
python MCP/CalculiX/mcp_server.py --help          # FastMCP server, 8 tools
ccx -i model                                      # or use the MCP "run_solver" tool

# 2. look at it: export one .frd frame for the viewer
python MCP/CalculiX/tools/viewer_case.py \
    --inp model.inp --frd model.frd --out-dir viewer/dist/run \
    --dt 1.2e-7 --time 2.2e-4

# 3. open the viewer (needs the upstream viewer/ tree + the patch applied)
#    http://127.0.0.1:4183/peridigm.html?result=/run/result_mesh.json
cd viewer && npx vite preview --port 4183 --strictPort
```

`viewer_case.py` handles 8-node hex decks (`C3D8`, `C3D8R`, …). It writes
`result_mesh.json` plus a small `cae_project.json`; nodes may omit the redundant
`deformed` array because the viewer recomputes `coordinates + scale * displacement`.

## Numbers from the migration

| item | value |
| --- | --- |
| coarse mesh | 215,585 nodes / 207,374 C3D8R elements (5 mm seed) |
| explicit run | 2,500 increments / 1,077 s |
| Courant limit (5 mm mesh) | ≈1.265e-7 s → used 1.2e-7 s |
| split into 5 dynamic steps | identical to one step: max\|Δu\| = 4.6e-23 mm |
| interrupt + `*RESTART,READ` | final state identical (0 difference) |
| `.rout` size | ≈570 MB per step (215k nodes) |
| `result_mesh.json` | 56.7 MB (65.4 MB with `deformed`) |
| surface extraction | 1,243,844 faces → 16,226 boundary quads |
| dedupe time | 661 ms → 188 ms (3.5×) |

Details, pitfalls and reproduction commands: [docs/calculix-ultrasonic-migration.md](docs/calculix-ultrasonic-migration.md).

## Licence

Upstream code is MIT (see `MCP/CalculiX` and the upstream `LICENSE`); this fork
inherits it.
