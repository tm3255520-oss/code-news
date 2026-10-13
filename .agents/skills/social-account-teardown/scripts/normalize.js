/**
 * L2 归一化层 —— 把各平台原始 JSON 统一成一份 schema。
 * 换平台只在这里加一个分支，L3 指标层与报告层完全不用动。
 *
 * 用法:
 *   node normalize.js --platform douyin --raw workdir/douyin_raw.json \
 *                     [--profile workdir/douyin_profile.txt] --out workdir/posts.json
 *   node normalize.js --platform bilibili --raw workdir/bili_raw.json --out workdir/posts.json
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

const ts = (t) => (t ? new Date((String(t).length > 10 ? +t : +t * 1000)).toISOString().slice(0, 10) : '');

/** 从抖音正文里抽 #话题 */
function extractTags(desc) {
  const m = String(desc || '').match(/#([^\s#]+)/g);
  return m ? m.map((s) => s.slice(1)) : [];
}

// ── 抖音 ────────────────────────────────────────────────
function normalizeDouyin(raw, profileText) {
  const list = Array.isArray(raw) ? raw : raw.aweme_list || [];
  const account = { id: '', name: '', fans: 0, total_likes: 0, post_count: list.length, bio: '' };

  // 抖音主页 innerText 的排版是「标签\n数字」：
  //   ... 地球Online助手 / 关注 / 0 / 粉丝 / 4.7万 / 获赞 / 63.2万 ...
  // 注意顶部导航栏也有「关注」二字，所以一律以「粉丝」「获赞」为锚点，不要从头 findIndex。
  if (profileText) {
    const lines = profileText.split('\n').map((s) => s.trim()).filter(Boolean);
    const pick = (label) => {
      const i = lines.findIndex((l) => l === label);
      return i >= 0 ? parseCount(lines[i + 1] || '0') : 0;
    };
    account.fans = pick('粉丝');
    account.total_likes = pick('获赞');

    const fi = lines.findIndex((l) => l === '粉丝');
    if (fi > 0) {
      // 关注数：顺序是 [昵称, 关注, <关注数>, 粉丝, <粉丝数>, 获赞, <获赞数>]
      // 不能用 findIndex('关注') —— 顶部导航栏也有「关注」二字，会命中错误的那一个
      account.following = parseCount(lines[fi - 1] || '0');
      // 昵称在「粉丝」锚点之前，中间可能夹着「关注」和关注数
      // 昵称在「粉丝」锚点之前，中间可能夹着「关注」和关注数
      for (let i = fi - 1; i >= Math.max(0, fi - 4); i--) {
        const t = lines[i];
        if (t && t !== '关注' && !/^[\d.,万亿kKwW]+$/.test(t) && !/^(登录|关注|私信|分享主页|作品|推荐|喜欢|合集|短剧)$/.test(t)) {
          account.name = t;
          break;
        }
      }
    }
    // 抖音号：主页「抖音号：xxx」那一行
    const idLine = lines.find((l) => /^抖音号：/.test(l));
    if (idLine) account.id = idLine.replace('抖音号：', '').trim();

    // 简介：以「分享主页」为锚点向前回溯。
    // 结构：... 抖音号：xxx / IP属地：xx / <简介> / [更多] / 分享主页 / 关注 / 私信
    // ❌ 不要改用「长度 > 12 的长行」去找 —— 实测会命中页脚的「互联网新闻信息服务许可证 11220230001」
    const si = lines.findIndex((l) => l === '分享主页');
    if (si > 0) {
      const skip = /^(抖音号：|IP属地：|分享主页|关注|私信|作品|推荐|喜欢|合集|短剧|登录|更多|展开|收起)$/;
      for (let i = si - 1; i >= Math.max(0, si - 5); i--) {
        const t = lines[i];
        if (t && !skip.test(t) && !/^\d+$/.test(t) && !/^===/.test(t)) {
          account.bio = t.slice(0, 100);
          break;
        }
      }
    }
  }

  const posts = list.map((a) => {
    const st = a.statistics || {};
    const images = a.images || a.image_list || [];
    return {
      id: a.aweme_id,
      title: a.desc || '',
      create_time: ts(a.create_time),
      url: `https://www.douyin.com/video/${a.aweme_id}`,
      // 有 images 数组即为图文作品
      media_type: images.length ? 'image_album' : 'video',
      media_count: images.length || 1,
      // ⚠️ 抖音图文作品的 play_count 恒为 0，接口不返回播放量
      play: st.play_count || 0,
      digg: st.digg_count || 0,
      comment: st.comment_count || 0,
      share: st.share_count || 0,
      collect: st.collect_count || 0,
      danmaku: 0,
      tags: extractTags(a.desc),
      raw: a,
    };
  });

  return { platform: 'douyin', account, posts };
}

// ── B站 ────────────────────────────────────────────────
function normalizeBilibili(raw) {
  // raw: { card: {...}, vlist: [...], stats: { bvid: {...} } }
  const card = (raw.card && raw.card.card) || raw.card || {};
  const account = {
    id: String(card.mid || ''),
    name: card.name || '',
    fans: card.fans || 0,
    total_likes: 0, // B站不公开总获赞
    post_count: card.archive || (raw.vlist || []).length,
    bio: card.sign || '',
  };

  const stats = raw.stats || {};
  const posts = (raw.vlist || []).map((v) => {
    const s = stats[v.bvid] || {};
    return {
      id: v.bvid,
      title: v.title || '',
      create_time: ts(v.created),
      url: `https://www.bilibili.com/video/${v.bvid}`,
      media_type: 'video',
      media_count: 1,
      play: s.view != null ? s.view : (v.play || 0),
      digg: s.like != null ? s.like : 0,
      comment: s.reply != null ? s.reply : (v.comment || 0),
      share: s.share || 0,
      collect: s.favorite || 0,
      danmaku: s.danmaku || 0,
      tags: [],
      raw: v,
    };
  });

  return { platform: 'bilibili', account, posts };
}

// ── 小红书 ──────────────────────────────────────────────
// 实测结构（2026-09-04）：
//   notes 是分页数组，摊平后每项 = { id, noteCard:{ type, displayTitle, interactInfo,
//     cover, noteId, user, time, xsecToken }, index, exposed, ssrRendered, xsecToken }
//   ⚠️ interactInfo 只有 { liked, likedCount, sticky } ——
//      列表接口不返回评论/收藏/分享，需打开单条笔记才能拿到。
//      所以这三项置 null（不是 0），由 metrics 标为「不可得」，避免算出假的 0%。
function normalizeXhs(raw) {
  const u = raw.user || {};
  const notes = raw.notes || [];
  const account = {
    id: u.userId || u.user_id || '',
    name: u.nickname || '',
    fans: parseCount(u.fans),
    total_likes: parseCount(u.likedCount != null ? u.likedCount : u.interaction),
    post_count: notes.length,
    bio: u.desc || '',
  };
  const posts = notes.map((n) => {
    const c = n.noteCard || {};
    const s = c.interactInfo || {};
    return {
      id: c.noteId || n.id || '',
      title: c.displayTitle || '',
      create_time: ts(c.time),
      url: `https://www.xiaohongshu.com/explore/${c.noteId || n.id}`,
      media_type: c.type === 'video' ? 'video' : 'image_album',
      media_count: 1, // 列表接口不含图片数组，需单条抓取
      play: null,     // 小红书不公开播放量
      digg: parseCount(s.likedCount != null ? s.likedCount : s.liked),
      comment: null,  // 不可得（需单条抓取）
      share: null,    // 不可得
      collect: null,  // 不可得
      danmaku: 0,
      tags: [],
      raw: n,
    };
  });
  return {
    platform: 'xiaohongshu',
    account,
    posts,
    _unavailable: ['comment', 'share', 'collect', 'play'],
  };
}

// ── Instagram ───────────────────────────────────────────
function normalizeInstagram(raw) {
  const u = raw.user || {};
  const account = {
    id: u.id || '',
    name: u.username || '',
    fans: u.edge_followed_by ? u.edge_followed_by.count : (u.follower_count || 0),
    total_likes: 0,
    post_count: u.edge_owner_to_timeline_media ? u.edge_owner_to_timeline_media.count : (u.media_count || 0),
    bio: u.biography || '',
  };
  const edges = (u.edge_owner_to_timeline_media && u.edge_owner_to_timeline_media.edges) || raw.media || [];
  const posts = edges.map((e) => {
    const n = e.node || e;
    const likes = n.edge_liked_by ? n.edge_liked_by.count : (n.like_count || 0);
    const cmts = n.edge_media_to_comment ? n.edge_media_to_comment.count : (n.comment_count || 0);
    const isVideo = n.is_video || n.media_type === 2;
    return {
      id: n.id || n.shortcode,
      title: ((n.edge_media_to_caption && n.edge_media_to_caption.edges[0] && n.edge_media_to_caption.edges[0].node.text) || n.caption || '').slice(0, 200),
      create_time: ts(n.taken_at_timestamp || n.timestamp),
      url: `https://www.instagram.com/p/${n.shortcode || n.code}/`,
      media_type: isVideo ? 'video' : (n.__typename === 'GraphSidecar' || (n.children && n.children.length) ? 'image_album' : 'image'),
      media_count: n.edge_sidecar_to_children ? n.edge_sidecar_to_children.edges.length : 1,
      play: n.video_view_count || 0,
      digg: likes,
      comment: cmts,
      share: 0, // INS 不公开分享数
      collect: 0, // INS 不公开收藏数
      danmaku: 0,
      tags: (String(n.caption || '').match(/#([^\s#]+)/g) || []).map((s) => s.slice(1)),
      raw: n,
    };
  });
  return { platform: 'instagram', account, posts };
}

const ADAPTERS = { douyin: normalizeDouyin, bilibili: normalizeBilibili, xiaohongshu: normalizeXhs, instagram: normalizeInstagram };

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

(async () => {
  const args = parseArgs();
  const p = args.platform;
  if (!ADAPTERS[p]) { console.error('未知平台: ' + p + '，支持: ' + Object.keys(ADAPTERS).join(', ')); process.exit(1); }
  const raw = JSON.parse(fs.readFileSync(args.raw, 'utf8'));
  const profileText = args.profile ? fs.readFileSync(args.profile, 'utf8') : null;
  const out = ADAPTERS[p](raw, profileText);
  fs.writeFileSync(args.out || 'posts.json', JSON.stringify(out, null, 2), 'utf8');
  console.log(`✅ 归一化完成 | 平台=${out.platform} | 账号=${out.account.name || '(未解析)'} | 粉丝=${out.account.fans} | 作品=${out.posts.length}`);
})();
