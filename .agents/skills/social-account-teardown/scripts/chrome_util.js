/**
 * 跨平台 Chrome 定位 —— 上架后用户可能用 Win / macOS / Linux，不能硬编码路径。
 *
 * 只做两件事：找到本机 Chrome，以及按跨平台安全的方式拼启动参数。
 * 不负责判断是否 headless（那是 login_helper.js 的职责）。
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function candidates() {
  const p = process.platform;
  const list = [];
  if (p === 'win32') {
    const pf = process.env['ProgramFiles'] || 'C:\\Program Files';
    const pf86 = process.env['ProgramFiles(x86)'] || '';
    const lad = process.env.LOCALAPPDATA || '';
    list.push(
      path.join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      path.join(pf86, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      path.join(lad, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      // Edge 兜底：CDP 协议完全兼容
      path.join(pf, 'Microsoft', 'Edge', 'Application', 'msedge.exe')
    );
  } else if (p === 'darwin') {
    list.push(
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Chromium.app/Contents/MacOS/Chromium',
      path.join(process.env.HOME || '', 'Applications', 'Google Chrome.app', 'Contents', 'MacOS', 'Google Chrome')
    );
  } else {
    list.push(
      '/usr/bin/google-chrome',
      '/usr/bin/google-chrome-stable',
      '/usr/bin/chromium',
      '/usr/bin/chromium-browser',
      '/snap/bin/chromium'
    );
  }
  return list.filter(Boolean);
}

/** 返回本机 Chrome 绝对路径，找不到返回 null */
function findChrome() {
  for (const c of candidates()) {
    try { if (fs.existsSync(c)) return c; } catch (e) {}
  }
  if (process.platform !== 'win32') {
    for (const bin of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']) {
      try {
        const r = execSync(`command -v ${bin} 2>/dev/null || true`, { encoding: 'utf8' }).trim();
        if (r && fs.existsSync(r)) return r;
      } catch (e) {}
    }
  }
  return null;
}

/** 默认 user-data-dir，跟随 skill 使用，跨平台都能写 */
function defaultProfileDir(baseDir) {
  return path.join(baseDir || process.cwd(), '.cdp-profile');
}

module.exports = { findChrome, candidates, defaultProfileDir };
