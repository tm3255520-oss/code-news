/**
 * L3 多账号横向对比 —— 拆解最核心的用途：把「我的号 vs 对标号」的差异量化出来。
 *
 * 用法:
 *   node compare.js \
 *     --set "我的号=dy_me/posts.json" \
 *     --set "对标号=dy_target/posts.json" \
 *     [--out cmp.json] [--md cmp.md]
 *
 * 输出：控制台表格 + JSON（可选 markdown）。
 *
 * ── 设计上刻意做的四件事（每一条都是被真实数据打过脸之后加的）──────────
 *
 * 1. 【量级归一化】一个 111 粉和一个 4.7 万粉的账号，直接比「平均点赞」毫无意义。
 *    所以额外给 `千粉均赞`（mean_digg ÷ 粉丝 × 1000），把所有账号拉到同一量级再比。
 *    粉丝量级差 > 3 倍时明确警告：**绝对数字不可比，只看相对结构**。
 *
 * 2. 【缺失字段不参与比较】小红书列表接口拿不到评论/收藏/分享。
 *    某个账号上为 null 时整个指标跳过，**绝不能把 null 当 0 去比** ——
 *    那会得出「小红书账号互动极差」的假结论。
 *
 * 3. 【比率可靠性门禁】总赞 < 1000 的账号，其百分比指标强制降级、不得进入「强差异」。
 *    真实案例：某 58 粉账号 18 条共 274 赞，因 2 条「评论数>赞数」算出评论率 34.31%，
 *    看起来像强互动账号，实际只是分母太小。**这种假差异不能进结论。**
 *
 * 4. 【区分"账号行为"与"抓取窗口"】样本跨度、日更频率这类指标，
 *    差异可能来自"我们只抓到最近 18 条"而不是"对方真的更懒"。
 *    样本跨度**只作元信息不进差异排名**；日更频率在样本可能被截断时标注截断风险。
 */
const fs = require('fs');
const path = require('path');
const { compute, loadPosts, postFeatures, mean, round1, round2 } = require('./core');

function parseArgs() {
  const a = { _sets: [] };
  for (let i = 2; i < process.argv.length; i++) {
    const k = process.argv[i].replace(/^--/, '');
    if (k === 'set') a._sets.push(process.argv[i + 1]);
    else a[k] = process.argv[i + 1];
  }
  return a;
}

function parseSet(s) {
  const i = s.indexOf('=');
  if (i < 0) return { label: path.basename(s).replace(/\.json$/, ''), path: s };
  return { label: s.slice(0, i).trim(), path: s.slice(i + 1).trim() };
}

/** 未登录态列表接口的经验上限：抖音 ~18、B站 ~20。达到即"可能没抓全" */
const TRUNC_RISK_N = { douyin: 15, bilibili: 15, xiaohongshu: 30, instagram: 30 };

function buildEntry(set) {
  const data = loadPosts(set.path);
  const m = compute(data);
  const feats = data.posts.map(postFeatures);
  const fans = m.account.fans || 0;
  const n = m.meta.sample_size;

  return {
    label: set.label,
    path: set.path,
    platform: data.platform,
    n,
    // ⚠️ 账号名在原 data.account 上；m.account 是"健康度"对象（fans/total_likes/fan_like_ratio），没有 name
    name: (data.account && data.account.name) || '',
    fans,
    total_likes: m.account.total_likes,
    fan_like_ratio: m.account.fan_like_ratio,
    mean_digg: m.distribution.mean_digg,
    median_digg: m.distribution.median_digg,
    max_digg: m.distribution.max_digg,
    digg_per_1k_fans: fans > 0 ? round1((m.distribution.mean_digg / fans) * 1000) : null,
    mean_median_ratio: m.distribution.mean_median_ratio,
    top_share_pct: m.distribution.top_share_pct,
    top1_share_pct: m.scale.top1_share_pct,
    span_days: m.cadence.span_days,
    posts_per_day: m.cadence.posts_per_day,
    first: m.cadence.first,
    last: m.cadence.last,
    share_ratio: m.interaction.share_ratio,
    comment_ratio: m.interaction.comment_ratio,
    collect_ratio: m.interaction.collect_ratio,
    type_distribution: m.format.type_distribution,
    avg_media_count: m.format.avg_media_count,
    avg_title_len: round1(mean(feats.map((f) => f.title_len))),
    avg_tag_count: round1(mean(feats.map((f) => f.tag_count))),
    dominant_type: Object.entries(m.format.type_distribution)
      .sort((a, b) => b[1] - a[1])
      .map(([t, c]) => `${t} ${Math.round((c / n) * 100)}%`)[0] || '-',
    // 可靠性标记
    ratio_unreliable: !!m.scale.ratio_unreliable,
    total_digg: m.scale.total_digg,
    // 样本是否可能没抓全。两条独立信号，命中任一即标风险：
    //   a) 达到该平台列表接口的经验上限（抖音 ~18、B站 ~20）
    //   b) 跨度很长但条数很少 —— 实测案例：小红书 29 条覆盖 1483 天，
    //      按这个频率四年只发 29 条不合常理，实际是列表接口只给了最近的 29 条
    truncation_risk: n >= (TRUNC_RISK_N[data.platform] || 15)
      || (m.cadence.span_days > 120 && n < 40),
    truncation_reason: n >= (TRUNC_RISK_N[data.platform] || 15)
      ? `抓到 ${n} 条，已达该平台列表接口经验上限`
      : (m.cadence.span_days > 120 && n < 40
        ? `${m.cadence.span_days} 天跨度里只有 ${n} 条，不合常理，很可能是列表接口只给了最近的一批`
        : ''),
    low_confidence: m.meta.low_confidence,
    _unavailable: data._unavailable || [],
    _metrics: m,
  };
}

// ── 指标定义 ────────────────────────────────────────────
// kind='ratio'  用 max/min 倍数（计数类）
// kind='pp'     用 max-min 百分点（占比类）
// info_only     只作元信息，不参与差异排名（样本跨度属于此类）
// sensitive     受样本截断影响，结论必须带截断提示
const METRICS = [
  { g: '体量', k: 'fans', label: '粉丝', unit: '', kind: 'ratio' },
  { g: '体量', k: 'total_likes', label: '主页总赞', unit: '', kind: 'ratio', crossVolatile: true },
  { g: '体量', k: 'mean_digg', label: '平均赞', unit: '', kind: 'ratio', crossVolatile: true },
  { g: '体量', k: 'median_digg', label: '中位赞', unit: '', kind: 'ratio', crossVolatile: true },
  { g: '体量', k: 'max_digg', label: '峰值赞', unit: '', kind: 'ratio', crossVolatile: true },
  { g: '体量', k: 'digg_per_1k_fans', label: '千粉均赞⚖️', unit: '', kind: 'ratio', note: '量级归一化后的内容效率，跨体量对比时看这个', crossVolatile: true },
  { g: '体量', k: 'fan_like_ratio', label: '总赞÷粉丝', unit: '', kind: 'ratio', note: '越高说明"内容爆但粉丝沉淀弱"（泛流量）' },

  { g: '集中度', k: 'mean_median_ratio', label: '均值÷中位', unit: '', kind: 'ratio', note: '>2 表示高度依赖头部爆款，日常内容很平' },
  { g: '集中度', k: 'top_share_pct', label: '头部占比', unit: '%', kind: 'pp' },
  { g: '集中度', k: 'top1_share_pct', label: '单条最高占比', unit: '%', kind: 'pp' },

  { g: '节奏', k: 'posts_per_day', label: '日更频率', unit: '条/天', kind: 'ratio', sensitive: true },
  { g: '节奏', k: 'span_days', label: '样本跨度', unit: '天', kind: 'ratio', info_only: true, note: '抓取窗口，不是账号行为差异' },

  { g: '形态', k: 'avg_media_count', label: '平均图片数', unit: '张', kind: 'ratio' },
  { g: '形态', k: 'avg_title_len', label: '标题长度', unit: '字', kind: 'ratio' },
  { g: '形态', k: 'avg_tag_count', label: '话题数', unit: '个', kind: 'ratio' },

  { g: '互动结构', k: 'share_ratio', label: '分享/赞', unit: '%', kind: 'pp', note: '>15% 说明有转发动机，是裂变型内容' },
  { g: '互动结构', k: 'comment_ratio', label: '评论/赞', unit: '%', kind: 'pp', note: '<2% 说明看完就走，没引发讨论' },
  { g: '互动结构', k: 'collect_ratio', label: '收藏/赞', unit: '%', kind: 'pp', note: '高 = 工具/资料属性强' },
];

const RANK = { weak: 0, medium: 1, strong: 2 };

function grade(kind, a, b) {
  if (kind === 'pp') {
    const d = Math.abs(a - b);
    if (d >= 10) return { level: 'strong', d: round1(d) };
    if (d >= 4) return { level: 'medium', d: round1(d) };
    return { level: 'weak', d: round1(d) };
  }
  const lo = Math.min(a, b), hi = Math.max(a, b);
  if (lo <= 0) return { level: 'weak', d: null };
  const r = hi / lo;
  if (r >= 2) return { level: 'strong', d: round2(r) };
  if (r >= 1.4) return { level: 'medium', d: round2(r) };
  return { level: 'weak', d: round2(r) };
}

const fmtV = (v) => (v === null || v === undefined ? 'N/A' : String(v));

function analyze(entries) {
  const rows = [];
  const skipped = [];
  const minN = Math.min(...entries.map((e) => e.n));
  const sampleLimited = minN < 15;
  const crossPlatform = new Set(entries.map((e) => e.platform)).size > 1;

  for (const def of METRICS) {
    const vals = entries.map((e) => (e[def.k] === undefined ? null : e[def.k]));
    if (vals.some((v) => v === null || v === undefined || Number.isNaN(v))) {
      const who = entries.filter((e, i) => vals[i] === null || vals[i] === undefined).map((e) => e.label);
      skipped.push({ metric: def.label, reason: `数据不可得：${who.join('、')}（接口不提供，未做估算）` });
      continue;
    }

    let best = { level: 'weak', d: null };
    for (let i = 0; i < vals.length; i++)
      for (let j = i + 1; j < vals.length; j++) {
        const gg = grade(def.kind, vals[i], vals[j]);
        if (RANK[gg.level] > RANK[best.level] || (gg.level === best.level && (gg.d || 0) > (best.d || 0))) {
          best = { ...gg, i, j };
        }
      }

    const maxIdx = vals.indexOf(Math.max(...vals));
    const minIdx = vals.indexOf(Math.min(...vals));
    const hi = entries[best.i != null ? (vals[best.i] >= vals[best.j] ? best.i : best.j) : maxIdx];
    const lo = entries[best.i != null ? (vals[best.i] >= vals[best.j] ? best.j : best.i) : minIdx];

    const notes = [];
    let level = best.level;

    // ── 可靠性门禁：把假差异挡在"强差异"之外 ──
    if (def.kind === 'pp' && entries.some((e) => e.ratio_unreliable)) {
      const who = entries.filter((e) => e.ratio_unreliable).map((e) => `${e.label}(总赞${e.total_digg})`);
      notes.push(`⚠️ ${who.join('、')} 绝对量过小，比率失真，此差异不可作决策依据`);
      level = 'weak';
    }
    if (!def.info_only && sampleLimited && level !== 'weak') notes.push(`⚠️ 最小样本仅 n=${minN}`);
    // 样本被截断时日更频率不可比：18条/214天 和 5条/2天 根本不是同一个东西
    if (def.sensitive && entries.some((e) => e.truncation_risk)) {
      // 注意：这里取的是 entry 数组（要读 truncation_reason），不是 label 数组
      const why = entries.filter((e) => e.truncation_risk).map((e) => `${e.label} ${e.truncation_reason}`).filter(Boolean);
      notes.push(`⚠️ ${why.join('；')} —— 实际频率应更高，此项不可用作结论`);
      level = 'weak';
    }
    if (crossPlatform && def.crossVolatile && level !== 'weak') {
      notes.push('⚠️ 跨平台，赞的含金量不同，绝对量仅供参考');
      if (level === 'strong') level = 'medium';
    }

    rows.push({
      group: def.g, metric: def.label, unit: def.unit,
      values: vals.map((v, i) => ({ label: entries[i].label, v })),
      diff: best.d, diff_kind: def.kind,
      level, raw_level: best.level,
      info_only: !!def.info_only,
      high: hi.label, low: lo.label,
      note: def.note || '',
      flags: notes,
    });
  }
  return { rows, skipped, minN, sampleLimited, crossPlatform };
}

function toFindings(rows, minN) {
  const strong = [], medium = [];
  for (const r of rows) {
    if (r.info_only || r.level === 'weak') continue;
    const vals = r.values.map((v) => `${v.label} ${fmtV(v.v)}${r.unit}`).join(' / ');
    const head = r.diff === null
      ? `${r.metric}：${vals} —— 一方为 0，倍数无意义（0 不能做分母）`
      : r.diff_kind === 'pp'
        ? `${r.metric}：${vals} —— 差 ${r.diff} 个百分点，${r.high} 更高`
        : `${r.metric}：${vals} —— ${r.high} 是 ${r.low} 的 ${r.diff} 倍`;
    const flags = r.flags.length ? `（${r.flags.join('；')}）` : `（n≥${minN}）`;
    (r.level === 'strong' ? strong : medium).push({ metric: r.metric, diff: r.diff, text: `${head}${flags}` });
  }
  strong.sort((a, b) => b.diff - a.diff);
  medium.sort((a, b) => b.diff - a.diff);
  return { strong, medium };
}

function buildCaveats(entries, crossPlatform) {
  const c = [];
  if (crossPlatform) {
    const ps = [...new Set(entries.map((e) => e.platform))];
    c.push(`跨平台对比（${ps.join(' / ')}）：赞的含金量不同、推荐机制不同，绝对量不可比。只能比结构（集中度、形态、节奏），不能比数字。`);
  }
  const fansArr = entries.map((e) => e.fans).filter((x) => x > 0);
  if (fansArr.length > 1) {
    const r = Math.max(...fansArr) / Math.min(...fansArr);
    if (r >= 3) {
      c.push(`粉丝量级差 ${round1(r)} 倍（${entries.map((e) => `${e.label} ${e.fans}`).join(' / ')}）：绝对点赞数不可直接比，请只看「千粉均赞」等归一化指标。`);
    }
  }
  for (const e of entries) {
    if (e.n < 15) c.push(`${e.label} 仅 ${e.n} 条样本 —— 它的所有百分比指标都是定性参考，不构成强结论。`);
    if (e.truncation_risk) c.push(`${e.label} ${e.truncation_reason}，可能只是"最近的作品"而非全部，日更频率被低估。`);
    if (e._unavailable.length) c.push(`${e.label}（${e.platform}）列表接口不提供 ${e._unavailable.join('/')}，相关维度已整列跳过，未以 0 参与比较。`);
    if (e.ratio_unreliable) c.push(`${e.label} 样本总赞仅 ${e.total_digg}（均值 ${e._metrics.scale.avg_digg}），绝对量过小，其比率类指标已全部强制降级，不进入强差异。`);
  }
  c.push('本次对比只反映已抓取样本区间的表现，不含更早历史内容。样本可能是"最近的运气"而非长期水平。');
  c.push('本脚本只给相关性，不给因果。差异存在 ≠ 复制该特征就能得到同样结果。');
  return c;
}

// ── 输出 ────────────────────────────────────────────────
function toMarkdown(entries, rows, findings, caveats, skipped, minN) {
  const L = [];
  L.push(`# 账号横向对比 · ${entries.map((e) => e.label).join(' vs ')}`);
  L.push('');
  L.push(`生成时间：${new Date().toISOString().slice(0, 19).replace('T', ' ')}　|　最小样本 n=${minN}`);
  L.push('');
  L.push('## 1. 账号概览');
  L.push('');
  L.push('| | ' + entries.map((e) => e.label).join(' | ') + ' |');
  L.push('|---|' + entries.map(() => '---|').join(''));
  const overview = [
    ['账号名', (e) => e.name || '-'],
    ['平台', (e) => e.platform],
    ['样本数', (e) => e.n],
    ['粉丝', (e) => e.fans],
    ['主页总赞', (e) => e.total_likes],
    ['样本总赞', (e) => e.total_digg],
    ['主形态', (e) => e.dominant_type],
    ['样本区间', (e) => `${e.first} ~ ${e.last}`],
  ];
  for (const [label, fn] of overview) L.push(`| ${label} | ` + entries.map((e) => fmtV(fn(e))).join(' | ') + ' |');

  L.push('');
  L.push('## 2. 维度对比');
  L.push('');
  let g = '';
  for (const r of rows) {
    if (r.group !== g) {
      g = r.group;
      L.push(`### ${g}`);
      L.push('');
      L.push('| 指标 | ' + entries.map((e) => e.label).join(' | ') + ' | 差异 | 强度 | 备注 |');
      L.push('|---|' + entries.map(() => '---|').join('') + '---|---|---|');
    }
    const mark = r.info_only ? '— 元信息'
      : r.level === 'strong' ? '🔴 强'
      : r.level === 'medium' ? '🟡 中' : '⚪ 弱（不可用作结论）';
    const dv = r.diff === null ? '-' : r.diff_kind === 'pp' ? `${r.diff}pp` : `${r.diff}×`;
    const note = [r.note, ...r.flags].filter(Boolean).join(' ');
    L.push(`| ${r.metric} | ` + r.values.map((v) => fmtV(v.v)).join(' | ') + ` | ${dv} | ${mark} | ${note} |`);
  }

  L.push('');
  L.push('## 3. 关键差异');
  L.push('');
  L.push('### 强差异（优先关注）');
  if (findings.strong.length) findings.strong.forEach((f, i) => L.push(`${i + 1}. ${f.text}`));
  else L.push('无。当前数据下没有通过可靠性门禁的强差异（可能是量级过小或样本不足导致比率不可信）。');
  L.push('');
  L.push('### 中等差异 / 待验证');
  if (findings.medium.length) findings.medium.forEach((f, i) => L.push(`${i + 1}. ${f.text}`));
  else L.push('无。');

  L.push('');
  L.push('## 4. 局限性（必读）');
  L.push('');
  caveats.forEach((c) => L.push(`- ${c}`));
  if (skipped.length) {
    L.push('');
    L.push('### 跳过的维度');
    skipped.forEach((s) => L.push(`- ${s.metric}：${s.reason}`));
  }
  return L.join('\n');
}

(async () => {
  const args = parseArgs();
  if (!args._sets.length) {
    console.error('用法: node compare.js --set "标签A=pathA/posts.json" --set "标签B=pathB/posts.json" [--out cmp.json] [--md cmp.md]');
    process.exit(1);
  }
  const entries = args._sets.map(parseSet).map(buildEntry);
  const { rows, skipped, minN, sampleLimited, crossPlatform } = analyze(entries);
  const findings = toFindings(rows, minN);
  const caveats = buildCaveats(entries, crossPlatform);

  const dispW = (s) => [...String(s)].reduce((a, ch) => a + (ch.charCodeAt(0) > 255 ? 2 : 1), 0);
  const pad = (s, n) => { let x = String(s); let w = dispW(x); while (w < n) { x += ' '; w++; } return x; };
  const colW = Math.max(12, ...entries.map((e) => dispW(e.label))) + 2;

  console.log(`\n═══ 账号横向对比 · ${entries.map((e) => e.label).join(' vs ')} ═══`);
  console.log(`最小样本 n=${minN}${sampleLimited ? '  ⚠️ 样本不足' : ''}${crossPlatform ? '  ⚠️ 跨平台' : ''}`);

  console.log('\n──── 概览 ────');
  for (const e of entries) {
    console.log(`  【${e.label}】${e.name || '(未命名)'} · ${e.platform} · n=${e.n}${e.truncation_risk ? ' ⚠️样本可能被截断' : ''}`);
    console.log(`      粉丝 ${e.fans} | 主页总赞 ${e.total_likes} | 样本总赞 ${e.total_digg} | 主形态 ${e.dominant_type} | ${e.first} ~ ${e.last}`);
  }

  console.log('\n──── 维度对比 ────');
  let cur = '';
  for (const r of rows) {
    if (r.group !== cur) {
      cur = r.group;
      console.log(`\n  [${cur}]`);
      console.log('  ' + pad('指标', 18) + entries.map((e) => pad(e.label, colW)).join('') + pad('差异', 10) + '强度');
    }
    const mark = r.info_only ? '— 元信息'
      : r.level === 'strong' ? '🔴强'
      : r.level === 'medium' ? '🟡中' : '⚪弱';
    const dv = r.diff === null ? '-' : r.diff_kind === 'pp' ? `${r.diff}pp` : `${r.diff}x`;
    console.log('  ' + pad(r.metric, 18) + r.values.map((v) => pad(fmtV(v.v) + r.unit, colW)).join('') + pad(dv, 10) + mark);
    if (r.flags.length) console.log('      ' + r.flags.join('；'));
  }

  console.log('\n──── 关键差异 ────');
  console.log('  ▍强差异（已通过可靠性门禁）：');
  if (findings.strong.length) findings.strong.forEach((f, i) => console.log(`   ${i + 1}. ${f.text}`));
  else console.log('   无 —— 当前数据下没有可信的强差异。');
  console.log('  ▍中等差异 / 待验证：');
  if (findings.medium.length) findings.medium.forEach((f, i) => console.log(`   ${i + 1}. ${f.text}`));
  else console.log('   无。');

  console.log('\n──── 局限性（必读）────');
  caveats.forEach((c) => console.log(`  ⚠️ ${c}`));
  if (skipped.length) {
    console.log('  ▍跳过的维度：');
    skipped.forEach((s) => console.log(`   - ${s.metric}：${s.reason}`));
  }

  const outJson = {
    generated_at: new Date().toISOString(),
    entries: entries.map(({ _metrics, ...rest }) => rest),
    rows, skipped, findings, caveats,
    meta: { min_sample: minN, sample_limited: sampleLimited, cross_platform: crossPlatform },
  };
  if (args.out) fs.writeFileSync(args.out, JSON.stringify(outJson, null, 2), 'utf8');
  if (args.md) fs.writeFileSync(args.md, toMarkdown(entries, rows, findings, caveats, skipped, minN), 'utf8');
  console.log(`\n✅ ${args.out ? 'JSON: ' + args.out : ''}${args.md ? ' | Markdown: ' + args.md : ''}`);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
