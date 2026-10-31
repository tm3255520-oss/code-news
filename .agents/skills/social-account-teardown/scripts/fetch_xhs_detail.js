/**
 * 小红书单条笔记详情抓取 —— 补上列表接口拿不到的那半数据。
 *
 * 为什么必须有这个脚本：
 *   列表接口（user_posted）的 interactInfo **只有 likedCount**。
 *   评论/收藏/分享三项在 normalize 里被迫置 null，metrics 会把它们标为「不可得」。
 *   结果就是：小红书账号算不出互动结构，也做不了爆款因子分析。
 *   这三项只有打开单条笔记才能拿到 —— 这是当前最大的数据缺口。
 *
 * 用法:
 *   node fetch_xhs_detail.js --posts xhs_test/posts.json --port 9337 \
 *        --out xhs_test/details.json --merge xhs_test/posts_full.json [--limit 10] [--delay 4000]
 *
 * 前置条件：
 *   1. Chrome 已带 --remote-debugging-port=9337 启动，且是**有头模式**（UA 不含 Headless）
 *   2. 该 user-data-dir 里已有小红书登录态（用 login_helper.js 登录过一次即可）
 *   未登录时详情页同样有登录墙，脚本会明确报「登录墙」而不是静默返回空。
 *
 * 已知限制（实测踩过的）：
 *   - **xsec_token 会过期**。列表里带的 token 有时效，过期后页面会跳错误态。
 *     脚本会检测 detail 为空并提示「token 可能过期，请重跑 fetch_xhs.js 拿新 token」。
 *   - 单条详情是 SSR + Vue3 ref，字段在 __INITIAL_STATE__.note.noteDetailMap[id].note 里，
 *     且被 Vue ref 包着，必须 unref 才能读到值（同 fetch_xhs.js 的坑 #1）。
 *   - 状态树有循环引用，**只能逐字段抽、不能整块 JSON.stringify**（同坑 #2）。
 */
const fs = require('fs');
const path = require('path');
const { CDP, DEFAULT_UA } = require('./cdp_client');

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

// Vue3 ref 解包 + 定位到单条笔记详情。单行无注释，拼进 IIFE（拼多行前缀不稳定，见 fetch_xhs.js 坑 #4）
const HELPERS =
  "const __u=(o)=>(o&&typeof o==='object'&&o.__v_isRef)?(o._value!==undefined?o._value:o._rawValue):o;" +
  "const __S=()=>window.__INITIAL_STATE__||{};" +
  "const __N=()=>__u(__S().note)||{};" +
  "const __MAP=()=>__u(__N().noteDetailMap)||{};" +
  "const __D=(id)=>{const m=__MAP();const e=__u(m[id])||{};return __u(e.note)||{};};" +
  "const __num=(v)=>{if(v===null||v===undefined||v==='')return null;const s=String(v).replace(/,/g,'');" +
  "const m=s.match(/^([\\d.]+)\\s*([万wWkK亿]?)/);if(!m)return null;const n=parseFloat(m[1]);" +
  "if(m[2]==='万'||m[2]==='w'||m[2]==='W')return Math.round(n*1e4);" +
  "if(m[2]==='亿')return Math.round(n*1e8);if(m[2]==='k'||m[2]==='K')return Math.round(n*1e3);return Math.round(n);};";

const wrap = (body) => `(()=>{${HELPERS}${body}})()`;

/** 从 posts.json 里取出 noteId + xsecToken（token 在顶层 raw 或 noteCard 上，两处都试） */
function readTargets(postsFile) {
  const j = JSON.parse(fs.readFileSync(postsFile, 'utf8'));
  return j.posts.map((p) => {
    const r = p.raw || {};
    const c = r.noteCard || {};
    return {
      id: p.id,
      title: p.title,
      list_digg: p.digg,
      token: r.xsecToken || c.xsecToken || r.xsec_token || '',
    };
  }).filter((t) => t.id);
}

(async () => {
  const args = parseArgs();
  if (!args.posts) { console.error('缺少 --posts <posts.json>'); process.exit(1); }

  const limit = parseInt(args.limit || '10', 10);
  const delay = parseInt(args.delay || '4000', 10);
  const wait = parseInt(args.wait || '9000', 10);
  const port = args.port || '9337';

  let targets = readTargets(args.posts);
  if (args.ids) {
    const set = new Set(args.ids.split(',').map((s) => s.trim()));
    targets = targets.filter((t) => set.has(t.id));
  }
  if (args.top) {
    targets = [...targets].sort((a, b) => (b.list_digg || 0) - (a.list_digg || 0)).slice(0, parseInt(args.top, 10));
  }
  targets = targets.slice(0, limit);

  const noToken = targets.filter((t) => !t.token);
  if (noToken.length) {
    console.warn(`⚠️ ${noToken.length} 条笔记没有 xsec_token，详情页可能打不开。`);
    console.warn('   解决办法：重跑 fetch_xhs.js 重新抓一次列表（token 是列表接口下发的）。');
  }

  console.log(`准备抓取 ${targets.length} 条笔记详情 | port=${port} | 间隔 ${delay}ms`);

  const cdp = new CDP(port);
  await cdp.connect();

  // 拦截评论接口：详情页会加载评论，顺手拿回来（高赞评论 = 用户共鸣点）
  const hits = new Map();
  cdp.on((m) => {
    if (m.method === 'Network.responseReceived') {
      const u = m.params.response.url || '';
      if (/api\/sns\/web\/v2\/comment\/(page|sub\/page)/.test(u)) hits.set(m.params.requestId, { url: u, done: false });
    } else if (m.method === 'Network.loadingFinished') {
      const e = hits.get(m.params.requestId);
      if (e) e.done = true;
    }
  });

  const ev = (body) => cdp.evaluate(wrap(body)).catch((e) => '__ERR__' + String(e.message).slice(0, 120));

  // 先确认登录态（未登录时详情页也是登录墙，早失败早提示）
  const results = [];
  let wallHits = 0, tokenExpired = 0;

  for (let i = 0; i < targets.length; i++) {
    const t = targets[i];
    // 没有 token 时用裸 URL，小红书可能重定向，成功率低但值得一试
    const url = t.token
      ? `https://www.xiaohongshu.com/explore/${t.id}?xsec_token=${encodeURIComponent(t.token)}&xsec_source=pc_user`
      : `https://www.xiaohongshu.com/explore/${t.id}`;
    hits.clear();

    process.stdout.write(`\n[${i + 1}/${targets.length}] ${t.id} … `);
    await cdp.init(url, DEFAULT_UA);
    await cdp.sleep(wait);
    // 滚一下触发评论区懒加载
    await cdp.evaluate(`window.scrollTo(0, 600); 'ok'`).catch(() => {});
    await cdp.sleep(2500);

    const bodyTxt = String(await ev(`return document.body.innerText.replace(/\\s+/g,' ').slice(0,300);`));
    if (/扫码登录|登录后查看|登录即可查看/.test(bodyTxt)) {
      wallHits++;
      console.log('❌ 登录墙 —— 登录态已失效，请重跑 login_helper.js');
      results.push({ id: t.id, ok: false, reason: 'login_wall' });
      if (wallHits >= 2) { console.log('\n⚠️ 连续 2 条都是登录墙，提前中止（继续跑只会浪费时间）。'); break; }
      await cdp.sleep(delay);
      continue;
    }

    // 字段名为实测所得，勿凭印象改（2026-09-05 实探）：
    //   note.interactInfo = { likedCount, collectedCount, commentCount, shareCount, liked, collected, ... }
    //   注意是 shareCount 不是 sharedCount；图片数组是 imageList 不是 imagesList
    const json = await cdp.evaluate(wrap(
      `const m=__MAP();const e=__u(m[${JSON.stringify(t.id)}])||{};const n=__u(e.note)||{};` +
      `if(!n||!Object.keys(n).length)return JSON.stringify({ok:false});` +
      `const i=n.interactInfo||{};const im=n.imageList||n.imagesList||[];` +
      `const v=n.video||{};const cap=v.capacity||v.media||{};` +
      // 评论直接躺在状态树的 noteDetailMap[id].comments 里，比网络拦截更可靠
      `const cm=__u(e.comments)||{};const cl=__u(cm.comments)||__u(cm.list)||[];` +
      `const cs=(Array.isArray(cl)?cl:[]).slice(0,30).map((c0)=>{const x=__u(c0)||{};` +
      `const u=__u(x.user_info)||__u(x.user)||{};` +
      `return {id:x.id||'',user:u.nickname||'',content:(x.content||'').slice(0,200),` +
      `like_count:__num(x.like_count)||0,sub_count:__num(x.sub_comment_count)||0,create_time:x.create_time||0};});` +
      `return JSON.stringify({ok:true,type:n.type||'',title:n.title||'',` +
      `desc:(n.desc||'').slice(0,600),` +
      `likedCount:__num(i.likedCount),collectedCount:__num(i.collectedCount),` +
      `commentCount:__num(i.commentCount),shareCount:__num(i.shareCount!==undefined?i.shareCount:i.sharedCount),` +
      `imgCount:Array.isArray(im)?im.length:0,` +
      `time:n.time||n.lastUpdateTime||0,` +
      `tags:(n.tagList||[]).map((x)=>(x&&x.name)||'').filter(Boolean),` +
      `duration:cap.duration||0,` +
      `ipLocation:n.ipLocation||'',` +
      `comments:cs});`
    )).catch(() => '__ERR__');

    let d = null;
    if (json && !String(json).startsWith('__')) { try { d = JSON.parse(json); } catch (e) {} }

    if (!d || !d.ok) {
      tokenExpired++;
      console.log('⚠️ 详情为空 —— token 可能已过期，或该笔记已删除/仅好友可见');
      results.push({ id: t.id, ok: false, reason: 'empty_detail' });
      await cdp.sleep(delay);
      continue;
    }

    // 评论：优先用状态树里那份，网络拦截作为补充（两者去重合并）
    const comments = [...(d.comments || [])];
    const seen = new Set(comments.map((c) => c.id));
    for (const [rid, e] of hits) {
      if (!e.done) continue;
      try {
        const r = await cdp.send('Network.getResponseBody', { requestId: rid });
        const b = JSON.parse(r.body || '{}');
        const list = (b.data && b.data.comments) || [];
        for (const c of list) {
          if (seen.has(c.id)) continue;
          seen.add(c.id);
          comments.push({
            id: c.id,
            user: (c.user_info && c.user_info.nickname) || '',
            content: (c.content || '').slice(0, 200),
            like_count: c.like_count || 0,
            sub_count: c.sub_comment_count || 0,
            create_time: c.create_time || 0,
          });
        }
      } catch (err) {}
    }

    results.push({
      id: t.id, title: t.title || d.title, ok: true,
      type: d.type, desc: d.desc, time: d.time,
      digg: d.likedCount, comment: d.commentCount, collect: d.collectedCount, share: d.shareCount,
      img_count: d.imgCount, tags: d.tags, duration: d.duration, ip_location: d.ipLocation,
      comments: comments.slice(0, 30),
      url: url.split('?')[0],
    });
    console.log(`✅ 赞${d.likedCount} 评${d.commentCount} 藏${d.collectedCount} 享${d.shareCount} 图${d.imgCount} 评论${comments.length}条`);

    await cdp.sleep(delay);
  }

  const outPath = args.out || 'xhs_details.json';
  fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');

  const ok = results.filter((r) => r.ok);
  console.log(`\n════ 汇总 ════`);
  console.log(`成功 ${ok.length} / ${results.length}`);
  if (ok.length) {
    const avg = (f) => Math.round(ok.reduce((s, r) => s + (r[f] || 0), 0) / ok.length * 10) / 10;
    console.log(`均值：赞 ${avg('digg')} | 评 ${avg('comment')} | 藏 ${avg('collect')} | 享 ${avg('share')} | 图 ${avg('img_count')}`);
    console.log(`抓到评论总数：${ok.reduce((s, r) => s + r.comments.length, 0)}`);
  }
  if (tokenExpired) console.log(`⚠️ ${tokenExpired} 条详情为空（token 过期/笔记不可见）—— 重跑 fetch_xhs.js 拿新 token 再试。`);
  if (wallHits) console.log(`⚠️ ${wallHits} 条撞登录墙 —— 重跑 login_helper.js 重新登录。`);
  console.log(`✅ 详情已写入 ${outPath}`);

  // ── 合并回 posts.json ──
  if (args.merge) {
    const j = JSON.parse(fs.readFileSync(args.posts, 'utf8'));
    const map = new Map(ok.map((r) => [r.id, r]));
    let patched = 0;
    for (const p of j.posts) {
      const d = map.get(p.id);
      if (!d) continue;
      p.comment = d.comment;
      p.collect = d.collect;
      p.share = d.share;
      if (d.img_count) p.media_count = d.img_count;
      if (d.digg != null) p.digg = d.digg;
      if (d.tags && d.tags.length) p.tags = d.tags;
      p._detail = { desc: d.desc, ip_location: d.ip_location, duration: d.duration, comments: d.comments };
      patched++;
    }
    // 全部补齐后即可从"不可得"清单里移除，让 metrics 正常计算互动结构
    if (j._unavailable) {
      const stillMissing = [];
      for (const k of j._unavailable) {
        const allHave = j.posts.every((p) => p[k] !== null && p[k] !== undefined);
        if (!allHave) stillMissing.push(k);
      }
      j._unavailable = stillMissing;
    }
    fs.writeFileSync(args.merge, JSON.stringify(j, null, 2), 'utf8');
    console.log(`✅ 已合并 ${patched} 条 → ${args.merge}`);
    console.log(`   仍不可得的字段：${(j._unavailable || []).join(', ') || '无（已全部补齐）'}`);
  }

  cdp.close();
  process.exit(0);
})().catch((e) => { console.error('ERR', e.stack); process.exit(1); });
