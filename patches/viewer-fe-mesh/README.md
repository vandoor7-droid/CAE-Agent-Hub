# viewer: finite-element results (CalculiX)

Two files from `viewer/` are patched so the shared viewer can display a
CalculiX finite-element result (8-node hex mesh) directly, without a separate
"observation" mesh:

| file | change |
| --- | --- |
| `viewer/components/CaeResultViewer.js` | surface extraction rewritten: integer-bucket interior-face dedupe instead of sort+join string keys; `deformed` recomputed on demand when the JSON omits it |
| `viewer/peridigm.jsx` | accept FE result meshes (the old guard required `representation === "material-points"` and rejected any `elements`); header shows node/element counts; guard the history plot when `dynamicFrames` is missing |
| `viewer/README.md` | documents `?result=/run/result_mesh.json` for FE results |

Apply with:

```bash
cd viewer && git apply ../patches/viewer-fe-mesh/0001-viewer-fe-mesh.patch
```

The patch is generated against LF-normalised files; on a CRLF checkout use
`git apply --ignore-whitespace`, or just copy the three files next to this
README over their counterparts — they are the same content.

## Why the surface builder changed

A 207,374-element hex mesh expands to 1,243,844 quad faces; the interior ones
have to be removed so only the 16,226 boundary faces are drawn. The original
implementation built a string key per face (`sort()` then `join(":")`) and used
it as a `Map` key:

```js
const key = [...labels].sort((a, b) => a - b).join(":");
```

That is ~1.2 M sorts plus string concatenation. The patched version buckets
candidate faces by their smallest node label and compares integer arrays:

```js
const ids = sortIds(fi.map((i) => c[i]));      // 4-element insertion sort
let bucket = buckets.get(ids[0]) ?? [];
const at = bucket.findIndex((f) => same(f, ids));
```

Measured on the same mesh (`viewer/scripts/bench-surface.mjs`):

| | old | new |
| --- | --- | --- |
| interior-face dedupe | 661 ms | **188 ms** (3.5×) |
| boundary faces | 16,226 | 16,226 (identical) |
| JSON parse (56 MB) | 206 ms | 206 ms |

## Why `deformed` is optional

`deformed[i] = coordinates[i] + deformationScale * displacement[i]`, so storing
it triples the coordinate payload for nothing. Dropping it takes the sample case
from 65.4 MB to 56.7 MB (−13%) and the viewer recomputes it while building the
geometry (and in `buildDisplayBounds`, so the framing is unchanged).

## Reproduce

```bash
# 1. export a CalculiX .frd frame as a viewer case
python MCP/CalculiX/tools/viewer_case.py \
    --inp run.inp --frd run.frd --out-dir viewer/dist/run

# 2. serve the built viewer and open
#    http://127.0.0.1:4183/peridigm.html?result=/run/result_mesh.json
cd viewer && npx vite preview --port 4183 --strictPort

# 3. optional: measure the surface builder
node viewer/scripts/bench-surface.mjs viewer/dist/run/result_mesh.json
```
