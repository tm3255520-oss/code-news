/**
 * 登录助手 —— 打开一个可见浏览器窗口，停在目标站点等你手动登录，检测到登录态后退出。
 *
 * 为什么要单独一个脚本：
 *   小红书 / Instagram / B站作品列表 / 抖音小号，都需要登录态才能拿到数据。
 *   登录必须本人操作（扫码/验证码），脚本不能代劳。所以流程是：
 *     1. 本脚本开窗口 + 停在你眼前
 *     2. 你手动登录
 *     3. 脚本检测到登录态 → 退出
 *     4. 再跑 fetch_*.js（复用同一 port 和 user-data-dir，会话保持）
 *
 * ⚠️ 前置条件：Chrome 必须是【有头模式】。
 *   沙箱环境可能强制 headless（UA 里带 "HeadlessChrome"），此时没有可见窗口，
 *   用户根本无法扫码。启动 Chrome 时要跳出沙箱限制，并确认 UA 中不含 Headless。
 *
 * 用法: node login_helper.js --url "https://www.douyin.com/user/<sec>" [--port 9337] [--wait 360]
 */
const { CDP, DEFAULT_UA } = require('./cdp_client');

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

// 判定「已登录」的两套机制，优先用页面状态（更可靠），cookie 仅作兜底。
//
// ⚠️⚠️ cookie 只列【登录后才会有】的凭证。访客态就会下发的绝不能列入，否则误判。
//    实测踩坑 1（抖音）：passport_csrf_token / sid_tt 未登录访问就有，
//      曾导致 2 秒误报「已登录」，随后抓取仍拿空。
//    实测踩坑 2（小红书）：web_session 同样是访客就会下发的！
//      12 个 cookie 里明明有 web_session（有效期到 2027），
//      但页面 __INITIAL_STATE__.user.loggedIn._value 是 false，页面仍显示登录墙。
//      —— 所以 cookie 判定不可靠，必须以页面状态为准。
const LOGIN_COOKIES = {
  'douyin.com': ['sessionid', 'sessionid_ss'],
  'xiaohongshu.com': [], // 不可靠：访客也有 web_session，只能靠页面判定
  'instagram.com': ['sessionid', 'ds_user_id'],
  'bilibili.com': ['SESSDATA', 'DedeUserID'],
};
const DEFAULT_COOKIES = ['sessionid', 'SESSDATA'];

// 直接问页面「你登录了吗」，返回字符串 'true' / 'false'
const LOGIN_PROBES = {
  // 小红书：Vue 3 ref 包装，真实值在 _value
  'xiaohongshu.com':
    '(() => { try { const s = window.__INITIAL_STATE__; const u = s && s.user && s.user.loggedIn; ' +
    'return String(u && u._value !== undefined ? !!u._value : !!u); } catch (e) { return "probe-error"; } })()',
};

(async () => {
  const args = parseArgs();
  const url = args.url || 'https://www.douyin.com/';
  const port = args.port || '9337';
  const maxWait = parseInt(args.wait || '360', 10); // 秒

  const cdp = new CDP(port);
  await cdp.connect();

  // headless 检查：无头模式下用户看不到窗口，登录无从谈起
  const targets = await cdp._http('/json/version');
  if (/Headless/i.test(targets['User-Agent'] || '')) {
    console.log('❌ 当前 Chrome 是 headless 模式，没有可见窗口，无法手动登录。');
    console.log('   请关闭它，重新以有头模式启动（不要带 --headless，且需跳出沙箱限制），');
    console.log('   然后用 curl http://127.0.0.1:<port>/json/version 确认 UA 中不含 "Headless"。');
    process.exit(1);
  }

  const host = new URL(url).hostname.replace(/^www\./, '');
  const wanted = LOGIN_COOKIES[host] || DEFAULT_COOKIES;

  await cdp.init(url, DEFAULT_UA);
  await cdp.sleep(2500);
  try { await cdp.send('Page.bringToFront'); } catch (e) {}

  console.log('\n════════════════════════════════════════');
  console.log('  浏览器窗口已打开，请手动完成登录');
  console.log(`  目标站点: ${host}`);
  console.log(`  等待上限: ${maxWait}s`);
  console.log('════════════════════════════════════════\n');
  console.log('  登录完成后脚本会自动检测到并退出，然后即可运行 fetch_*.js\n');

  const probe = LOGIN_PROBES[host];
  const started = Date.now();
  let ok = false;
  while ((Date.now() - started) / 1000 < maxWait) {
    await cdp.sleep(2000);

    // 1) 页面状态判定（优先，最可靠）
    if (probe) {
      try {
        const v = String(await cdp.evaluate(probe));
        if (v === 'true') {
          console.log(`\n✅ 页面确认已登录（${host} 的 loggedIn = true）`);
          console.log(`   耗时 ${Math.round((Date.now() - started) / 1000)}s`);
          ok = true;
          break;
        }
      } catch (e) { /* 页面还没就绪，下一轮再试 */ }
    }

    // 2) cookie 兜底（仅当该平台有可靠的登录 cookie 时才用）
    if (wanted.length) {
      try {
        const c = await cdp.send('Network.getCookies', { urls: [url] });
        const names = (c.cookies || []).map((x) => x.name);
        const hit = names.filter((n) => wanted.includes(n));
        if (hit.length) {
          console.log(`\n✅ 检测到登录态（cookie: ${hit.join(', ')}）`);
          console.log(`   耗时 ${Math.round((Date.now() - started) / 1000)}s`);
          ok = true;
          break;
        }
      } catch (e) {}
    }

    const el = Math.round((Date.now() - started) / 1000);
    if (el % 20 === 0) console.log(`   …已等待 ${el}s`);
  }

  if (ok) console.log(`\n现在可以运行抓取脚本了，记得用同一个 --port ${port} 和 user-data-dir：`);

  if (!ok) {
    console.log(`\n⏱ 等待 ${maxWait}s 超时，未检测到登录态。`);
    console.log('   若你已登录但仍检测不到，可能是本脚本的 cookie 特征列表过时了 ——');
    console.log('   请打开开发者工具查看实际 cookie 名，并补进 LOGIN_COOKIES。');
  }
  cdp.close();
  process.exit(ok ? 0 : 2);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
