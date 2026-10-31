/**
 * L3 指标层 —— 平台无关。输入统一 schema 的 posts.json，输出 metrics.json。
 *
 * 设计原则：
 *  - 只算「用抓到的真实字段能算出来的」指标，缺字段就不算这个指标，不估算不脑补
 *  - 所有比率都带样本量 n，n<20 时明确标记 low_confidence
 *  - 同时给均值和中位数，均值被头部拉高时差值是关键信号
 *
 * ⚠️ 计算内核在 core.js，与 compare.js / virality.js 共用。
 *    要改口径就改 core.js，不要在任何一个脚本里另写一份，否则三个脚本的
 *    「均值」「TopN 占比」会悄悄漂移，对比出来的差异就是口径差异而非真实差异。
 *
 * 用法: node metrics.js --posts workdir/posts.json [--out workdir/metrics.json]
 */
const fs = require('fs');
const { compute } = require('./core');

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

const args = parseArgs();
const data = JSON.parse(fs.readFileSync(args.posts, 'utf8'));
const m = compute(data);
const outPath = args.out || 'metrics.json';
fs.writeFileSync(outPath, JSON.stringify(m, null, 2), 'utf8');

// 控制台摘要
const d = m.distribution, i = m.interaction;
console.log(`\n═══ ${m.meta.account || '(未命名)'} · ${m.meta.platform} ═══`);
console.log(`样本 ${m.meta.sample_size} 条${m.meta.low_confidence ? '  ⚠️ 低置信度' : ''} | 跨度 ${m.cadence.span_days} 天 | 日更 ${m.cadence.posts_per_day}`);
console.log(`粉丝 ${m.account.fans} | 总赞 ${m.account.total_likes} | 粉赞比 1:${m.account.fan_like_ratio}`);
console.log(`\n赞：均值 ${d.mean_digg} / 中位 ${d.median_digg} / 峰值 ${d.max_digg}`);
const headLine = `头部依赖：均值÷中位 = ${d.mean_median_ratio} | Top${d.topN} 贡献 ${d.top_share_pct}%`;
console.log(headLine + (d.topN !== 5 ? ` | Top5 贡献 ${d.top5_share_pct}%` : ''));
if (m.scale.ratio_unreliable) {
  console.log(`\n⚠️⚠️ 量级过小：${m.scale.warning}`);
  console.log(`   单条最高赞贡献 ${m.scale.top1_share_pct}% —— 下列比率不可用于横向对比`);
} else if (m.scale.concentration_warning) {
  console.log(`\n⚠️ ${m.scale.concentration_warning}`);
}
const fmt = (v) => (v === null || v === undefined ? 'N/A（接口不提供）' : v + '%');
console.log(`\n互动结构（占赞比）：`);
console.log(`  分享 ${fmt(i.share_ratio)}  |  评论 ${fmt(i.comment_ratio)}  |  收藏 ${fmt(i.collect_ratio)}${i.danmaku_ratio ? `  |  弹幕 ${i.danmaku_ratio}%` : ''}`);
if (i.unavailable_note) console.log(`  ⚠️ ${i.unavailable_note}：${i.unavailable_fields.join(', ')}`);
if (i.play_note) console.log(`  ⚠️ ${i.play_note}`);
console.log(`\n形态：${JSON.stringify(m.format.type_distribution)} | 平均 ${m.format.avg_media_count} 张/条`);
console.log(`\n✅ 已写入 ${outPath}`);
