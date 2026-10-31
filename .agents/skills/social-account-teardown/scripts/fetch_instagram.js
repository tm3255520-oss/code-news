/**
 * Instagram 账号抓取
 *
 * ❌ 验证状态：【未登录不可行，已实测】
 *    2026-09-04 实测：GET https://www.instagram.com/api/v1/users/web_profile_info/?username=xxx
 *    带 x-ig-app-id header → HTTP 429（限流）。匿名态已被封死。
 *
 * 唯一现实路径：登录态 + CDP。
 *   1. 用独立 user-data-dir 启动 Chrome（见 SKILL.md）
 *   2. 在打开的浏览器里手动登录一次 Instagram
 *   3. 重跑本脚本 —— 复用同一 profile 目录，会话保持
 *
 * 拦截目标：
 *   - /api/v1/feed/user/<user_id>/  （含关注者可见内容）
 *   - /graphql/query                （新版主页走 GraphQL）
 *
 * ⚠️ 合规提示：仅用于拆解用户自己有权查看的公开账号数据，
 *    不做批量爬取、不绕过付费墙、不伪造身份。
 *
 * 用法: node fetch_instagram.js --username <name> [--port 9335] [--out workdir/]
 */
const fs = require('fs');
const path = require('path');
const { CDP, DEFAULT_UA } = require('./cdp_client');

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

(async () => {
  const args = parseArgs();
  if (!args.username) { console.error('缺少 --username <name>'); process.exit(1); }
  const out = args.out || '.';
  fs.mkdirSync(out, { recursive: true });

  const cdp = new CDP(args.port || '9335');
  await cdp.connect();

  const hits = new Map();
  cdp.on((m) => {
    if (m.method === 'Network.responseReceived') {
      const u = m.params.response.url || '';
      if (/api\/v1\/feed\/user\/|graphql\/query|api\/v1\/users\/web_profile_info/.test(u)) {
        hits.set(m.params.requestId, { url: u, done: false });
      }
    } else if (m.method === 'Network.loadingFinished') {
      const e = hits.get(m.params.requestId);
      if (e) e.done = true;
    }
  });

  const url = `https://www.instagram.com/${args.username}/`;
  await cdp.init(url, DEFAULT_UA);
  console.log('等待 20s…');
  await cdp.sleep(20000);

  // 检测是否被登录墙挡住
  const wall = await cdp.evaluate(`(() => {
    const t = document.body.innerText || '';
    return JSON.stringify({
      hasLoginForm: !!document.querySelector('form#loginForm, input[name="username"]'),
      saysLogin: /Log in|登录|Sign up/.test(t.slice(0, 800)),
      bodyHead: t.slice(0, 200)
    });
  })()`).catch(() => null);
  if (wall) {
    const w = typeof wall === 'string' ? JSON.parse(wall) : wall;
    if (w.hasLoginForm || w.saysLogin) {
      console.log('\n⚠️ 检测到登录墙。请在刚打开的 Chrome 里登录 Instagram，然后重跑本脚本。');
      console.log('   （务必复用同一 --user-data-dir 和 --port，否则会话丢失）');
    }
  }

  for (let i = 0; i < 4; i++) {
    await cdp.evaluate(`window.scrollTo(0, document.body.scrollHeight); 'ok'`).catch(() => {});
    await cdp.sleep(4000);
  }

  const bodies = [];
  for (const [rid, e] of hits) {
    if (!e.done) continue;
    try {
      const r = await cdp.send('Network.getResponseBody', { requestId: rid });
      const j = JSON.parse(r.body || '{}');
      bodies.push({ url: e.url, data: j });
    } catch (err) {}
  }

  fs.writeFileSync(path.join(out, 'ig_raw.json'), JSON.stringify(bodies, null, 2), 'utf8');

  console.log(`\n拦截到 ${bodies.length} 个响应 → ${path.join(out, 'ig_raw.json')}`);
  bodies.slice(0, 5).forEach((b) => {
    console.log(`  ${b.url.slice(0, 100)}`);
    console.log(`    keys=${Object.keys(b.data).slice(0, 10).join(',')}`);
  });

  if (!bodies.length) {
    console.log('\n❌ 没拿到任何数据。');
    console.log('   1) 确认已在弹出的 Chrome 里登录 Instagram');
    console.log('   2) 确认 username 正确');
    console.log('   3) 若平台接口已改版，请检查上面的拦截正则是否还匹配，并更新本脚本');
  }
  cdp.close();
  process.exit(0);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
