/**
 * 趋势追踪 —— 读一个目录下的历史快照，输出账号的时间变化。
 *
 * 用法:
 *   node trend.js --dir snapshots/ [--name 账号名] [--md trend.md]
 *
 * ── 三个刻意的设计（都是为了让趋势不骗人）────────────────────────
 *
 * 1. 【同批作品对比】两次快照之间，「样本总赞」的增加很可能只是"又发了几条新的"。
 *    所以总赞增长之外，必须单独算**交集作品**（两次都存在的那些 id）的赞增量 ——
 *    那才是"老内容还在不在涨"。这俩数字经常差很远。
 *
 * 2. 【抓取窗口污染】抖音未登录态只能拿到最近 ~18 条。如果第二次抓的作品数变了、
 *    或者最早的 id 从窗口里滑出去了，总量指标就不可比。
 *    检测到作品集发生增删时会明确警告，不把窗口变化说成内容变化。
 *
 * 3. 【只有 1 份快照就直说】没有历史数据时不假装有趋势。
 *    这是最容易被忽略也最容易造假的地方。
 */
const fs = require('fs');
const path = require('path');
const { compute } = require('./core');

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

const vw = (s) => [...String(s)].reduce((acc, c) => acc + (/[\u3000-\u9fff\uff00-\uffef]/.test(c) ? 2 : 1), 0);
const pad = (s, n) => String(s) + ' '.repeat(Math.max(0, n - vw(s)));
const padL = (s, n) => ' '.repeat(Math.max(0, n - vw(s))) + String(s);

function loadSnapshots(dir, nameFilter) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => {
      try { return { file: f, data: JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')) }; }
      catch (e) { return null; }
    })
    .filter(Boolean)
    .filter((s) => !nameFilter || (s.data.account && s.data.account.name || '').includes(nameFilter))
    .sort((a, b) => String(a.data.captured_at || '').localeCompare(String(b.data.captured_at || '')));
}

const diggOf = (posts) => posts.reduce((a, p) => a + (p.digg || 0), 0);
const byId = (posts) => new Map(posts.map((p) => [p.id, p]));

function delta(cur, prev) {
  if (prev === 0) return cur > 0 ? '新增' : '0';
  const d = cur - prev;
  const r = (d / prev) * 100;
  return `${d >= 0 ? '+' : ''}${d} (${d >= 0 ? '+' : ''}${r.toFixed(1)}%)`;
}

(async () => {
  const args = parseArgs();
  const dir = args.dir || 'snapshots';
  const snaps = loadSnapshots(dir, args.name);

  if (!snaps.length) {
    console.error(`目录里没有快照: ${dir}`);
    console.error('先用 snapshot.js 存档：node snapshot.js --posts workdir/posts.json --dir ' + dir);
    process.exit(1);
  }

  // 同一天多次抓取不算趋势点 —— 一天内的波动是噪声，不是趋势。
  // 同一日期只保留该日最后一份（captured_at 最大的那份）。
  const byDate = new Map();
  snaps.forEach((s) => {
    const d = s.data.snapshot_date || 'unknown';
    const prev = byDate.get(d);
    if (!prev || String(s.data.captured_at || '') > String(prev.data.captured_at || '')) byDate.set(d, s);
  });
  const list = [...byDate.values()].sort((a, b) => String(a.data.captured_at).localeCompare(String(b.data.captured_at)));
  const dup = snaps.length - list.length;

  const name = (list[0].data.account && list[0].data.account.name) || '(未命名)';
  const platform = list[0].data.platform;

  console.log(`\n═══ 趋势追踪 · ${name} · ${platform} ═══`);
  console.log(`快照 ${list.length} 份（日期去重后） | ${list[0].data.snapshot_date} ~ ${list[list.length - 1].data.snapshot_date}`);
  if (dup > 0) console.log(`   （同日重复抓取 ${dup} 份已合并，一天内的差异是噪声不是趋势）`);

  if (list.length === 1) {
    console.log('\n⚠️ 只有 1 份快照，无法计算任何趋势。');
    console.log('   趋势需要至少两次抓取。建议：');
    console.log('   1) 过几天重新抓一次该账号');
    console.log('   2) node normalize.js --platform ... --raw ... --out ...');
    console.log('   3) node snapshot.js --posts ... --dir ' + dir);
    console.log('   4) 再运行本脚本');
    console.log('\n   想自动化？用定时任务每天/每周跑一次抓取+快照即可。');
    process.exit(0);
  }

  // ── 时间线 ──
  console.log('\n──── 时间线 ────');
  console.log(`  ${pad('日期', 12)}${padL('粉丝', 8)}${padL('作品', 8)}${padL('样本总赞', 10)}${padL('千粉均赞', 10)}`);
  console.log('  ' + '─'.repeat(50));
  list.forEach((s) => {
    const d = s.data;
    const total = diggOf(d.posts);
    const fans = (d.account && d.account.fans) || 0;
    const per1k = fans > 0 ? Math.round((total / fans) * 1000) : 0;
    console.log(`  ${pad(d.snapshot_date, 12)}${padL(fans, 8)}${padL(d.post_count, 8)}${padL(total, 10)}${padL(per1k, 10)}`);
  });

  // ── 首末对比 ──
  const first = list[0].data;
  const last = list[list.length - 1].data;
  const days = Math.max(1, Math.round((new Date(last.captured_at) - new Date(first.captured_at)) / 86400000));

  console.log('\n──── 整体变化 ────');
  const f0 = (first.account && first.account.fans) || 0;
  const f1 = (last.account && last.account.fans) || 0;
  const t0 = diggOf(first.posts);
  const t1 = diggOf(last.posts);
  console.log(`  跨度 ${days} 天`);
  console.log(`  粉丝     ${padL(f0, 8)} → ${padL(f1, 8)}   ${delta(f1, f0)}   日均 ${f0 > 0 || f1 > 0 ? ((f1 - f0) / days).toFixed(1) : '—'}`);
  console.log(`  样本总赞 ${padL(t0, 8)} → ${padL(t1, 8)}   ${delta(t1, t0)}`);
  const p0 = f0 > 0 ? Math.round((t0 / f0) * 1000) : 0;
  const p1 = f1 > 0 ? Math.round((t1 / f1) * 1000) : 0;
  console.log(`  千粉均赞 ${padL(p0, 8)} → ${padL(p1, 8)}   ${delta(p1, p0)}   （剔除粉丝规模影响）`);

  // ── 同批作品（核心：排除新发作品的干扰）──
  const m0 = byId(first.posts);
  const m1 = byId(last.posts);
  const common = [...m0.keys()].filter((id) => m1.has(id));
  const added = [...m1.keys()].filter((id) => !m0.has(id));
  const gone = [...m0.keys()].filter((id) => !m1.has(id));

  console.log('\n──── 同批作品增长（排除新发作品）────');
  if (!common.length) {
    console.log('  两次快照没有重叠作品，无法对比。可能是账号清空或换号。');
  } else {
    const c0 = common.reduce((a, id) => a + (m0.get(id).digg || 0), 0);
    const c1 = common.reduce((a, id) => a + (m1.get(id).digg || 0), 0);
    console.log(`  追踪 ${common.length} 条在两次快照中都存在的作品`);
    console.log(`  赞合计  ${c0} → ${c1}   ${delta(c1, c0)}`);
    if (c1 === c0) {
      console.log('  ⚠️ 老内容零增长 —— 说明作品发完就停止流通，没有长尾。');
    } else if (c1 > c0) {
      console.log(`  ✅ 老内容仍在累积（+${c1 - c0}），有长尾效应。`);
    } else {
      console.log('  ⚠️ 老内容赞数下降，可能是删稿/限流/统计口径变化。');
    }
    // 增长最快的内容
    const growth = common
      .map((id) => ({ id, d: (m1.get(id).digg || 0) - (m0.get(id).digg || 0), t: (m0.get(id).title || '').slice(0, 30), c: m1.get(id).digg }))
      .sort((a, b) => b.d - a.d)
      .slice(0, 5);
    console.log('\n  增长最快的内容:');
    growth.forEach((g) => console.log(`    ${g.d >= 0 ? '+' : ''}${g.d}  现${g.c}赞  ${g.t || '(无标题)'}`));
  }

  if (added.length) console.log(`\n  期间新增作品: ${added.length} 条`);
  if (gone.length) console.log(`  ⚠️ 期间消失作品: ${gone.length} 条（删稿/设为私密/滑出抓取窗口）`);

  // ── 诚实警告 ──
  const warns = [];
  if (gone.length) warns.push(`有 ${gone.length} 条作品从快照里消失，样本总赞的变化可能受此影响，不完全是内容表现。`);
  if (added.length && added.length > common.length) warns.push(`新增 ${added.length} 条 > 保留 ${common.length} 条，样本已大幅换血，总量指标基本不可比。`);
  if (last.post_count >= 18 && platform === 'douyin') warns.push('作品数已达抖音未登录态的经验上限（~18 条），样本可能被截断，不代表账号全部内容。');
  const dSpan = Math.abs(last.post_count - first.post_count);
  if (dSpan > 0 && dSpan > common.length * 0.5) warns.push(`两次快照作品数相差 ${dSpan} 条，样本窗口变化较大，比较时请留意。`);
  if (days < 3) warns.push(`两次快照仅隔 ${days} 天，短期波动大，不足以判断趋势方向。`);

  if (warns.length) {
    console.log('\n──── 读这份趋势前请注意 ────');
    warns.forEach((w, i) => console.log(`  ${i + 1}. ${w}`));
  }

  // ── 情景外推（不是预测）──
  if (f1 > f0 && days >= 7) {
    const perDay = (f1 - f0) / days;
    console.log('\n──── 按当前速度外推（算术外推，不是预测）────');
    [1000, 5000, 10000].forEach((target) => {
      if (f1 < target) {
        const need = Math.round((target - f1) / perDay);
        console.log(`  ${f1} → ${target} 粉：约 ${need} 天（${(need / 30).toFixed(1)} 个月）`);
      }
    });
    console.log('  ⚠️ 假设涨粉速度恒定。实际上账号增长通常是前期慢、爆发期快、之后放缓，');
    console.log('     外推只适合看数量级，不要当成承诺。');
  }

  const out = { snapshots: list.length, deduped: dup, first_date: first.snapshot_date, last_date: last.snapshot_date, days, warns };
  if (args.md) {
    fs.writeFileSync(args.md, `# ${name} 趋势追踪\n\n${JSON.stringify(out, null, 2)}\n`, 'utf8');
    console.log(`\n✅ 已写入 ${args.md}`);
  }
  process.exit(0);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
