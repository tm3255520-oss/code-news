/**
 * 抖音账号抓取 —— 【已端到端实测通过】2026-09-03 成功抓取 18 条完整数据
 *
 * 原理：让浏览器自己发请求，我们只在网络层截获响应。
 *   Network.enable → 监听 responseReceived 匹配 aweme/v1/web/aweme/post
 *   → loadingFinished 后 Network.getResponseBody 取回 → 抽 aweme_list
 * 分页由「真实滚动 + 点击加载更多」触发。
 *
 * ❌ 反面教材：不要改用页内 fetch() 直接调 API。实测只返回 93 字节空结果，
 *    抖音校验完整请求头链，页内构造不出来。参见 ../references/platform-adapters.md
 *
 * 用法:
 *   node fetch_douyin.js --sec MS4wLjABAAAA... [--port 9335] [--scroll 6] [--out workdir/]
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
  if (!args.sec) { console.error('缺少 --sec <sec_user_id>'); process.exit(1); }
  const port = args.port || '9335';
  const scrollCount = parseInt(args.scroll || '6', 10);
  const out = args.out || '.';
  fs.mkdirSync(out, { recursive: true });

  const cdp = new CDP(port);
  const currentUrl = await cdp.connect();
  console.log('已连接 CDP，当前页面:', String(currentUrl).slice(0, 80));

  // 半自动登录：先停在抖音首页等用户扫码，拿到登录态再继续抓。
  // 很多账号（尤其作品少的新号）未登录态 aweme_list 直接返回空，不登录抓不到任何东西。
  if (args['wait-login']) {
    await cdp.init('https://www.douyin.com/', DEFAULT_UA);
    await cdp.sleep(2000);
    try { await cdp.send('Page.bringToFront'); } catch (e) {}
    console.log('\n>>> 请在刚打开的 Chrome 窗口里扫码登录抖音 <<<');
    console.log('    登录后脚本会自动继续（最多等 6 分钟）…');
    let ok = false;
    for (let i = 1; i <= 180; i++) {
      await cdp.sleep(2000);
      try {
        const c = await cdp.send('Network.getCookies', { urls: ['https://www.douyin.com'] });
        if ((c.cookies || []).some((x) => /^(sessionid|sessionid_ss|sid_tt)$/.test(x.name))) { ok = true; break; }
      } catch (e) {}
      if (i % 15 === 0) console.log(`    已等待 ${i * 2}s…`);
    }
    if (ok) { console.log('    ✅ 检测到登录态，继续抓取'); }
    else { console.log('    ⚠️ 等待超时，未检测到登录态，将以未登录态继续（大概率抓不到）'); }
  }

  // 用 Map 记录命中的请求
  const hits = new Map();
  cdp.on((m) => {
    if (m.method === 'Network.responseReceived') {
      const u = m.params.response.url || '';
      if (/aweme\/v1\/web\/aweme\/post/.test(u)) {
        hits.set(m.params.requestId, { url: u, done: false });
      }
    } else if (m.method === 'Network.loadingFinished') {
      const e = hits.get(m.params.requestId);
      if (e) e.done = true;
    }
  });

  const url = 'https://www.douyin.com/user/' + args.sec;
  await cdp.init(url, DEFAULT_UA);
  console.log('已跳转，等待 25s 首屏加载…');
  await cdp.sleep(25000);

  // 滚动 + 点「加载更多」触发分页
  for (let i = 0; i < scrollCount; i++) {
    await cdp.evaluate(`window.scrollTo(0, document.body.scrollHeight); 'ok'`).catch(() => {});
    await cdp.sleep(4000);
    await cdp.evaluate(`(() => {
      const els = Array.from(document.querySelectorAll('span,div,a,button'));
      els.filter(e => e.children.length === 0 && /^(加载更多|查看更多|看更多)$/.test((e.innerText||'').trim()))
         .forEach(e => e.click());
      return 'clicked';
    })()`).catch(() => {});
    await cdp.sleep(3500);
    console.log(`  滚动 ${i + 1}/${scrollCount} 完成，已捕获 ${hits.size} 个接口响应`);
  }

  // 取回响应体；失败/异常时留存诊断信息，避免「抓到 0 条但不知道为什么」
  const merged = [];
  const diagnostics = [];
  for (const [rid, e] of hits) {
    if (!e.done) { diagnostics.push({ url: e.url, err: '响应未完成 (loadingFinished 未触发)' }); continue; }
    try {
      const r = await cdp.send('Network.getResponseBody', { requestId: rid });
      const body = r.body || '';
      const j = JSON.parse(body);
      if (j.aweme_list && j.aweme_list.length) {
        merged.push(...j.aweme_list);
      } else if (j.not_login_module && j.not_login_module.guide_login_tip_exist) {
        // 精确识别登录墙：接口明说了「登录后可看更多」，不要再让用户猜原因
        diagnostics.push({ url: e.url, err: '登录墙：接口返回 not_login_module.guide_login_tip_exist=true（未登录态不给作品列表）', body: '' });
      } else {
        diagnostics.push({ url: e.url, err: `无 aweme_list（条数 ${(j.aweme_list || []).length}）`, body: body.slice(0, 300) });
      }
    } catch (err) {
      diagnostics.push({ url: e.url, err: err.message });
    }
  }
  const seen = new Set();
  const uniq = merged.filter((a) => {
    if (seen.has(a.aweme_id)) return false;
    seen.add(a.aweme_id);
    return true;
  });

  // 抓账号 profile（页面可见信息，不是接口数据）
  let profile = null;
  try {
    profile = await cdp.evaluate(`document.body.innerText.slice(0, 3000)`);
  } catch (e) {}

  fs.writeFileSync(path.join(out, 'douyin_raw.json'), JSON.stringify(uniq, null, 2), 'utf8');
  if (profile) fs.writeFileSync(path.join(out, 'douyin_profile.txt'), profile, 'utf8');

  console.log(`\n✅ 完成：接口命中 ${hits.size} 次，合并 ${merged.length} 条，去重后 ${uniq.length} 条`);
  console.log(`   原始: ${path.join(out, 'douyin_raw.json')}`);
  console.log(`   主页: ${path.join(out, 'douyin_profile.txt')}`);

  // 抓到 0 条时输出诊断，而不是静默产出空文件
  if (!uniq.length) {
    console.log('\n❌ 未抓到任何作品。诊断：');
    if (!hits.size) {
      console.log('   未捕获到任何 aweme/post 接口请求 —— 页面可能未渲染作品区（加载太慢？账号被限制？）');
    }
    diagnostics.slice(0, 3).forEach((d, i) => {
      console.log(`\n   [${i + 1}] ${d.err}`);
      console.log(`       URL: ${d.url.slice(0, 100)}`);
      if (d.body) console.log(`       BODY: ${d.body}`);
    });
    const isWall = diagnostics.some((d) => /登录墙/.test(d.err));
    if (isWall) {
      console.log('\n   👉 确定性结论：这是登录墙，不是脚本问题。');
      console.log('      解决：加上 --wait-login 参数重跑，在打开的 Chrome 里扫码登录后自动继续。');
      console.log('      （作品数少的新号几乎必然触发；大号未登录也能拿到最近 ~18 条）');
    } else {
      console.log('\n   可能原因：');
      console.log('   1) 首屏 25s 不够，页面未渲染完 —— 加大 --scroll 轮次');
      console.log('   2) 账号设置了隐私/仅粉丝可见');
      console.log('   3) 触发风控 —— 用 --wait-login 登录后重试');
      console.log('   4) 账号确实没有公开作品');
    }
  }

  // ⚠️ 覆盖度核对：未登录态抖音主页只露出前 ~18 条，其余被登录墙挡住。
  // 实测：某账号主页显示作品 85 条，未登录只抓到 18 条（21%）。
  // 不问清楚就当全量用，会得出「该号只发了 18 条」的错误结论。
  if (profile) {
    const lines = profile.split('\n').map((s) => s.trim()).filter(Boolean);
    const wi = lines.findIndex((l) => l === '作品');
    const totalWorks = wi >= 0 ? (parseInt(lines[wi + 1], 10) || 0) : 0;
    const wall = lines.some((l) => /登录后查看更多作品|登录后查看/.test(l));
    if (totalWorks > uniq.length) {
      const rate = Math.round((uniq.length / totalWorks) * 100);
      console.log(`\n⚠️ 覆盖度仅 ${uniq.length}/${totalWorks} (${rate}%) —— 这不是该账号的全部作品`);
      if (wall) console.log('   检测到登录墙。要拿全量：在刚打开的 Chrome 里扫码登录，');
      console.log('   然后重跑本脚本（--port 与 --user-data-dir 保持一致以复用会话）。');
      console.log('   若只做近期内容拆解，18 条足够；若要看长期趋势，必须先登录。');
    } else if (totalWorks > 0) {
      console.log(`\n✅ 覆盖度 ${uniq.length}/${totalWorks}，已抓全`);
    }
  }

  cdp.close();
  process.exit(0);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
