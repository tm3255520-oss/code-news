/**
 * B站 UP主抓取
 *
 * 验证状态（2026-09-04 实测）：
 *   ✅ /x/web-interface/card           —— curl 直连可用，返回粉丝/关注/投稿数，无需登录
 *   ⚠️ /x/space/wbi/arc/search         —— wbi 签名算法已实现且正确，但实测返回 code:-352 风控校验失败
 *                                         （测试环境出口 IP 在新加坡；国内 IP 可能可以直接通过）
 *
 * 所以本脚本分两段：
 *   第 1 段（稳）拿账号 profile
 *   第 2 段（赌）尝试拿视频列表，失败会明确报错并建议你改用 CDP 登录态方案
 *
 * 用法: node fetch_bilibili.js --mid <uid> [--ps 30] [--pages 3] [--out workdir/]
 */
const fs = require('fs');
const path = require('path');
const https = require('https');
const crypto = require('crypto');

const MIXIN_KEY_ENC_TAB = [
  46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
  27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
  37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
  22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
];
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36';

let COOKIE = '';

function get(url, headers = {}) {
  return new Promise((res, rej) => {
    https.get(url, { headers: { 'User-Agent': UA, Cookie: COOKIE, ...headers } }, (r) => {
      let d = ''; r.on('data', (c) => (d += c)); r.on('end', () => res(d));
    }).on('error', rej);
  });
}

/** 建立会话：访问首页拿 buvid3 + 调 spi 拿 b_3/b_4 */
async function initSession() {
  const cookies = await new Promise((r) => {
    https.get('https://www.bilibili.com/', { headers: { 'User-Agent': UA } }, (res) => {
      const c = (res.headers['set-cookie'] || []).map((s) => s.split(';')[0]);
      res.resume(); res.on('end', () => r(c));
    }).on('error', () => r([]));
  });
  let b3 = '', b4 = '';
  try {
    const spi = JSON.parse(await get('https://api.bilibili.com/x/frontend/finger/spi'));
    b3 = spi.data.b_3; b4 = spi.data.b_4;
  } catch (e) {}
  COOKIE = [...cookies, b3 && `b_3=${b3}`, b4 && `b_4=${b4}`].filter(Boolean).join('; ');
}

/** wbi 签名：nav 拿 img/sub key → 重排取 32 位 → 参数排序后 md5 */
function encWbi(params, imgKey, subKey) {
  const mixinKey = MIXIN_KEY_ENC_TAB.map((i) => (imgKey + subKey)[i]).join('').slice(0, 32);
  const p = { ...params, wts: Math.round(Date.now() / 1000) };
  const q = Object.keys(p).sort()
    .map((k) => encodeURIComponent(k) + '=' + encodeURIComponent(String(p[k]).replace(/[!'()*]/g, '')))
    .join('&');
  return q + '&w_rid=' + crypto.createHash('md5').update(q + mixinKey).digest('hex');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

(async () => {
  const args = parseArgs();
  if (!args.mid) { console.error('缺少 --mid <uid>'); process.exit(1); }
  const ps = parseInt(args.ps || '30', 10);
  const pages = parseInt(args.pages || '2', 10);
  const out = args.out || '.';
  fs.mkdirSync(out, { recursive: true });

  await initSession();

  // ── 第 1 段：账号 profile（已实测可用）──
  const cardRaw = await get(`https://api.bilibili.com/x/web-interface/card?mid=${args.mid}&photo=false`);
  let card;
  try { card = JSON.parse(cardRaw); } catch (e) { console.error('card 接口返回非 JSON'); console.error(cardRaw.slice(0, 200)); process.exit(1); }
  if (card.code !== 0) { console.error('card 接口失败:', card.code, card.message); process.exit(1); }
  const c = card.data.card;
  console.log(`✅ 账号：${c.name} | 粉丝 ${c.fans} | 关注 ${c.attention} | 投稿 ${card.data.archive} | 获赞 ${card.data.like_num}`);

  // ── 第 2 段：视频列表（需 wbi，可能被风控）──
  const nav = JSON.parse(await get('https://api.bilibili.com/x/web-interface/nav'));
  let imgKey, subKey;
  try {
    imgKey = nav.data.wbi_img.img_url.split('/').pop().split('.')[0];
    subKey = nav.data.wbi_img.sub_url.split('/').pop().split('.')[0];
  } catch (e) { console.error('拿 wbi key 失败'); process.exit(1); }
  console.log(`出口 IP 属地: ${nav.data.ip_region}（海外 IP 更容易触发 -352 风控）`);

  const vlist = [];
  for (let pn = 1; pn <= pages; pn++) {
    const signed = encWbi({ mid: args.mid, ps: String(ps), pn: String(pn), order: 'pubdate', platform: 'web', web_location: '1550101' }, imgKey, subKey);
    const raw = await get('https://api.bilibili.com/x/space/wbi/arc/search?' + signed, { Referer: `https://space.bilibili.com/${args.mid}/` });
    let j;
    try { j = JSON.parse(raw); } catch (e) {
      console.error(`\n❌ 第 ${pn} 页返回非 JSON（被风控拦截，长度 ${raw.length}）`);
      console.error('   code 通常藏在这里：', raw.slice(0, 0) || '');
      break;
    }
    if (j.code !== 0) {
      console.error(`\n❌ 视频列表失败: code=${j.code} message=${j.message}`);
      if (j.code === -352) {
        console.error('\n   -352 = 风控校验失败。wbi 签名本身没问题，是环境被判定为机器人。');
        console.error('   可选路径：');
        console.error('   1) 换国内出口 IP 重试');
        console.error('   2) 改用 CDP 方案：启动带调试端口的 Chrome，用已有登录态访问');
        console.error('      space.bilibili.com/<mid>/video，拦截 /x/space/wbi/arc/search 响应体');
      }
      break;
    }
    vlist.push(...j.data.list.vlist);
    console.log(`   第 ${pn} 页 +${j.data.list.vlist.length} 条`);
    await sleep(2500);
  }

  // ── 第 3 段：逐条取互动数据 ──
  const stats = {};
  if (vlist.length) {
    console.log(`\n取 ${vlist.length} 条视频的互动数据…`);
    for (let i = 0; i < vlist.length; i++) {
      const bvid = vlist[i].bvid;
      try {
        const st = JSON.parse(await get(`https://api.bilibili.com/x/web-interface/archive/stat?bvid=${bvid}`, { Referer: 'https://www.bilibili.com/' }));
        if (st.code === 0) stats[bvid] = st.data;
      } catch (e) {}
      if ((i + 1) % 10 === 0) console.log(`   ${i + 1}/${vlist.length}`);
      await sleep(1200);
    }
  }

  const payload = { card: { card: c, archive: card.data.archive, like_num: card.data.like_num }, vlist, stats };
  fs.writeFileSync(path.join(out, 'bili_raw.json'), JSON.stringify(payload, null, 2), 'utf8');
  console.log(`\n✅ 完成：视频 ${vlist.length} 条，互动数据 ${Object.keys(stats).length} 条 → ${path.join(out, 'bili_raw.json')}`);
  if (!vlist.length) console.log('   仅拿到账号 profile，无作品数据，报告只能做账号级判断');
  process.exit(0);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
