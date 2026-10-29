import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const argumentsList = process.argv.slice(2);
const baseIndex = argumentsList.indexOf('--base-url');
if (baseIndex === -1 || !argumentsList[baseIndex + 1]) throw new Error('--base-url is required');
const base = argumentsList[baseIndex + 1];
const output = resolve('.artifacts/browser');
await mkdir(output, { recursive: true });
const profile = await mkdtemp(join(tmpdir(), 'zore-website-browser-'));
const candidates = process.platform === 'win32'
  ? ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe']
  : process.platform === 'darwin'
    ? ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    : ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
const executable = process.env.BROWSER_PATH || candidates.find(existsSync);
if (!executable) throw new Error('Chrome or Chromium is required; set BROWSER_PATH');
const browser = spawn(executable, ['--headless', '--disable-gpu', '--disable-background-networking', '--hide-scrollbars', '--no-sandbox', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore', windowsHide: true });
let socket;
let sequence = 0;
const pending = new Map();
const failures = [];
const evidence = [];

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}

function call(method, params = {}) {
  return new Promise((accept, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(() => reject(new Error(`Browser timed out: ${method}`)), 15000);
    pending.set(id, { accept, reject, timeout });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const value = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (value.exceptionDetails) throw new Error(JSON.stringify(value.exceptionDetails));
  return value.result.value;
}

async function navigate(route) {
  const url = new URL(route, base).href;
  const result = await call('Page.navigate', { url });
  requireValue(!result.errorText, `${url}: ${result.errorText}`);
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (await evaluate(`location.href === ${JSON.stringify(url)} && document.readyState === 'complete'`)) {
      await evaluate('Promise.all([document.fonts.ready,...[...document.images].map(image=>image.decode())]).then(()=>true)');
      return;
    }
    await new Promise(accept => setTimeout(accept, 50));
  }
  throw new Error(`Page did not finish loading: ${url}`);
}

async function capture(name) {
  const data = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  await writeFile(join(output, name + '.png'), Buffer.from(data.data, 'base64'));
}

try {
  let port;
  for (let attempt = 0; attempt < 200; attempt += 1) {
    try {
      port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]);
      break;
    } catch {
      await new Promise(accept => setTimeout(accept, 100));
    }
  }
  requireValue(port, 'Browser did not expose its debugging port');
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((accept, reject) => {
    socket.addEventListener('open', accept, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  socket.addEventListener('message', event => {
    const response = JSON.parse(event.data);
    const request = pending.get(response.id);
    if (request) {
      clearTimeout(request.timeout);
      pending.delete(response.id);
      if (response.error) request.reject(new Error(JSON.stringify(response.error)));
      else request.accept(response.result);
    } else if (response.method === 'Runtime.exceptionThrown') {
      failures.push(JSON.stringify(response.params.exceptionDetails));
    } else if (response.method === 'Log.entryAdded' && response.params.entry.level === 'error') {
      failures.push(response.params.entry.text);
    }
  });
  await call('Page.enable');
  await call('Runtime.enable');
  await call('Log.enable');
  await call('Page.addScriptToEvaluateOnNewDocument', { source: "Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.previewCopied=text}}})" });
  const routes = ['/', '/docs', '/docs/install', '/docs/first-program', '/docs/language', '/docs/tools', '/docs/status'];
  for (const width of [1440, 1024, 768, 375, 320]) {
    await call('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width < 500 });
    for (const route of routes) {
      await navigate(route);
      const data = await evaluate(`JSON.stringify({route:location.pathname,width:innerWidth,pageWidth:document.documentElement.scrollWidth,headings:document.querySelectorAll('h1').length,missingAlt:[...document.images].filter(image=>!image.hasAttribute('alt')).length,canonical:document.querySelector('link[rel=canonical]').href})`);
      const layout = JSON.parse(data);
      requireValue(layout.pageWidth <= width && layout.headings === 1 && layout.missingAlt === 0, `Layout failed: ${data}`);
      requireValue(layout.canonical === 'https://zore.dev' + route, `Canonical differs: ${data}`);
      evidence.push(layout);
      if (width === 1440 || width === 375) await capture((route === '/' ? 'home' : route.slice(1).replaceAll('/', '-')) + '-' + width);
      if (width < 500) {
        await evaluate("document.querySelector('.mobile-nav summary').click()");
        requireValue(await evaluate("document.querySelector('.mobile-nav').open && [...document.querySelectorAll('.mobile-nav a')].filter(e=>e.checkVisibility()).every(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth})"), `Mobile navigation failed: ${route} ${width}`);
        const docsMenu = await evaluate("Boolean(document.querySelector('.docs-mobile-nav'))");
        if (docsMenu) {
          await evaluate("document.querySelector('.mobile-nav summary').click();document.querySelector('.docs-mobile-nav summary').click()");
          requireValue(await evaluate('document.documentElement.scrollWidth<=innerWidth'), `Docs menu overflow: ${route}`);
        }
      }
      if (await evaluate("Boolean(document.querySelector('[data-copy-target]'))")) {
        requireValue(await evaluate("(async()=>{const button=document.querySelector('[data-copy-target]');button.click();await new Promise(resolve=>setTimeout(resolve,10));return window.previewCopied===document.getElementById(button.dataset.copyTarget).textContent})()"), `Copy control failed: ${route}`);
      }
    }
  }
  await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
  await navigate('/');
  await call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  await call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  requireValue(await evaluate("document.activeElement.classList.contains('skip-link')"), 'Keyboard skip link was not first');
  await call('Emulation.setDeviceMetricsOverride', { width: 720, height: 550, deviceScaleFactor: 2, mobile: false });
  await navigate('/');
  requireValue(await evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Page overflow in the 200% equivalent viewport');
  await capture('home-zoom-200');
  await call('Emulation.setScriptExecutionDisabled', { value: true });
  await navigate('/docs/install');
  requireValue(await evaluate("document.querySelector('h1').textContent.includes('Install') && [...document.querySelectorAll('.docs-sidebar a')].some(link=>link.href.endsWith('/docs/first-program'))"), 'Documentation is not usable without scripts');
  requireValue(failures.length === 0, `Browser errors: ${failures.join('\n')}`);
  await writeFile(join(output, 'checks.json'), JSON.stringify({ layouts: evidence, keyboard: 'skip link first', zoom: { cssWidth: 720, deviceScaleFactor: 2, model: '200% equivalent viewport' }, noScript: true, clipboard: 'stubbed; source matches', errors: failures }, null, 2) + '\n');
  console.log(`Passed browser checks: ${evidence.length} layouts, mobile menus, clipboard, keyboard, zoom and no-script docs`);
  await call('Browser.close');
} finally {
  socket?.close();
  for (const request of pending.values()) clearTimeout(request.timeout);
  browser.kill();
}
