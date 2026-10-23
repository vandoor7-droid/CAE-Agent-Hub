// Benchmark the viewer's surface builder on a real result_mesh.json.
//
//   node scripts/bench-surface.mjs path/to/result_mesh.json
//
// Compares the current integer-bucket face dedupe with the older string-key
// version (sort labels, join with ":", use as a Map key) and prints the face
// count for both. A mismatch means the optimisation changed the geometry.
import fs from "node:fs";

const path = process.argv[2];
if (!path) {
  console.error("usage: node scripts/bench-surface.mjs <result_mesh.json>");
  process.exit(2);
}

const t0 = performance.now();
const raw = fs.readFileSync(path, "utf8");
const t1 = performance.now();
const mesh = JSON.parse(raw);
const t2 = performance.now();

const HEX = [
  [0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1],
  [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0],
];

function oldDedupe(elements) {
  const faces = new Map();
  for (const el of elements) {
    const c = el.connectivity;
    for (const fi of HEX) {
      const labels = fi.map((i) => c[i]);
      const key = [...labels].sort((a, b) => a - b).join(":");
      if (faces.has(key)) { faces.delete(key); continue; }
      faces.set(key, labels);
    }
  }
  return faces.size;
}

function newDedupe(elements) {
  const buckets = new Map();
  const sortIds = (ids) => {
    for (let i = 1; i < ids.length; i += 1) {
      const v = ids[i];
      let j = i - 1;
      while (j >= 0 && ids[j] > v) { ids[j + 1] = ids[j]; j -= 1; }
      ids[j + 1] = v;
    }
    return ids;
  };
  const same = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
  for (const el of elements) {
    const c = el.connectivity;
    for (const fi of HEX) {
      const ids = sortIds(fi.map((i) => c[i]));
      let bucket = buckets.get(ids[0]);
      if (!bucket) { bucket = []; buckets.set(ids[0], bucket); }
      const at = bucket.findIndex((f) => same(f, ids));
      if (at >= 0) { bucket.splice(at, 1); if (bucket.length === 0) buckets.delete(ids[0]); continue; }
      bucket.push(ids);
    }
  }
  let n = 0;
  for (const b of buckets.values()) n += b.length;
  return n;
}

const t3 = performance.now();
const oldCount = oldDedupe(mesh.elements);
const t4 = performance.now();
const newCount = newDedupe(mesh.elements);
const t5 = performance.now();

console.log(JSON.stringify({
  file: path.split(/[\\/]/).pop(),
  nodes: mesh.nodes.length,
  elements: mesh.elements.length,
  read_ms: Math.round(t1 - t0),
  parse_ms: Math.round(t2 - t1),
  old_string_dedupe_ms: Math.round(t4 - t3),
  old_faces: oldCount,
  new_bucket_dedupe_ms: Math.round(t5 - t4),
  new_faces: newCount,
  same_geometry: oldCount === newCount,
  speedup: Number(((t4 - t3) / Math.max(t5 - t4, 0.001)).toFixed(2)),
}, null, 2));
