/**
 * 一键启动带调试端口的 Chrome —— 替代 SKILL.md 里手敲的启动命令。
 *
 * 用法:
 *   node scripts/launch_chrome.js [--port 9337] [--profile ./.cdp-profile] [--no-headless-check]
 *
 * 关键约束（实测踩出来的，勿删）：
 *  - 必须用【独立】 --user-data-dir，否则会连到你正在用的浏览器，把人家的标签页搞乱
 *  - 沙箱环境可能强制 headless（UA 里带 HeadlessChrome），headless 下没有窗口，
 *    用户无法扫码登录。本脚本启动后会去读 /json/version 校验 UA，
 *    发现是 headless 就明确告警，避免用户白等。
 *  - 端口被占或 profile 损坏时，换目录名比删目录省事（删大目录常被安全策略拦）
 */
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { findChrome, defaultProfileDir } = require('./chrome_util');

function parseArgs() {
  const a = {};
  for (let i = 2; i < process.argv.length; i += 2) a[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return a;
}

const httpJson = (port, p) =>
  new Promise((res, rej) => {
    const r = http.request({ host: '127.0.0.1', port: parseInt(port, 10), path: p, method: 'GET', headers: { Host: '127.0.0.1:' + port } }, (resp) => {
      let b = ''; resp.on('data', (c) => (b += c)); resp.on('end', () => { try { res(JSON.parse(b)); } catch (e) { res(b); } });
    });
    r.on('error', rej); r.end();
  });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const args = parseArgs();
  const port = args.port || '9337';
  // ⚠️ 必须转绝对路径。实测传相对路径（./.cdp-xxx）时 Chrome 直接启动失败、
  //    端口无任何响应，且因为 stdio 被忽略而看不到任何报错，极难排查。
  const profile = path.resolve(args.profile || defaultProfileDir(process.cwd()));

  // 已在跑就别重复启动
  try {
    const v = await httpJson(port, '/json/version');
    if (v && v.Browser) {
      const headless = /Headless/i.test(v['User-Agent'] || '');
      console.log(`端口 ${port} 已有浏览器在运行：${v.Browser}`);
      console.log(headless ? '⚠️ 是 headless 模式（无窗口，无法扫码登录）' : '✅ 有头模式，可直接登录');
      process.exit(0);
    }
  } catch (e) { /* 没在跑，继续启动 */ }

  const chrome = findChrome();
  if (!chrome) {
    console.error('❌ 未找到 Chrome。请先安装 Google Chrome，或用 --profile 检查环境变量。');
    process.exit(1);
  }
  console.log(`Chrome: ${chrome}`);

  try { fs.mkdirSync(profile, { recursive: true }); } catch (e) {}
  console.log(`Profile: ${profile}`);

  const spawnArgs = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-blink-features=AutomationControlled',
    '--window-size=1280,900',
    'about:blank',
  ];

  const child = spawn(chrome, spawnArgs, { detached: true, stdio: 'ignore' });
  child.unref();
  console.log(`\n已启动，等待端口 ${port} 就绪…`);

  let ok = false;
  for (let i = 1; i <= 15; i++) {
    await sleep(1500);
    try {
      const v = await httpJson(port, '/json/version');
      if (v && v.Browser) {
        const headless = /Headless/i.test(v['User-Agent'] || '');
        console.log(`\n✅ 就绪（第 ${i} 次探测）: ${v.Browser}`);
        if (headless) {
          console.log('\n⚠️⚠️ 当前是 HEADLESS 模式 —— 没有可见窗口，你无法扫码登录。');
          console.log('   常见于沙箱/容器环境（会忽略 --headless=false 强制无头）。');
          console.log('   若需要登录：请让执行环境允许启动 GUI 进程后重试。');
          console.log('   若只抓不需登录的数据（如抖音大号），headless 也能用。');
        } else {
          console.log('   ✅ 有头模式，窗口应该已经弹出，可正常扫码登录。');
        }
        console.log(`\n后续命令记得带上 --port ${port}`);
        ok = true;
        break;
      }
    } catch (e) {}
  }
  if (!ok) {
    console.error(`\n❌ 等待超时，端口 ${port} 无响应。可能是启动被拦截，或 Chrome 路径不对。`);
    process.exit(1);
  }
  process.exit(0);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
