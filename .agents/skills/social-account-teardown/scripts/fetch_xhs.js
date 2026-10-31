/**
 * 小红书账号抓取
 *
 * 验证状态：2026-09-04 实测通过 —— 登录后成功读到账号信息与笔记列表。
 *
 * 四个已探明的坑（都是实测踩出来的，勿改回）：
 *
 * 1. 【Vue 3 ref 包装】__INITIAL_STATE__ 里的值不是裸数据，而是 Vue 响应式 ref。
 *    直接取 s.user.userInfo 得到的是 {dep,__v_isRef,__v_isShallow,_rawValue,_value}，
 *    昵称/粉丝这些真实字段全在 _value（或 _rawValue）里。必须先 unref。
 *    实测：昵称取到「隐形婴儿」，notes 是数组、len=5。
 *
 * 2. 【循环引用】状态树有循环引用，整块 JSON.stringify 会抛 Uncaught
 *    （报错栈指向小红书自己的 library-polyfill）。所以：
 *      - 每个查询都包成自包含 IIFE，单次只返回一个短字符串
 *      - 整体序列化笔记数组要 try/catch，失败则降级逐条抽字段
 *
 * 3. 【登录墙 + cookie 陷阱】未登录态页面直接显示「登录即可查看 Ta 的笔记」，
 *    一条都不给（比抖音更狠）。而且 **web_session 是访客就会下发的 cookie**，
 *    不能作为登录凭证 —— 实测 cookie 里有 web_session（有效期到 2027），
 *    但页面 loggedIn._value = false。必须用 login_helper 的页面判定。
 *
 * 4. 【注入方式】多行 PRELUDE 前缀 + 多语句拼接不稳定，实测会抛 Uncaught。
 *    改成单次 IIFE、helper 单行无注释，稳定通过。
 *
 * 用法:
 *   node scripts/login_helper.js --url "<用户主页URL>" --port 9337   # 先登录
 *   node scripts/fetch_xhs.js --url "<用户主页URL>" --port 9337 --out workdir/
 *   node scripts/normalize.js --platform xiaohongshu --raw workdir/xhs_raw.json --out workdir/posts.json
 */
const fs = require('fs');
const path = require('path');
const { CDP, DEFAULT_UA } = require('./cdp_client');

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

// helper 单行无注释，拼进 IIFE
const HELPERS =
  "const __u=(o)=>(o&&typeof o==='object'&&o.__v_isRef)?(o._value!==undefined?o._value:o._rawValue):o;" +
  "const __S=()=>window.__INITIAL_STATE__||{};" +
  "const __U=()=>__u(__S().user)||{};" +
  "const __I=()=>__u(__U().userInfo)||{};" +
  // notes 实测是「分页数组」：notes[0] 本身又是一个数组（或直接是笔记对象数组）。
  // 所以要判断首元素是否为数组，是则摊平一层，得到笔记对象 { id, noteCard:{...} }。
  "const __N=()=>{const r=__u(__U().notes);if(!r)return[];" +
  "let a=Array.isArray(r)?r:Object.keys(r).map((k)=>__u(r[k]));" +
  "if(a.length&&Array.isArray(a[0])){const o=[];a.forEach((s)=>{if(Array.isArray(s))o.push(...s);else o.push(s);});return o;}" +
  "return a;};" +
  // 笔记真实字段在 noteCard 里，不是顶层
  "const __C=(i)=>{const x=__N()[i]||{};return x.noteCard||{};};";

const wrap = (body) => `(()=>{${HELPERS}${body}})()`;

(async () => {
  const args = parseArgs();
  if (!args.url) { console.error('缺少 --url <用户主页 URL>'); process.exit(1); }
  const out = args.out || '.';
  fs.mkdirSync(out, { recursive: true });

  const cdp = new CDP(args.port || '9337');
  await cdp.connect();

  const hits = new Map();
  cdp.on((m) => {
    if (m.method === 'Network.responseReceived') {
      const u = m.params.response.url || '';
      if (/api\/sns\/web\/v1\/(user_posted|user\/otherinfo|user\/posted|user_profile)/.test(u)) {
        hits.set(m.params.requestId, { url: u, done: false });
      }
    } else if (m.method === 'Network.loadingFinished') {
      const e = hits.get(m.params.requestId);
      if (e) e.done = true;
    }
  });

  await cdp.init(args.url, DEFAULT_UA);
  console.log('等待 18s 首屏…');
  await cdp.sleep(18000);
  for (let i = 0; i < 4; i++) {
    await cdp.evaluate(`window.scrollTo(0, document.body.scrollHeight); 'ok'`).catch(() => {});
    await cdp.sleep(3500);
  }

  const ev = (body) =>
    cdp.evaluate(wrap(body)).catch((e) => '__ERR__' + String(e.message).slice(0, 120));

  // ── 登录状态 ──
  const loggedIn = String(await ev(`return String(__u(__S().user.loggedIn));`));
  const bodyTxt = String(await ev(`return document.body.innerText.replace(/\\s+/g,' ').slice(0,200);`));
  const wall = /登录即可查看|扫码登录/.test(bodyTxt);
  console.log('\n──── 登录状态 ────');
  console.log(`  loggedIn = ${loggedIn}`);
  if (wall) console.log('  ⚠️ 页面仍显示登录墙');

  // ── 账号信息 ──
  // 🔴 陷阱：user.userInfo 是【登录用户】不是【页面用户】！
  //    实测踩坑：抓别人的主页，昵称/uid 却是自己的。
  //    页面用户的可靠来源：①笔记的 noteCard.user（昵称/uid）②userPageData（粉丝/简介/IP）
  const nick = String(await ev(`const n=__N()[0];const u=n&&n.noteCard&&n.noteCard.user;return String((u&&(u.nickname||u.nickName))||__I().nickname||'');`));
  const uid = String(await ev(`const n=__N()[0];const u=n&&n.noteCard&&n.noteCard.user;return String((u&&u.userId)||__I().userId||'');`));
  // 粉丝/获赞不在 userInfo 里，而在 userPageData.interactions 数组：
  // [{type:'follows',name:'关注',count:'..'},{type:'fans',name:'粉丝',count:'..'},...]
  const fans = String(await ev(`const p=__u(__U().userPageData)||{};const a=p.interactions||[];const f=a.find((x)=>x.type==='fans'||x.name==='粉丝');return f?String(f.count):'';`));
  const liked = String(await ev(`const p=__u(__U().userPageData)||{};const a=p.interactions||[];const f=a.find((x)=>/赞|收藏/.test(x.name||'')||x.type==='interaction');return f?String(f.count):'';`));
  const desc = String(await ev(`const p=__u(__U().userPageData)||{};const b=__u(p.basicInfo)||{};return String(b.desc||__I().desc||'').slice(0,80);`));
  console.log('\n──── 账号 ────');
  console.log(`  昵称=${nick || '(空)'}  uid=${uid || '(空)'}  粉丝=${fans || '(空)'}  获赞与收藏=${liked || '(空)'}`);
  if (desc) console.log(`  简介=${desc}`);

  // ── 笔记 ──
  const count = parseInt(String(await ev(`return String(__N().length);`)), 10) || 0;
  console.log(`\n──── 笔记 ────`);
  console.log(`  条数 = ${count}`);
  let notes = [];

  if (count > 0) {
    const keys = String(await ev(`const c=__C(0);const t=__N()[0]||{};return 'top:'+Object.keys(t).slice(0,12).join(',')+' | noteCard:'+Object.keys(c).slice(0,18).join(',');`));
    console.log(`  首条字段 = ${keys}`);

    const rawJson = await cdp.evaluate(wrap(`try{return JSON.stringify(__N());}catch(e){return '__SERIALIZE_ERR__';}`)).catch(() => '__ERR__');
    if (rawJson && !rawJson.startsWith('__')) {
      try { notes = JSON.parse(rawJson) || []; } catch (e) {}
    }
    if (notes.length) {
      console.log(`  ✅ 整体序列化成功 ${notes.length} 条`);
    } else {
      console.log('  ⚠️ 整体序列化失败（循环引用），降级为逐条抽字段');
      const FIELDS = ['noteId', 'note_id', 'id', 'displayTitle', 'title', 'desc', 'type', 'time', 'lastUpdateTime'];
      for (let i = 0; i < Math.min(count, 40); i++) {
        const rec = {};
        for (const f of FIELDS) {
          const v = await ev(`const x=__N()[${i}]||{};const c=x.noteCard||{};const v=(x[${JSON.stringify(f)}]!==undefined)?x[${JSON.stringify(f)}]:c[${JSON.stringify(f)}];return (v===undefined||v===null||typeof v==='object')?'':String(v);`);
          if (v && !String(v).startsWith('__ERR__')) rec[f] = v;
        }
        const inter = String(await ev(
          `const x=__C(${i});const i=x.interactInfo||x.interact_info||{};` +
          `return [i.likedCount!==undefined?i.likedCount:(i.liked||''),` +
          `i.commentCount!==undefined?i.commentCount:(i.comments||''),` +
          `i.sharedCount!==undefined?i.sharedCount:(i.shared||''),` +
          `i.collectedCount!==undefined?i.collectedCount:(i.collected||'')].join('|');`
        ));
        const p = inter.split('|');
        rec.interactInfo = { likedCount: p[0] || '', commentCount: p[1] || '', sharedCount: p[2] || '', collectedCount: p[3] || '' };
        rec.__images = String(await ev(`const x=__C(${i});const a=x.imagesList||x.images||[];return String(Array.isArray(a)?a.length:0);`));
        notes.push(rec);
      }
      console.log(`  ✅ 逐条抽取完成 ${notes.length} 条`);
    }
  }

  // ── 网络拦截补充 ──
  const bodies = [];
  for (const [rid, e] of hits) {
    if (!e.done) continue;
    try {
      const r = await cdp.send('Network.getResponseBody', { requestId: rid });
      bodies.push({ url: e.url, data: JSON.parse(r.body || '{}') });
    } catch (err) {}
  }

  fs.writeFileSync(path.join(out, 'xhs_raw.json'),
    JSON.stringify({ user: { userId: uid, nickname: nick, fans, likedCount: liked, desc }, notes }, null, 2), 'utf8');
  fs.writeFileSync(path.join(out, 'xhs_net.json'), JSON.stringify(bodies, null, 2), 'utf8');
  console.log(`\n✅ 落盘: ${path.join(out, 'xhs_raw.json')} | 网络拦截 ${bodies.length} 个`);

  if (wall || !notes.length) {
    console.log('\n⚠️ 没拿到笔记。若显示登录墙，先跑 login_helper.js 登录。');
  }
  cdp.close();
  process.exit(0);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
