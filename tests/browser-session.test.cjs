const {test} = require('node:test');
const assert = require('node:assert/strict');
const {acquireProfile} = require('../scripts/upro-browser-session.cjs');

test('shared sessions serialize and the next operation can acquire after release', async () => {
  const profile = 'upro-mutex-test-' + process.pid;
  const release = await acquireProfile(profile);
  try {
    await assert.rejects(acquireProfile(profile, 30), /session busy/);
    const other = await acquireProfile(profile + '-other', 30);
    await other();
  } finally { await release(); }
  const next = await acquireProfile(profile, 30);
  await next();
});
