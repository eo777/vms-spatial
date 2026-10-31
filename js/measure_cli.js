'use strict';
// Reference scorer: per-token pool measures with the viewer's own selector and formulas (js/sources.js), from the
// command line, so the Python port (vmsspatial.measures) can be checked against it and so that anyone can score a
// bundle without Python.
//
//   node js/measure_cli.js <bundle.json|.json.gz> <out.json> [--policy strict|sensitivity] [--configs cfg.json]
//
// Without --configs the output holds, per token, the study selector's measures (components, h1, h2, n, pair_ess,
// worddiv, available) and the preceding-99 and following-99 reading-order windows (back_*, fwd_*). With --configs, a JSON
// list of pool shapes [{name, dir ('up'|'down'), left, right, depth, angle, offset, weight, metric, cap}] is scored
// instead (the geometry-sweep form), one block per configuration, plus repeat_out (a twin within 99 tokens outside the
// pool). Config fields follow vmsspatial.selector.PoolSpec.as_dict().
const fs = require('fs'), path = require('path'), zlib = require('zlib');
const S = require(path.join(__dirname, 'sources.js'));

function readJson(p) {
  const buf = fs.readFileSync(p);
  return JSON.parse(p.endsWith('.gz') ? zlib.gunzipSync(buf).toString('utf8') : buf.toString('utf8'));
}

function pool(ctx, pos, cfg) {
  const target = ctx.centers[pos];
  if (!target) return { indices: [], weights: [], available: 0, missingTarget: true };
  const line = ctx.lineOf[pos], page = ctx.pages.get(ctx.data.lines[line].page), cand = [], tan = Math.tan((cfg.angle ?? 45) * Math.PI / 180);
  const up = (cfg.dir || 'up') === 'up', cap = cfg.cap ?? 100, tb0 = ctx.geometry[pos];
  // target 'cursor': a provisional box one median word wide at the leading edge (left for up, right for the mirror)
  const tx = cfg.target === 'cursor' ? (up ? tb0[0] + page.wordWidth / 2 : tb0[2] - page.wordWidth / 2) : target.x, ax = tx + (cfg.offset || 0) * page.wordWidth;
  for (const i of page.indices) {
    if (up) { if (i >= pos) break; } else if (i <= pos) continue;
    const b = ctx.centers[i];
    if (!b) continue;
    let distance, alignment = 1;
    if (ctx.lineOf[i] === line) {
      const dx = b.x - tx;
      if (up) { if (!cfg.left || dx >= 0 || -dx > cfg.left * page.wordWidth) continue; distance = -dx / page.wordWidth; }
      else { if (!cfg.right || dx <= 0 || dx > cfg.right * page.wordWidth) continue; distance = dx / page.wordWidth; }
      if (cfg.metric === 'edge') {
        const tb = ctx.geometry[pos], nb = ctx.geometry[i];
        const gap = up ? tb[0] - nb[2] : nb[0] - tb[2];
        distance = 1 + Math.max(0, gap) / page.wordWidth;
      }
    } else {
      if (!cfg.depth) continue;
      const box = ctx.geometry[i];
      const dy = up ? target.y - b.y : b.y - target.y;
      const near = up ? Math.max(0, target.y - box[3]) : Math.max(0, box[1] - target.y);
      const far = up ? Math.min(cfg.depth * page.pitch, target.y - box[1]) : Math.min(cfg.depth * page.pitch, box[3] - target.y);
      const horizontal = Math.max(box[0] - ax, ax - box[2], 0);
      if (dy <= 0 || far <= 0 || near > far || horizontal > far * tan + 1e-8) continue;
      const ddx = b.x - ax;
      distance = Math.hypot(ddx, dy) / page.pitch;
      alignment = dy * dy / (ddx * ddx + dy * dy);
    }
    cand.push({ i, distance, w: cfg.weight === 'uniform' ? 1 : alignment / (1 + distance) ** 2 });
  }
  cand.sort((a, b) => b.w - a.w || a.distance - b.distance || (up ? b.i - a.i : a.i - b.i));
  const chosen = cand.slice(0, cap).sort((a, b) => a.i - b.i);
  return { indices: chosen.map(x => x.i), weights: chosen.map(x => x.w), available: cand.length, missingTarget: false };
}

function main() {
  const args = process.argv.slice(2);
  const inPath = args[0], outPath = args[1];
  let policy = 'strict', configs = null, metric = 'centre', targetMode = 'box';
  for (let k = 2; k < args.length; k++) {
    if (args[k] === '--policy') policy = args[++k];
    else if (args[k] === '--configs') configs = readJson(args[++k]);
    else if (args[k] === '--metric') metric = args[++k];
    else if (args[k] === '--target') targetMode = args[++k];
  }
  const d = readJson(inPath);
  const c = S.prepare(d, { policy });
  const n = d.words.length, num = x => (Number.isFinite(x) ? x : null);
  const out = {};
  if (!configs) {
    for (const k of ['components', 'h1', 'h2', 'n', 'ess', 'pair_ess', 'worddiv', 'available', 'back_components', 'back_h2', 'fwd_components', 'fwd_h2']) out[k] = new Array(n).fill(null);
    const options = { left: 3, depth: 8, angle: 45, weight: 'distance', metric, target: targetMode };
    for (let i = 0; i < n; i++) {
      const s = S.measure(c, S.sourcePool(c, i, 100, options));
      out.components[i] = num(s.components); out.h1[i] = num(s.h1); out.h2[i] = num(s.h2);
      out.n[i] = s.n; out.ess[i] = num(s.ess); out.pair_ess[i] = num(s.pairEss); out.worddiv[i] = num(s.worddiv); out.available[i] = s.available;
      const b = S.measure(c, S.windowPool(c, i - 1, 99, 'backward'));
      out.back_components[i] = num(b.components); out.back_h2[i] = num(b.h2);
      const f = S.measure(c, S.windowPool(c, i + 1, 99, 'forward'));
      out.fwd_components[i] = num(f.components); out.fwd_h2[i] = num(f.h2);
    }
  } else {
    const positions = new Map();
    d.words.forEach((w, i) => { if (!positions.has(w)) positions.set(w, []); positions.get(w).push(i); });
    const repeatOutside = (i, indices) => {
      const P = positions.get(d.words[i]);
      if (P.length === 1) return 0;
      const inPool = new Set(indices);
      for (const j of P) { if (j < i - 99) continue; if (j > i + 99) break; if (j !== i && !inPool.has(j)) return 1; }
      return 0;
    };
    for (const cfg of configs) {
      const block = {};
      for (const k of ['components', 'h1', 'h2', 'worddiv', 'n', 'ess', 'pair_ess', 'available', 'repeat_out']) block[k] = new Array(n).fill(null);
      for (let i = 0; i < n; i++) {
        const p = pool(c, i, cfg), m = S.measure(c, p);
        block.components[i] = num(m.components); block.h1[i] = num(m.h1); block.h2[i] = num(m.h2); block.worddiv[i] = num(m.worddiv);
        block.n[i] = m.n; block.ess[i] = num(m.ess); block.pair_ess[i] = num(m.pairEss); block.available[i] = m.available; block.repeat_out[i] = repeatOutside(i, p.indices);
      }
      out[cfg.name] = block;
    }
  }
  fs.writeFileSync(outPath, JSON.stringify(out));
  console.log(JSON.stringify({ tokens: n, policy, configs: configs ? configs.length : 0 }));
}

if (require.main === module) main();
module.exports = { pool };
