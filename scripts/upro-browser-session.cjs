// OS-owned mutex: a crashed process releases it without stale lock files.
const net = require('node:net');
const crypto = require('node:crypto');
const path = require('node:path');

function endpoint(profile) {
  const normalized = path.resolve(profile);
  const digest = crypto.createHash('sha256').update(process.platform === 'win32'
    ? normalized.toLowerCase() : normalized).digest();
  return process.platform === 'win32'
    ? {path: '\\\\.\\pipe\\upro-youtube-' + digest.toString('hex').slice(0, 32)}
    : {host: '127.0.0.1', port: 30000 + digest.readUInt32BE(0) % 25000};
}

async function acquireProfile(profile, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (true) {
    const server = net.createServer(socket => socket.destroy());
    const error = await new Promise(resolve => {
      server.once('error', resolve);
      server.listen(endpoint(profile), () => resolve(null));
    });
    if (!error) return () => new Promise((resolve, reject) => {
      server.close(error => error ? reject(error) : resolve());
    });
    if (error.code !== 'EADDRINUSE') throw error;
    if (Date.now() >= deadline) throw new Error('YouTube session busy; no browser operation started');
    await new Promise(resolve => setTimeout(resolve, Math.min(250, Math.max(1, deadline - Date.now()))));
  }
}
module.exports = {acquireProfile};
