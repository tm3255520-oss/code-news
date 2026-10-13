/**
 * 共享内核 —— 统计工具 + 统一指标计算 + 作品特征提取。
 *
 * 为什么要有这个文件：
 *   metrics.js（单账号）、compare.js（多账号对比）、virality.js（爆款因子）
 *   三个脚本必须共用**同一套口径**。如果各写一份，均值/中位/TopN 的定义会悄悄漂移，
 *   对比出来的"差异"就可能是口径差异而不是真实差异。这里就是唯一事实来源。
 *
 * 2026-09-05 从 metrics.js 抽出，计算逻辑逐行照搬，未改变任何输出。
 */
const fs = require('fs');

/** "4.7万" → 47000；"1.2亿" → 120000000；"3,405" → 3405 */
function parseCount(v) {
  if (v === null || v === undefined) return 0;
  if (typeof v === 'number') return v;
  const s = String(v).trim().replace(/,/g, '');
  const m = s.match(/^([\d.]+)\s*([万万亿wWkK]?)/);
  if (!m) return 0;
  const n = parseFloat(m[1]);
  const unit = m[2];
  if (unit === '万' || unit === 'w' || unit === 'W') return Math.round(n * 1e4);
  if (unit === '亿') return Math.round(n * 1e8);
  if (unit === 'k' || unit === 'K') return Math.round(n * 1e3);
  return Math.round(n);
}

const sum = (a) => a.reduce((x, y) => x + y, 0);
const mean = (a) => (a.length ? sum(a) / a.length : 0);
function median(a) {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
const pct = (x, y) => (y > 0 ? +((x / y) * 100).toFixed(2) : 0);
const round1 = (x) => Math.round(x * 10) / 10;
const round2 = (x) => Math.round(x * 100) / 100;

// ── 发布时刻提取 ────────────────────────────────────────
// 归一化层只保留到「日」（create_time: "2026-09-04"），**小时/星期在 raw 里**。
// 发布时段分析必须从 raw 里挖，各平台字段位置不同，这里集中处理。
const WD = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

function tsMsFromRaw(p) {
  const r = p.raw || {};
  const cands = [
    r.create_time, // 抖音：unix 秒
    r.noteCard && r.noteCard.time, // 小红书：毫秒
    r.time, // 兜底
    r.taken_at_timestamp, // INS
  ];
  for (const c of cands) {
    if (typeof c === 'number' && c > 0) return String(c).length > 10 ? c : c * 1000;
    if (typeof c === 'string' && /^\d{9,13}$/.test(c)) {
      const n = +c;
      return String(c).length > 10 ? n : n * 1000;
    }
  }
  return null;
}

/** 返回 {hour, weekday, weekday_cn}（北京时间 UTC+8），取不到返回 null */
function timeInfo(p) {
  const ms = tsMsFromRaw(p);
  if (!ms) return null;
  const d = new Date(ms + 8 * 3600 * 1000); // 北京时间
  return { hour: d.getUTCHours(), weekday: d.getUTCDay(), weekday_cn: WD[d.getUTCDay()] };
}

/** 单条作品的结构化特征 —— 对比与爆款因子分析都基于这个向量 */
function postFeatures(p) {
  const t = timeInfo(p);
  return {
    id: p.id,
    title: p.title || '',
    title_len: (p.title || '').length,
    tag_count: (p.tags || []).length,
    media_count: p.media_count || 1,
    media_type: p.media_type || 'unknown',
    hour: t ? t.hour : null,
    weekday_cn: t ? t.weekday_cn : null,
    date: p.create_time || '',
    digg: p.digg || 0,
    comment: p.comment,
    share: p.share,
    collect: p.collect,
  };
}

// ── 统一指标计算（从 metrics.js 逐行搬来，未改逻辑）──────
function compute(data) {
  const { platform, account, posts } = data;
  const n = posts.length;
  const lowConf = n < 20;

  const diggs = posts.map((p) => p.digg);
  const totalDigg = sum(diggs);

  const sorted = [...diggs].sort((a, b) => b - a);
  const topN = Math.max(1, Math.min(5, Math.floor(n * 0.2)));
  const topShare = pct(sum(sorted.slice(0, topN)), totalDigg);
  const top5Share = pct(sum(sorted.slice(0, 5)), totalDigg);

  const dates = posts.map((p) => p.create_time).filter(Boolean).sort();
  let spanDays = 0, perDay = 0;
  if (dates.length > 1) {
    spanDays = Math.max(1, Math.round((new Date(dates[dates.length - 1]) - new Date(dates[0])) / 86400000));
    perDay = +(n / spanDays).toFixed(2);
  }

  const unavailable = data._unavailable || [];
  const avail = (k) => !unavailable.includes(k);
  const agg = (k) => sum(posts.map((p) => (p[k] == null ? 0 : p[k])));

  const interaction = {
    digg_total: totalDigg,
    comment_total: avail('comment') ? agg('comment') : null,
    share_total: avail('share') ? agg('share') : null,
    collect_total: avail('collect') ? agg('collect') : null,
    danmaku_total: avail('danmaku') ? agg('danmaku') : null,
    share_ratio: avail('share') ? pct(agg('share'), totalDigg) : null,
    comment_ratio: avail('comment') ? pct(agg('comment'), totalDigg) : null,
    collect_ratio: avail('collect') ? pct(agg('collect'), totalDigg) : null,
    danmaku_ratio: avail('danmaku') ? pct(agg('danmaku'), totalDigg) : null,
  };
  if (unavailable.length) {
    interaction.unavailable_fields = unavailable;
    interaction.unavailable_note = '本平台列表接口不提供这些指标，需打开单条内容才能获取';
  }

  const scale = {
    total_digg: totalDigg,
    avg_digg: Math.round(mean(diggs)),
    ratio_unreliable: totalDigg < 1000,
  };
  if (scale.ratio_unreliable) {
    scale.warning = `总赞仅 ${totalDigg}（均值 ${scale.avg_digg}），绝对量太小，以下比率仅供观察，不可与正常量级账号横向对比`;
  }
  const top1 = sorted[0] || 0;
  scale.top1_share_pct = pct(top1, totalDigg);
  if (!scale.ratio_unreliable && scale.top1_share_pct > 40) {
    scale.concentration_warning = `单条最高赞作品贡献 ${scale.top1_share_pct}%，整体比率被个别内容主导`;
  }

  const playTotal = agg('play');
  if (playTotal > 0) {
    interaction.play_total = playTotal;
    interaction.like_play_ratio = pct(totalDigg, playTotal);
  } else {
    interaction.play_note = '本平台/形态不返回播放量（如图文作品），赞阅比不可计算';
  }

  const typeCount = {};
  posts.forEach((p) => { typeCount[p.media_type] = (typeCount[p.media_type] || 0) + 1; });
  const mediaCounts = posts.map((p) => p.media_count || 1);

  const tagStat = {};
  posts.forEach((p) => {
    (p.tags || []).forEach((t) => {
      if (!tagStat[t]) tagStat[t] = { count: 0, digg: 0 };
      tagStat[t].count++;
      tagStat[t].digg += p.digg;
    });
  });
  const topTags = Object.entries(tagStat)
    .map(([tag, v]) => ({ tag, count: v.count, avg_digg: Math.round(v.digg / v.count) }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 15);

  const topPosts = [...posts].sort((a, b) => b.digg - a.digg).slice(0, 5).map((p) => ({
    id: p.id, date: p.create_time, digg: p.digg, comment: p.comment,
    share: p.share, collect: p.collect, title: (p.title || '').slice(0, 60),
  }));

  const acct = {
    fans: account.fans || 0,
    total_likes: account.total_likes || 0,
    fan_like_ratio: account.fans > 0 ? +(account.total_likes / account.fans).toFixed(2) : null,
  };

  const m = {
    meta: { platform, account: account.name, generated_at: new Date().toISOString(), sample_size: n, low_confidence: lowConf },
    distribution: {
      mean_digg: Math.round(mean(diggs)),
      median_digg: Math.round(median(diggs)),
      max_digg: Math.max(...diggs, 0),
      min_digg: Math.min(...diggs, 0),
      mean_median_ratio: median(diggs) > 0 ? +(mean(diggs) / median(diggs)).toFixed(2) : null,
      top_share_pct: topShare,
      topN,
      top5_share_pct: top5Share,
    },
    scale,
    cadence: { span_days: spanDays, posts_per_day: perDay, first: dates[0] || '', last: dates[dates.length - 1] || '' },
    interaction,
    format: { type_distribution: typeCount, avg_media_count: +mean(mediaCounts).toFixed(1) },
    tags: topTags,
    top_posts: topPosts,
    account: acct,
  };

  if (lowConf) m.meta.warning = `样本仅 ${n} 条，百分比指标仅作定性参考，不足以支撑强结论`;
  return m;
}

/** 载入 posts.json（容错：文件路径 / 找不到给明确报错） */
function loadPosts(file) {
  if (!fs.existsSync(file)) throw new Error(`文件不存在: ${file}`);
  const j = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!j || !Array.isArray(j.posts)) throw new Error(`不是合法的 posts.json（缺 posts 数组）: ${file}`);
  return j;
}

module.exports = {
  parseCount, sum, mean, median, pct, round1, round2,
  timeInfo, postFeatures, compute, loadPosts,
};
