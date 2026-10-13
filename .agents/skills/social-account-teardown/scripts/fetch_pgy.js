/**
 * 小红书蒲公英 (pgy.xiaohongshu.com) 后台数据抓取
 *
 * 验证状态：2026-09-05 实测 —— xiao 账号下不可用，标记为受限平台。
 *
 * 四个已探明的硬约束（实测踩出来的，**不要试图绕过**）：
 *
 * 1. 【账号身份强校验】蒲公英的 `/api/solar/*` 端点全部按调用方身份做权限路由，
 *    错误路径返回 `"url not support"` 而不是 404 —— 这是设计上的"假装不存在"。
 *    实测：以 blockBlogger=true 的 cookie 调用 `/api/solar/kol/detail/{uid}`，返回
 *    `{"code":-11000000,"msg":"get ... url not support","success":false}`。
 *
 * 2. 【公开 URL 不存在】蒲公英是纯 SPA，所有路由（含 SEO 期望的
 *    `/creator/public/{uid}`、`/kol/info?userId={uid}`、`/creator-square`）
 *    都返回相同的 React shell html 且落地后显示"页面不见"。蒲公英没有公开数据接口。
 *
 * 3. 【博主权限被封】xiao 当前登录账号（隐形婴儿/InvisBaby）profile 显示
 *    `role="kol"` 但服务端返回 `blockBlogger: true, access: ["buyer"]`，
 *    `roleInfoList[0].status: 20` 表示博主申请未通过。所有 `/creator/*` 路由
 *    在前端就跳到"页面不见"。
 *
 * 4. 【数据按调用者隔离】即使 xiao 申请成为品牌方账号，蒲公英的 API
 *    仍按品牌方身份鉴权 —— 能看到"达人广场"的卡片，但卡片数据是公开层级的，
 *    拿不到 EVI/卡兹克 后台 30 天互动率、商单报价、粉丝画像等私有数据。
 *    想拿到这些，需要 EVI/卡兹克 各自的 cookie（即对方授权），不可能。
 *
 * 用法（**当前为受限模式**）:
 *   node scripts/fetch_pgy.js --url "https://pgy.xiaohongshu.com/creator/home" --port 9337 --out workdir/
 *
 * 输出（受限模式）:
 *   workdir/pgy_access.json  —— 当前账号身份与可用权限诊断
 *
 * 替代方案（推荐）:
 *   - 数据已在公开层：用 scripts/fetch_xhs.js + scripts/fetch_xhs_detail.js 抓
 *     www.xiaohongshu.com 个人主页，能拿到粉丝/获赞/全部笔记列表/每条笔记赞藏评。
 *     这是 EVI/卡兹克 在不登录对方账号的情况下能拿到的最全数据。
 *   - 需要报价/商单/粉丝画像：必须用第三方付费工具（新榜、千瓜、灰豚），
 *     或拿到对应账号本人的蒲公英 cookie —— 都不在 skill 覆盖范围。
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
  if (!args.url) { console.error('缺少 --url (蒲公英入口 URL)'); process.exit(1); }
  const out = args.out || '.';
  fs.mkdirSync(out, { recursive: true });

  const cdp = new CDP(args.port || '9337');
  const curUrl = await cdp.connect();
  console.error('[已连接 page]', curUrl);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Network.enable', {
    maxResourceBufferSize: 80000000,
    maxTotalBufferSize: 400000000,
  });
  await cdp.send('Network.setUserAgentOverride', { userAgent: DEFAULT_UA });
  await cdp.send('Page.navigate', { url: args.url });
  await cdp.sleep(4000);

  // Probe 1: /api/solar/user/info (唯一任何身份都能调通的接口)
  const probeInfo = await cdp.evaluate(`fetch("/api/solar/user/info",{credentials:"include"}).then(r=>r.json()).then(j=>JSON.stringify(j)).catch(e=>"ERR:"+e)`);
  let parsed = {};
  try { parsed = JSON.parse(probeInfo || '{}'); } catch {}

  // Probe 2: 真正导航看 /creator/home 是否能进入
  const routeChecks = ['/creator/home', '/creator/notes', '/brand/home', '/agent/home'];
  const routeResults = {};
  for (const r of routeChecks) {
    await cdp.send('Page.navigate', { url: 'https://pgy.xiaohongshu.com' + r });
    await cdp.sleep(2500);
    const txt = await cdp.evaluate('document.title + " | " + (document.body.innerText || "").slice(0, 120)');
    routeResults[r] = txt;
  }

  const isPageBlocked = (txt) => /页面不见|403|not.*allowed/.test(String(txt || ''));
  const allBlocked = Object.values(routeResults).every(isPageBlocked);

  // Diagnostic
  const diag = {
    platform: 'pgy.xiaohongshu.com',
    probe_time: new Date().toISOString(),
    url: args.url,
    user: parsed.data ? {
      userId: parsed.data.userId,
      nickname: parsed.data.nickName,
      redId: parsed.data.redId,
      role: parsed.data.role,
      access: parsed.data.access,
      blockBlogger: parsed.data.blockBlogger,
      hasBuyerAuth: parsed.data.hasBuyerAuth,
      permissions: parsed.data.permissions,
      professionalAccount: parsed.data.certification && parsed.data.certification.professionalAccount,
      roleStatus: parsed.data.roleInfoList && parsed.data.roleInfoList[0] && parsed.data.roleInfoList[0].status,
      sellerType: parsed.data.sellerType,
      accountType: parsed.data.accountType,
    } : null,
    routeAccess: routeResults,
    verdict: '',
    recommendation: '',
  };

  // Decide verdict
  const u = diag.user;
  if (!u) {
    diag.verdict = 'NOT_LOGGED_IN';
    diag.recommendation = '未登录蒲公英 cookie —— 先用 login_helper.js 登录。';
  } else if (allBlocked) {
    diag.verdict = 'NO_ROLE_GRANTED';
    diag.recommendation = '当前账号在蒲公英没有可用身份（所有 creator/brand/agent 路由都落到"页面不见"）。' +
      '蒲公英后台数据这条路在当前账号下不可行。请改用 fetch_xhs.js + fetch_xhs_detail.js 抓公开主页。';
  } else if (u.blockBlogger) {
    diag.verdict = 'BLOCKED_BLOGGER';
    diag.recommendation = '账号 blockBlogger=true（博主申请未通过 / 被封）。即使部分路由可访问，也拿不到 EVI/卡兹克 的后台数据。';
  } else if (u.permissions && u.permissions.includes('Home')) {
    diag.verdict = 'KOL_OK';
    diag.recommendation = '账号有 creator 权限 —— 但只能看自己账号的后台数据，看不到 EVI/卡兹克。' +
      '如果目标就是自己账号的数据，请把 --url 改为 https://pgy.xiaohongshu.com/creator/home 并扩大本脚本。';
  } else {
    diag.verdict = 'UNKNOWN';
    diag.recommendation = '未识别身份 —— 把 diag 输出附在 issue 里。';
  }

  fs.writeFileSync(path.join(out, 'pgy_access.json'), JSON.stringify(diag, null, 2));

  console.log('\n========== 蒲公英抓取诊断 ==========');
  console.log('账号:', u ? `${u.nickname} (${u.userId})` : '(未登录)');
  if (u) {
    console.log('角色:', u.role, '| access:', u.access.join(','));
    console.log('权限:', u.permissions.join(','));
    console.log('blockBlogger:', u.blockBlogger, '| 博主申请 status:', u.roleStatus);
  }
  console.log('\n路由访问状态:');
  for (const [r, s] of Object.entries(routeResults)) console.log('  ' + r + ' -> ' + s);
  console.log('\n结论: ' + diag.verdict);
  console.log(diag.recommendation);
  console.log('\n详细诊断已写入 ' + path.join(out, 'pgy_access.json'));

  await cdp.close();
  process.exit(diag.verdict === 'KOL_OK' ? 0 : 2);
})().catch(e => { console.error(e); process.exit(1); });