// Standalone Upro browser. No Codex desktop bridge or copied browser sessions.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const [rootArg, channelId, mode] = process.argv.slice(2);
  const root = path.resolve(rootArg);
  if (!['check', 'status', 'connect', 'inspect', 'inspect-upload', 'inspect-content', 'inspect-shorts'].includes(mode) || !/^[a-z0-9-]+$/.test(channelId)) {
    throw new Error('Invalid browser operation');
  }
  const channel = JSON.parse(fs.readFileSync(path.join(root, 'channels', channelId + '.json'), 'utf8').replace(/^\uFEFF/, ''));
  const account = channel.platforms.youtube.channel_id || channel.platforms.youtube.account;
  if (!/^UC[A-Za-z0-9_-]{22}$/.test(account)) throw new Error('Missing exact YouTube channel');
  const profile = path.join(root, '.runtime', 'browser-profiles', channelId);
  const report = path.join(root, '.runtime', 'upro', 'browser-connections', channelId + '.json');
  const saveStatus = status => {
    fs.mkdirSync(path.dirname(report), {recursive: true});
    const temporary = report + '.' + process.pid + '.tmp';
    fs.writeFileSync(temporary, JSON.stringify({status, channel_id: channelId,
      expected_account_id: account, observed_at: new Date().toISOString(),
      publication_performed: false}));
    fs.renameSync(temporary, report);
  };
  const context = await chromium.launchPersistentContext(profile, {
    channel: 'chrome', headless: mode !== 'connect', chromiumSandbox: true,
    locale: 'es-ES', timezoneId: 'Europe/Madrid', acceptDownloads: false,
    viewport: { width: 1280, height: 900 },
  });
  try {
    const page = context.pages()[0] || await context.newPage();
    if (mode === 'check') {
      await page.setContent('<title>Upro browser check</title><h1>Upro</h1>');
      if (await page.title() !== 'Upro browser check') throw new Error('Browser check failed');
      console.log(JSON.stringify({status: 'BROWSER_READY', channel_id: channelId,
        desktop_bridge_required: false, authenticated: null, publication_performed: false}));
      return;
    }
    await page.goto('https://studio.youtube.com/channel/' + account, {waitUntil: 'domcontentloaded', timeout: 45000});
    // Studio can show a browser compatibility notice, which is not a login failure.
    const continueToStudio = page.getByRole('link', {name: 'Cambiar a la nueva versión de Studio', exact: true});
    if (await continueToStudio.isVisible()) await continueToStudio.click();
    if (mode === 'connect') {
      saveStatus('AUTH_REQUIRED');
      console.log(JSON.stringify({status: 'CONNECTION_WINDOW_OPEN', channel_id: channelId,
        instruction: 'Completa el acceso en Chrome. Upro cerrará la ventana cuando reconozca el canal.'}));
      let closed = false;
      context.on('close', () => { closed = true; });
      while (!closed) {
        // Read only the destination and visible Studio control; never credentials.
        const ready = await Promise.all(context.pages().map(async candidate => {
          const current = new URL(candidate.url());
          return current.hostname === 'studio.youtube.com' && current.pathname === '/channel/' + account
            && await candidate.getByRole('button', {name: /^(Crear|Create)$/}).first().isVisible().catch(() => false);
        }));
        if (ready.some(Boolean)) {
          saveStatus('CHANNEL_READY');
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
      return;
    }
    // Auth redirects are reported, never filled, bypassed or copied from another profile.
    await Promise.race([
      page.getByRole('button', {name: /Crear|Create/, exact: true}).first().waitFor({state: 'visible', timeout: 15000}),
      page.waitForURL(url => url.hostname === 'accounts.google.com', {timeout: 15000}),
    ]).catch(() => {});
    const current = new URL(page.url());
    const identityMatch = current.hostname === 'studio.youtube.com' && current.pathname === '/channel/' + account;
    const studioControls = await page.getByRole('button', {name: /^(Crear|Create)$/}).first().isVisible();
    saveStatus(identityMatch && studioControls ? 'CHANNEL_READY' : 'AUTH_REQUIRED');
    if (['inspect', 'inspect-upload', 'inspect-content', 'inspect-shorts'].includes(mode) && identityMatch && studioControls) {
      if (['inspect-content', 'inspect-shorts'].includes(mode)) {
        await page.getByRole('menuitem', {name: /^(Contenido|Content)$/}).click();
        await page.waitForURL(url => url.hostname === 'studio.youtube.com'
          && url.pathname.startsWith('/channel/' + account + '/videos'), {timeout: 15000});
        await page.getByText(/^(Contenido del canal|Channel content)$/, {exact: true})
          .first().waitFor({state: 'visible', timeout: 15000});
        if (mode === 'inspect-shorts') {
          await page.getByRole('tab', {name: 'Shorts', exact: true}).click();
          await page.waitForURL(url => url.hostname === 'studio.youtube.com'
            && url.pathname.startsWith('/channel/' + account + '/videos/short'), {timeout: 15000});
          await page.waitForLoadState('networkidle', {timeout: 15000});
        }
      }
      if (mode === 'inspect-upload') {
        await page.getByRole('button', {name: 'Subir vídeos', exact: true}).click();
        await page.locator('input[type="file"]').waitFor({state: 'attached', timeout: 15000});
      }
      const controls = await page.locator('button, [role="button"], [role="tab"], a').evaluateAll(elements => elements
        .filter(e => e.getClientRects().length)
        .map(e => ({tag: e.tagName, id: e.id, role: e.getAttribute('role'),
          label: e.getAttribute('aria-label'), text: (e.innerText || '').trim().slice(0, 160),
          href: e.tagName === 'A' ? e.getAttribute('href') : undefined}))
        .filter(e => e.label || e.text).slice(0, 100));
      const fields = await page.locator('input, textarea, [contenteditable="true"]').evaluateAll(elements => elements
        .map(e => ({tag: e.tagName, id: e.id, type: e.getAttribute('type'), accept: e.getAttribute('accept'),
          label: e.getAttribute('aria-label'), editable: e.getAttribute('contenteditable')})));
      console.log(JSON.stringify({status: 'CHANNEL_READY', channel_id: channelId,
        expected_account_id: account, controls, fields,
        content_text: ['inspect-content', 'inspect-shorts'].includes(mode) ? (await page.locator('body').innerText()).slice(0, 16000) : undefined,
        scope: 'visible_page_only_not_complete_history',
        publication_performed: false}));
      return;
    }
    console.log(JSON.stringify({status: identityMatch && studioControls ? 'CHANNEL_READY' : 'AUTH_REQUIRED',
      channel_id: channelId, expected_account_id: account,
      observed_host: current.hostname, observed_path: current.pathname,
      authenticated: Boolean(identityMatch && studioControls), publication_performed: false}));
  } finally { await context.close(); }
}
main().catch(error => {
  // Do not emit browser logs, cookies, navigation queries or credentials.
  const detail = String(error.message || '').split('\n')[0].replace(/https?:\/\/\S+/g, '[url]');
  console.error(JSON.stringify({status: 'BROWSER_ERROR', error_type: error.name || 'Error', detail}));
  process.exitCode = 1;
});
