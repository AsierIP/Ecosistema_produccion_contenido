// Standalone Upro browser. No Codex desktop bridge or copied browser sessions.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const [rootArg, channelId, mode] = process.argv.slice(2);
  const root = path.resolve(rootArg);
  if (!['check', 'status', 'connect'].includes(mode) || !/^[a-z0-9-]+$/.test(channelId)) {
    throw new Error('Invalid browser operation');
  }
  const channel = JSON.parse(fs.readFileSync(path.join(root, 'channels', channelId + '.json'), 'utf8').replace(/^\uFEFF/, ''));
  const account = channel.platforms.youtube.channel_id || channel.platforms.youtube.account;
  if (!/^UC[A-Za-z0-9_-]{22}$/.test(account)) throw new Error('Missing exact YouTube channel');
  const profile = path.join(root, '.runtime', 'browser-profiles', channelId);
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
    if (mode === 'connect') {
      console.log(JSON.stringify({status: 'CONNECTION_WINDOW_OPEN', channel_id: channelId,
        instruction: 'Completa el acceso en Chrome y cierra esa ventana al terminar.'}));
      await new Promise(resolve => context.on('close', resolve));
      return;
    }
    // Auth redirects are reported, never filled, bypassed or copied from another profile.
    await Promise.race([
      page.getByRole('button', {name: /Crear|Create/, exact: true}).first().waitFor({state: 'visible', timeout: 15000}),
      page.waitForURL(url => url.hostname === 'accounts.google.com', {timeout: 15000}),
    ]).catch(() => {});
    const current = new URL(page.url());
    const identityMatch = current.hostname === 'studio.youtube.com' && current.pathname === '/channel/' + account;
    const studioControls = await page.getByRole('button', {name: /Crear|Create/, exact: true}).count();
    console.log(JSON.stringify({status: identityMatch && studioControls ? 'CHANNEL_READY' : 'AUTH_REQUIRED',
      channel_id: channelId, expected_account_id: account,
      authenticated: Boolean(identityMatch && studioControls), publication_performed: false}));
  } finally { await context.close(); }
}
main().catch(error => {
  // Do not emit browser logs, cookies, navigation queries or credentials.
  console.error(JSON.stringify({status: 'BROWSER_ERROR', error_type: error.name || 'Error'}));
  process.exitCode = 1;
});
