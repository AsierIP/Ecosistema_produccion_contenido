// Anonymous public verification: no login, model calls, upload or schedule changes.
const fs = require('node:fs');
const { chromium } = require('playwright');

async function main() {
  const request = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  if (!/^[A-Za-z0-9_-]{11}$/.test(request.video_id) ||
      !/^UC[A-Za-z0-9_-]{22}$/.test(request.account_id) ||
      !/^@[a-zA-Z0-9._-]+$/.test(request.handle)) throw new Error('Invalid identity');
  if (!Number.isFinite(Date.parse(request.publishAt)) || Date.now() < Date.parse(request.publishAt)) throw new Error('Verification is not due');
  const browser = await chromium.launch({channel: 'chrome', headless: true, chromiumSandbox: true});
  const page = await browser.newPage({locale: 'es-ES'});
  try {
    const url = 'https://www.youtube.com/shorts/' + request.video_id;
    await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 45000});
    const rejectCookies = page.getByRole('button', {name: /^(Rechazar todo|Reject all)$/});
    await rejectCookies.waitFor({state: 'visible', timeout: 5000}).catch(() => {});
    if (await rejectCookies.isVisible()) await rejectCookies.click();
    const author = page.locator(`a[href="/${request.handle}"]:visible,a[href="/${request.handle}/shorts"]:visible,a[href="/channel/${request.account_id}"]:visible`).first();
    await author.waitFor({state: 'visible', timeout: 30000});
    const video = page.locator('video:visible').first();
    await video.waitFor({state: 'visible', timeout: 15000});
    // Decode readiness in an anonymous context proves more than a loaded shell.
    await page.waitForFunction(() => {
      const v = [...document.querySelectorAll('video')].find(v => v.getClientRects().length && getComputedStyle(v).visibility !== 'hidden');
      return v && v.readyState >= 2 && v.videoWidth > 0 && Number.isFinite(v.duration) && v.duration > 0;
    }, null, {timeout: 30000});
    const observed = new URL(page.url());
    if (observed.hostname !== 'www.youtube.com' || observed.pathname !== '/shorts/' + request.video_id) {
      throw new Error('Public URL changed');
    }
    console.log(JSON.stringify({master_sha256: request.master_sha256, account_id: request.account_id,
      url, public_verified: true, evidence: {
        method: 'anonymous-browser-playable-video', observed_channel_href: await author.getAttribute('href'),
        verified_at: new Date().toISOString(),
        master_binding: 'Exact video id from the verified private upload; YouTube transcodes the uploaded master.'
      }}));
  } catch (error) {
    if (request.diagnostic === true) {
      console.error(error.message);
      console.error(JSON.stringify(await page.locator('video').evaluateAll(nodes => nodes.map(v => ({readyState:v.readyState,width:v.videoWidth,duration:v.duration,paused:v.paused,error:v.error?.code})))));
      console.error((await page.locator('body').innerText()).slice(0,1800));
    }
    throw error;
  } finally { await browser.close(); }
}
main().catch(error => {
  console.error(JSON.stringify({status: 'PUBLIC_CHECK_UNRESOLVED', error_type: error.name || 'Error'}));
  process.exitCode = 1;
});
