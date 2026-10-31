/**
 * 通用 CDP 客户端 —— 零第三方依赖，Node 18+ 自带 WebSocket。
 *
 * 关键实现约束（踩过的坑，勿改）：
 *  - Node 22 的 WebSocket 必须用 addEventListener，.on() 不触发
 *  - HTTP /json/list 请求必须显式带 Host: 127.0.0.1:<port>，否则 Chrome 拒绝
 *  - Network.enable 的 buffer 要放大，否则大响应体 getResponseBody 取不到
 */
const http = require('http');

class CDP {
  constructor(port = 9335) {
    this.port = String(port);
    this.id = 0;
    this.pending = new Map();
    this.listeners = [];
  }

  _http(pathname, method = 'GET') {
    return new Promise((resolve, reject) => {
      const r = http.request(
        { host: '127.0.0.1', port: parseInt(this.port, 10), path: pathname, method,
          headers: { Host: '127.0.0.1:' + this.port } },
        (res) => {
          let b = '';
          res.on('data', (c) => (b += c));
          res.on('end', () => { try { resolve(JSON.parse(b)); } catch (e) { resolve(b); } });
        }
      );
      r.on('error', reject);
      r.end();
    });
  }

  /** 连接浏览器里第一个 page 类型的 target */
  async connect() {
    const targets = await this._http('/json/list');
    const page = Array.isArray(targets) && targets.find((t) => t.type === 'page');
    if (!page) throw new Error('未找到 page target。Chrome 是否已带 --remote-debugging-port 启动？');

    const ws = new WebSocket(page.webSocketDebuggerUrl);
    this.ws = ws;

    ws.addEventListener('message', (ev) => {
      const m = JSON.parse(ev.data.toString());
      if (m.id && this.pending.has(m.id)) {
        const { res, rej } = this.pending.get(m.id);
        this.pending.delete(m.id);
        m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
      } else if (m.method) {
        this.listeners.forEach((fn) => fn(m));
      }
    });

    await new Promise((res, rej) => {
      ws.addEventListener('open', res, { once: true });
      ws.addEventListener('error', rej, { once: true });
    });
    return page.url;
  }

  /** 发送 CDP 命令，60s 超时 */
  send(method, params = {}) {
    return new Promise((res, rej) => {
      const i = ++this.id;
      this.pending.set(i, { res, rej });
      this.ws.send(JSON.stringify({ id: i, method, params }));
      setTimeout(() => {
        if (this.pending.has(i)) { this.pending.delete(i); rej(new Error('timeout:' + method)); }
      }, 60000);
    });
  }

  /** 在页面上下文执行表达式，awaitPromise: true 支持 async IIFE */
  async evaluate(expr) {
    const r = await this.send('Runtime.evaluate', {
      expression: expr, returnByValue: true, awaitPromise: true,
    });
    if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400));
    return r.result && r.result.value;
  }

  /** 标准初始化：启用 Page/Runtime/Network，伪装 UA，跳转 */
  async init(url, ua) {
    await this.send('Page.enable');
    await this.send('Runtime.enable');
    await this.send('Network.enable', {
      maxResourceBufferSize: 80000000,
      maxTotalBufferSize: 400000000,
    });
    if (ua) await this.send('Network.setUserAgentOverride', { userAgent: ua });
    await this.send('Page.navigate', { url });
  }

  /** 注册事件监听器，返回取消函数 */
  on(fn) { this.listeners.push(fn); }

  sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

  close() { if (this.ws) { try { this.ws.close(); } catch (e) {} } }
}

const DEFAULT_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36';

module.exports = { CDP, DEFAULT_UA };
