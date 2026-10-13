/**
 * L3 爆款因子分析 —— 回答「为什么这几条火」。
 *
 * 用法:
 *   node virality.js --posts workdir/posts.json [--out virality.json] [--md virality.md]
 *                    [--top 0.25] [--perm 2000]
 *
 * ── 方法论（小样本下唯一诚实的做法）────────────────────────
 *
 * 1. 【置换检验 p 值】不假设正态分布、不需要大样本。
 *    把 n 条随机分成同样大小的两组，重复 2000 次，看「真实 TOP-vs-尾部 差异」
 *    在这个随机分布里的位置。p=0.03 表示：随机分组只有 3% 的概率产生这么大的差异。
 *    没有 p 值就谈"爆款因子"，等于在 18 条数据里看星座。
 *
 * 2. 【BH 多重比较校正】检验 10 个因子时，即使全是噪声，也有约 40% 概率
 *    至少冒出一个 p<0.05（1-0.95^10）。所以判定一律用校正后的 p_adj（BH/FDR），
 *    原始 p 值只展示不判定。这是很多"数据分析"翻车的根因。
 *
 * 3. 【控制混杂变量：内容年龄】老作品有更长时间累积点赞，
 *    "TOP 组更老"会被误读成"TOP 组有什么特征"。age_days 单独检验，
 *    若显著则说明整个分组被「发布更早」污染，其他因子结论都要打折。
 *
 * 4. 【分母偏差】分组按 digg 排，再去比 comment/digg 这类比率，
 *    分母本身就是分组依据，高赞作品的比率会被天然压低。
 *    所以互动指标**先看绝对值**，比率只作辅助并标注偏差。
 *
 * 5. 【n<8 拒绝出结论】分组只有 2v2，任何检验都无意义。只给描述性统计。
 *
 * 6. 【相关性 ≠ 因果】p 显著只说明"同时出现"。选题本身才是主因，
 *    图片数/标题长度这类结构化特征很可能只是伴随现象。
 */
const fs = require('fs');
const { loadPosts, postFeatures, mean, round1, round2 } = require('./core');

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

// 固定种子 LCG，保证 p 值可复现（否则每次跑结论都飘，用户没法复现）
let _seed = 20260905;
function rnd() { _seed = (_seed * 1664525 + 1013904223) % 4294967296; return _seed / 4294967296; }
function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}

const meanOf = (vals, idx) => mean(idx.map((i) => vals[i]));
function stdOf(vals, idx) {
  if (idx.length < 2) return 0;
  const m = meanOf(vals, idx);
  return Math.sqrt(idx.reduce((s, i) => s + (vals[i] - m) ** 2, 0) / (idx.length - 1));
}

/** 置换检验：随机划两组（等大）B 次，看真实差异在 null 分布中的分位 */
function permTest(vals, idxA, idxB, B) {
  const obs = meanOf(vals, idxA) - meanOf(vals, idxB);
  const n = vals.length, k = idxA.length;
  if (k < 2 || n < k * 2) return { obs: round2(obs), p: 1, note: '样本不足，未做检验' };
  let cnt = 0;
  for (let b = 0; b < B; b++) {
    const perm = shuffle([...Array(n).keys()]);
    const d = meanOf(vals, perm.slice(0, k)) - meanOf(vals, perm.slice(n - k));
    if (Math.abs(d) >= Math.abs(obs) - 1e-12) cnt++;
  }
  return { obs: round2(obs), p: (cnt + 1) / (B + 1) };
}

function cohensD(vals, idxA, idxB) {
  const nA = idxA.length, nB = idxB.length;
  const sA = stdOf(vals, idxA), sB = stdOf(vals, idxB);
  const pooled = Math.sqrt(((nA - 1) * sA ** 2 + (nB - 1) * sB ** 2) / (nA + nB - 2));
  if (!pooled) return null;
  return round2((meanOf(vals, idxA) - meanOf(vals, idxB)) / pooled);
}

/** Benjamini-Hochberg FDR 校正，就地写入 p_adj */
function bhAdjust(tests) {
  const withP = tests.filter((t) => typeof t.p === 'number');
  const N = withP.length;
  if (!N) return;
  const sorted = [...withP].sort((a, b) => a.p - b.p);
  let prev = 1;
  for (let i = N - 1; i >= 0; i--) {
    const adj = Math.min(prev, (sorted[i].p * N) / (i + 1));
    sorted[i].p_adj = Math.min(1, round2(adj));
    prev = sorted[i].p_adj;
  }
}

const fmtV = (v) => (v === null || v === undefined ? 'N/A' : String(v));
const VMARK = {
  signal: '✅ 值得验证', weak: '🟡 弱信号', noise: '⚪ 噪声范围内',
  unknown: '— 未检验', reference: '— 分组依据',
};

const NUMERIC_FACTORS = [
  { k: 'media_count', label: '图片数', unit: '张' },
  { k: 'title_len', label: '标题长度', unit: '字' },
  { k: 'tag_count', label: '话题数', unit: '个' },
  { k: 'age_days', label: '内容年龄⚠️', unit: '天', note: '混杂变量：越老的作品累积点赞时间越长。若此项显著，其他因子结论都要打折' },
  { k: 'digg', label: '点赞(分组依据)', unit: '', reference: true },
];

const HOUR_BUCKETS = [
  [0, 6, '凌晨0-5点'], [6, 12, '上午6-11点'], [12, 18, '下午12-17点'], [18, 24, '晚间18-23点'],
];
const hourBucket = (h) => (HOUR_BUCKETS.find(([a, b]) => h >= a && h < b) || [0, 0, '未知'])[2];

(async () => {
  const args = parseArgs();
  if (!args.posts) { console.error('用法: node virality.js --posts workdir/posts.json [--out virality.json] [--md virality.md]'); process.exit(1); }

  const data = loadPosts(args.posts);
  const B = parseInt(args.perm || '2000', 10);
  const n = data.posts.length;
  const today = Date.now();
  const tests = []; // 收集所有检验，最后统一 BH 校正

  const feats = data.posts.map((p, i) => {
    const f = postFeatures(p);
    f._i = i;
    f.age_days = p.create_time ? Math.max(0, Math.round((today - new Date(p.create_time + 'T00:00:00Z').getTime()) / 86400000)) : null;
    return f;
  });

  const byDigg = [...feats].sort((a, b) => b.digg - a.digg);
  const k = Math.max(2, Math.min(8, Math.round(n * parseFloat(args.top || '0.25'))));
  const topG = byDigg.slice(0, k).map((f) => f._i);
  const botG = byDigg.slice(-k).map((f) => f._i);
  const tooSmall = n < 8;

  const platform = data.platform;
  const acct = (data.account && data.account.name) || '';

  console.log(`\n═══ 爆款因子分析 · ${acct || '(未命名)'} · ${platform} ═══`);
  console.log(`样本 n=${n} | TOP ${k} 条（赞 ${byDigg[0].digg}~${byDigg[k - 1].digg}） vs 尾部 ${k} 条（赞 ${byDigg[n - k].digg}~${byDigg[n - 1].digg}）`);
  if (tooSmall) {
    console.log(`\n⚠️⚠️ 样本仅 ${n} 条 —— 分组后每组不足 4 条，任何统计检验都无意义。`);
    console.log(`   下面只给描述性统计，不给结论。要做爆款因子分析至少需要 12-15 条样本。`);
  }

  // ── 数值因子 ──
  const numRows = [];
  for (const def of NUMERIC_FACTORS) {
    const vals = feats.map((f) => (f[def.k] === null || f[def.k] === undefined ? null : f[def.k]));
    if (vals.some((v) => v === null)) { numRows.push({ ...def, skipped: '数据不可得' }); continue; }
    if (new Set(vals).size === 1) { numRows.push({ ...def, skipped: '所有作品取值相同，无区分度' }); continue; }

    const row = { ...def, top: round1(meanOf(vals, topG)), bottom: round1(meanOf(vals, botG)), d: cohensD(vals, topG, botG) };
    if (tooSmall) { row.diff = round2(row.top - row.bottom); row.p = null; }
    else {
      const t = permTest(vals, topG, botG, B);
      row.diff = t.obs; row.p = round2(t.p);
      if (!def.reference) tests.push(row);
    }
    numRows.push(row);
  }

  // ── 互动结构：绝对值优先 ──
  const interRows = [];
  const unavailable = data._unavailable || [];
  for (const key of ['comment', 'share', 'collect']) {
    const label = { comment: '评论', share: '分享', collect: '收藏' }[key];
    if (unavailable.includes(key)) { interRows.push({ key, label, skipped: '本平台列表接口不提供' }); continue; }
    const vals = feats.map((f) => (f[key] == null ? 0 : f[key]));
    if (!vals.some((v) => v > 0)) { interRows.push({ key, label, skipped: '全部为 0' }); continue; }

    const diggVals = feats.map((f) => f.digg);
    const row = {
      key, label,
      top_abs: round1(meanOf(vals, topG)), bot_abs: round1(meanOf(vals, botG)),
      d: cohensD(vals, topG, botG),
      // 比率：分母是分组依据，天然有偏，只作参考
      top_ratio_pct: meanOf(diggVals, topG) > 0 ? round1((meanOf(vals, topG) / meanOf(diggVals, topG)) * 100) : null,
      bot_ratio_pct: meanOf(diggVals, botG) > 0 ? round1((meanOf(vals, botG) / meanOf(diggVals, botG)) * 100) : null,
    };
    if (tooSmall) { row.diff = round2(row.top_abs - row.bot_abs); row.p = null; }
    else {
      const t = permTest(vals, topG, botG, B);
      row.diff = t.obs; row.p = round2(t.p);
      tests.push(row);
    }
    interRows.push(row);
  }

  // ── 分类因子：形态 / 时段 / 星期 ──
  // 每个取值做一次「是否属于该类别」的 0/1 置换检验，并纳入 BH 校正
  const catRows = [];
  const catAnalyze = (label, get) => {
    const tv = topG.map((i) => get(feats[i])).filter((x) => x !== null && x !== undefined);
    const bv = botG.map((i) => get(feats[i])).filter((x) => x !== null && x !== undefined);
    if (!tv.length || !bv.length) { catRows.push({ label, skipped: '数据不可得' }); return; }

    const cnt = (a) => { const o = {}; a.forEach((x) => { o[x] = (o[x] || 0) + 1; }); return o; };
    const cT = cnt(tv), cB = cnt(bv);
    const keys = [...new Set([...Object.keys(cT), ...Object.keys(cB)])];
    const items = keys.map((key) => {
      // 0/1 向量：该条作品是否属于这个取值
      const bin = feats.map((f) => (get(f) === key ? 1 : 0));
      const it = {
        key,
        top_pct: Math.round(((cT[key] || 0) / tv.length) * 100),
        bot_pct: Math.round(((cB[key] || 0) / bv.length) * 100),
        top_n: cT[key] || 0, bot_n: cB[key] || 0,
      };
      // 只检验出现 ≥2 次的取值，避免 1/0 这类单点噪声
      if (!tooSmall && it.top_n + it.bot_n >= 2) {
        const t = permTest(bin, topG, botG, B);
        it.p = round2(t.p);
        it.d = cohensD(bin, topG, botG);
        tests.push({ key: `${label}:${key}`, p: it.p, _ref: it });
      }
      return it;
    }).sort((a, b) => (b.top_pct - b.bot_pct) - (a.top_pct - a.bot_pct));
    catRows.push({ label, items, note: '分类变量：把「是否属于该取值」转成 0/1 后做同样的置换检验' });
  };
  catAnalyze('内容形态', (f) => f.media_type);
  catAnalyze('发布时段', (f) => (f.hour === null ? null : hourBucket(f.hour)));
  catAnalyze('发布星期', (f) => f.weekday_cn);

  // ── BH 校正 → 判定 ──
  bhAdjust(tests);
  const decide = (row) => {
    if (row.reference) return 'reference';
    if (tooSmall || row.p === null || row.p === undefined) return 'unknown';
    const pAdj = row.p_adj != null ? row.p_adj : 1;
    const eff = row.d !== null && row.d !== undefined && Math.abs(row.d) >= 0.5;
    if (pAdj < 0.05 && eff) return 'signal';
    if (pAdj < 0.05 || eff) return 'weak';
    return 'noise';
  };
  numRows.forEach((r) => { if (!r.skipped) r.verdict = decide(r); });
  interRows.forEach((r) => { if (!r.skipped) r.verdict = decide(r); });
  for (const t of tests) if (t._ref) t._ref.p_adj = t.p_adj;
  catRows.forEach((r) => (r.items || []).forEach((it) => {
    if (it.p === undefined) { it.verdict = 'unknown'; return; }
    const pAdj = it.p_adj != null ? it.p_adj : 1;
    const eff = it.d !== null && it.d !== undefined && Math.abs(it.d) >= 0.5;
    it.verdict = pAdj < 0.05 && eff ? 'signal' : (pAdj < 0.05 || eff ? 'weak' : 'noise');
  }));

  // ── 控制台输出 ──
  const padTo = (s, w) => { let x = String(s); let d = [...x].reduce((a, c) => a + (c.charCodeAt(0) > 255 ? 2 : 1), 0); while (d < w) { x += ' '; d++; } return x; };

  console.log('\n──── TOP vs 尾部 · 数值因子 ────');
  console.log('  ' + padTo('因子', 18) + padTo('TOP组', 10) + padTo('尾部组', 10) + padTo('差值', 10) + padTo("Cohen's d", 11) + padTo('p', 8) + padTo('p_adj', 8) + '判定');
  for (const r of numRows) {
    if (r.skipped) { console.log('  ' + padTo(r.label, 18) + `— ${r.skipped}`); continue; }
    console.log('  ' + padTo(r.label, 18) + padTo(r.top, 10) + padTo(r.bottom, 10) + padTo(r.diff, 10)
      + padTo(fmtV(r.d), 11) + padTo(fmtV(r.p), 8) + padTo(fmtV(r.p_adj), 8) + VMARK[r.verdict]);
    if (r.note) console.log('      ' + r.note);
  }

  console.log('\n──── 互动结构（绝对值优先，比率有分母偏差）────');
  console.log('  ' + padTo('指标', 10) + padTo('TOP均', 9) + padTo('尾部均', 9) + padTo('差值', 9) + padTo('p', 8) + padTo('p_adj', 8) + padTo('TOP占赞%', 11) + padTo('尾部占赞%', 11) + '判定');
  for (const r of interRows) {
    if (r.skipped) { console.log('  ' + padTo(r.label, 10) + `— ${r.skipped}`); continue; }
    console.log('  ' + padTo(r.label, 10) + padTo(r.top_abs, 9) + padTo(r.bot_abs, 9) + padTo(r.diff, 9)
      + padTo(fmtV(r.p), 8) + padTo(fmtV(r.p_adj), 8) + padTo(fmtV(r.top_ratio_pct), 11) + padTo(fmtV(r.bot_ratio_pct), 11) + VMARK[r.verdict]);
  }

  console.log('\n──── 分类因子（0/1 置换检验）────');
  for (const r of catRows) {
    if (r.skipped) { console.log(`  ${r.label}：${r.skipped}`); continue; }
    console.log(`  ${r.label}`);
    for (const it of r.items) {
      const extra = it.p === undefined ? '（出现次数 <2，未检验）' : `p=${it.p} p_adj=${fmtV(it.p_adj)} ${VMARK[it.verdict]}`;
      console.log(`     ${padTo(it.key, 12)} TOP ${padTo(it.top_pct + '%(' + it.top_n + ')', 11)} 尾部 ${padTo(it.bot_pct + '%(' + it.bot_n + ')', 11)} ${extra}`);
    }
  }

  // ── 结论 ──
  const signals = numRows.filter((r) => r.verdict === 'signal');
  const interSignals = interRows.filter((r) => r.verdict === 'signal');
  const catSignals = [];
  catRows.forEach((r) => (r.items || []).forEach((it) => { if (it.verdict === 'signal') catSignals.push({ group: r.label, ...it }); }));
  const ageRow = numRows.find((r) => r.k === 'age_days');
  const confounded = ageRow && ageRow.verdict === 'signal';

  const findings = [];
  signals.forEach((r) => findings.push(`${r.label}：TOP ${r.top}${r.unit} vs 尾部 ${r.bottom}${r.unit}（差 ${r.diff}，d=${r.d}，p_adj=${r.p_adj}）—— ${r.diff > 0 ? 'TOP 更高' : 'TOP 更低'}`));
  interSignals.forEach((r) => findings.push(`${r.label}（绝对值）：TOP 均 ${r.top_abs} vs 尾部 ${r.bot_abs}（d=${r.d}，p_adj=${r.p_adj}）—— 高赞内容的${r.label}绝对量确实更大`));
  catSignals.forEach((c) => findings.push(`${c.group}「${c.key}」：TOP 占比 ${c.top_pct}% vs 尾部 ${c.bot_pct}%（p_adj=${c.p_adj}）`));

  const caveats = [];
  if (tooSmall) caveats.push(`样本仅 ${n} 条，未做任何统计检验。以下全是描述性观察，不能作为决策依据。`);
  else caveats.push(`样本 ${n} 条，TOP/尾部各 ${k} 条。k=${k} 时检验功效很低：真实存在但被判为噪声的因子会很多（假阴性）。`);
  caveats.push(`共做了 ${tests.length} 次检验，判定一律用 BH 校正后的 p_adj（FDR）。原始 p 值只展示不判定 —— 检验这么多次，即使全是噪声也会有约 ${Math.round((1 - Math.pow(0.95, tests.length)) * 100)}% 的概率至少出现一个 p<0.05。`);
  if (confounded) {
    caveats.push(`⚠️ 混杂变量警告：「内容年龄」差异显著（TOP ${ageRow.top} 天 vs 尾部 ${ageRow.bottom} 天，p_adj=${ageRow.p_adj}）。TOP 组更老 = 有更长时间累积点赞，这会污染其他所有因子的结论 —— 它们可能只是"发得更早"的副产物。`);
  }
  caveats.push('分组依据是点赞数，所以任何「以点赞为分母」的比率都有系统性偏差：高赞作品的比率会被天然压低。互动指标请先看绝对值那一列。');
  caveats.push('本脚本只检验相关性，不检验因果。p 显著只说明"它和爆款同时出现"。选题本身才是主因，图片数/标题长度这类结构化特征很可能只是伴随现象。');
  if (n < 20) caveats.push(`样本区间有限（未登录态通常只能拿到最近 15-20 条），"尾部组"可能不是真正的尾部，而是"最近几条还没起来的新内容"。`);

  console.log('\n──── 通过校正门槛的因子 ────');
  if (findings.length) findings.forEach((f, i) => console.log(`  ${i + 1}. ${f}`));
  else console.log('  无 —— 没有因子同时通过「p_adj<0.05」与「|d|≥0.5」。这不代表没有规律，更可能是样本量不够。');

  console.log('\n──── 局限性（必读）────');
  caveats.forEach((c) => console.log(`  ⚠️ ${c}`));

  // ── 落盘 ──
  const out = {
    generated_at: new Date().toISOString(),
    meta: {
      platform, account: acct, sample_size: n, top_k: k, perm_iterations: B,
      too_small: tooSmall, n_tests: tests.length, correction: 'Benjamini-Hochberg (FDR)',
      top_ids: topG.map((i) => feats[i].id), bottom_ids: botG.map((i) => feats[i].id),
    },
    numeric_factors: numRows, interaction: interRows, categorical: catRows,
    findings, caveats,
  };
  if (args.out) fs.writeFileSync(args.out, JSON.stringify(out, null, 2), 'utf8');

  if (args.md) {
    const L = [`# 爆款因子分析 · ${acct || '(未命名)'} · ${platform}`, '',
      `样本 n=${n}｜TOP ${k} vs 尾部 ${k}｜置换检验 ${B} 次｜BH 校正 ${tests.length} 项`, '',
      '## 数值因子', '', "| 因子 | TOP组 | 尾部组 | 差值 | Cohen's d | p | p_adj | 判定 |", '|---|---|---|---|---|---|---|---|'];
    for (const r of numRows) {
      if (r.skipped) { L.push(`| ${r.label} | — | — | — | — | — | — | ${r.skipped} |`); continue; }
      L.push(`| ${r.label} | ${r.top}${r.unit} | ${r.bottom}${r.unit} | ${r.diff} | ${fmtV(r.d)} | ${fmtV(r.p)} | ${fmtV(r.p_adj)} | ${VMARK[r.verdict]} |`);
    }
    L.push('', '## 互动结构（绝对值优先）', '', '| 指标 | TOP均 | 尾部均 | 差值 | p | p_adj | 判定 |', '|---|---|---|---|---|---|---|');
    for (const r of interRows) {
      if (r.skipped) { L.push(`| ${r.label} | — | — | — | — | — | ${r.skipped} |`); continue; }
      L.push(`| ${r.label} | ${r.top_abs} | ${r.bot_abs} | ${r.diff} | ${fmtV(r.p)} | ${fmtV(r.p_adj)} | ${VMARK[r.verdict]} |`);
    }
    L.push('', '## 分类因子', '');
    for (const r of catRows) {
      if (r.skipped) { L.push(`**${r.label}**：${r.skipped}`); continue; }
      L.push(`**${r.label}**`, '', '| 取值 | TOP | 尾部 | p | p_adj | 判定 |', '|---|---|---|---|---|---|');
      r.items.forEach((it) => L.push(`| ${it.key} | ${it.top_pct}%(${it.top_n}) | ${it.bot_pct}%(${it.bot_n}) | ${fmtV(it.p)} | ${fmtV(it.p_adj)} | ${VMARK[it.verdict] || '—'} |`));
      L.push('');
    }
    L.push('## 结论', '');
    if (findings.length) findings.forEach((f) => L.push(`- ${f}`));
    else L.push('- 无因子通过校正门槛。');
    L.push('', '## 局限性', '');
    caveats.forEach((c) => L.push(`- ${c}`));
    fs.writeFileSync(args.md, L.join('\n'), 'utf8');
  }

  console.log(`\n✅ ${args.out ? 'JSON: ' + args.out : ''}${args.md ? ' | Markdown: ' + args.md : ''}`);
})().catch((e) => { console.error('ERR', e.stack); process.exit(1); });
