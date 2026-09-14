#!/usr/bin/env node
// New, standalone examples. No proprietary FluxNote implementation is bundled.
import { readFile, writeFile, link, unlink } from 'node:fs/promises';
import { createWriteStream } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { pathToFileURL } from 'node:url';
import { setTimeout as sleep } from 'node:timers/promises';

export function apiOrigin(value = 'https://api.fluxnote.io') {
  const u = new URL(value);
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(u.hostname);
  if ((u.protocol !== 'https:' && !(local && u.protocol === 'http:')) ||
      u.username || u.password || u.search || u.hash || !['/', '/v1', '/v1/'].includes(u.pathname)) {
    throw new Error('API URL must be an HTTPS origin (HTTP is allowed only for local tests).');
  }
  return u.origin;
}

export function validate(input) {
  const text = v => typeof v === 'string' && v.trim().length > 0;
  if (!input || Array.isArray(input) || typeof input !== 'object' ||
      text(input.prompt) === text(input.script) || ('prompt' in input && 'script' in input) ||
      !['template', 'voice', 'language'].every(k => text(input[k])) ||
      !Number.isInteger(input.target_duration) || input.target_duration < 1) {
    throw new Error('Input needs exactly one prompt or script, template, voice, language and a positive integer target_duration.');
  }
  return input;
}

export class Client {
  constructor(key, origin) {
    if (!key || key === 'YOUR_FLUXNOTE_API_KEY') throw new Error('Set FLUXNOTE_API_KEY first.');
    this.key = key;
    this.origin = apiOrigin(origin);
  }
  async request(method, path, body, key, timeout = 30000) {
    if (!/^\/(videos(?:\/estimate|\/[A-Za-z0-9_-]+)?|options|voices)$/.test(path)) throw new Error('Invalid API path.');
    let res;
    try {
      res = await fetch(this.origin + '/v1' + path, {
        method, redirect: 'error', signal: AbortSignal.timeout(Math.max(1, Math.ceil(timeout))),
        headers: { Authorization: `Bearer ${this.key}`, Accept: 'application/json',
          ...(body ? { 'Content-Type': 'application/json' } : {}), ...(key ? { 'Idempotency-Key': key } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new Error(method === 'POST' && path === '/videos'
        ? 'No confirmed create response. Keep the receipt; do not start another job. See recovery instructions.'
        : 'API connection failed or timed out. Check connectivity; redirects are refused.');
    }
    if (!res.ok) {
      await res.body?.cancel();
      const hints = { 401: 'Check your API key.', 403: 'Check key scopes and plan access.',
        402: 'Insufficient credits.', 409: 'Idempotency conflict; keep the existing receipt.',
        422: 'Invalid input. Check the current catalog and narration format.', 429: 'Rate limited; retry later.' };
      const retry = res.headers.get('Retry-After');
      throw new Error(`API HTTP ${res.status}. ${hints[res.status] || 'Request failed; check FluxNote before retrying a write.'}` +
        (retry && /^\d+$/.test(retry) ? ` Retry after ${retry} seconds.` : ''));
    }
    let data;
    try { data = await res.json(); } catch { throw new Error('API returned invalid JSON. Keep any existing receipt.'); }
    return { data, retry: retrySeconds(res.headers.get('Retry-After')) };
  }
}

function retrySeconds(value) {
  if (!value) return 0;
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, number) : Math.max(0, (Date.parse(value) - Date.now()) / 1000) || 0;
}
function resourceID(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]+$/.test(value)) throw new Error('Response is missing a valid video ID. Keep the receipt.');
  return value;
}
export async function waitFor(client, id, seconds = 900, interval = 5) {
  resourceID(id);
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    const { data, retry } = await client.request('GET', `/videos/${id}`, undefined, undefined, Math.min(30000, deadline - Date.now()));
    if (['failed', 'cancelled', 'canceled', 'deleted', 'uncertain'].includes(data.status)) {
      throw new Error('Video failed or stopped. Check credit settlement in FluxNote before creating another job.');
    }
    if (['review_ready', 'storyboard'].includes(data.stage)) throw new Error('Open FluxNote to review this video before continuing.');
    if (data.status === 'completed') return data;
    await sleep(Math.max(0, Math.min(Math.max(interval, retry) * 1000, deadline - Date.now())));
  }
  throw new Error('Wait timed out. The server job continues. Resume with the saved receipt.');
}

export function mediaURL(value) {
  const u = new URL(value);
  if (u.protocol !== 'https:' || u.username || u.password) throw new Error('Downloads require HTTPS without URL credentials.');
  return u;
}
export async function download(value, output, fetcher = fetch) {
  let url = mediaURL(value);
  const temp = `${output}.${randomUUID()}.part`;
  const signal = AbortSignal.timeout(15 * 60 * 1000);
  try {
    for (let n = 0; n <= 5; n++) {
      // Intentionally no Authorization header, including on redirects.
      const res = await fetcher(url, { redirect: 'manual', signal });
      if ([301, 302, 303, 307, 308].includes(res.status)) {
        await res.body?.cancel();
        if (!res.headers.get('Location') || n === 5) throw new Error('Unsafe or excessive media redirects.');
        url = mediaURL(new URL(res.headers.get('Location'), url).href);
        continue;
      }
      if (!res.ok || !res.body) throw new Error('Download failed. Resume to obtain a fresh media URL.');
      await pipeline(Readable.fromWeb(res.body), createWriteStream(temp, { flags: 'wx', mode: 0o600 }), { signal });
      await link(temp, output); // Atomic no-overwrite, including symlinks.
      return;
    }
  } finally { await unlink(temp).catch(() => {}); }
}

export async function main(args = process.argv.slice(2)) {
  const [command, file, ...flags] = args;
  if (!['catalog', 'estimate', 'create', 'resume'].includes(command)) {
    console.log('Usage: node javascript/generate.mjs catalog | estimate INPUT.json | create INPUT.json --confirm | resume JOB.receipt.json');
    return;
  }
  if ((command === 'catalog' && (file || flags.length)) ||
      (command !== 'catalog' && (!file || flags.some(f => f !== '--confirm') || (flags.length && command !== 'create')))) {
    throw new Error('Invalid arguments. Run without arguments for usage.');
  }
  const client = new Client(process.env.FLUXNOTE_API_KEY, process.env.FLUXNOTE_API_URL);
  if (command === 'catalog') {
    for (const path of ['/options', '/voices']) console.log(JSON.stringify((await client.request('GET', path)).data, null, 2));
    return;
  }
  const content = JSON.parse(await readFile(file, 'utf8'));
  if (command === 'resume') {
    if (content.origin !== client.origin) throw new Error('Receipt belongs to a different API origin.');
    if (!content.id) throw new Error('Receipt has an uncertain submission. Check FluxNote; see docs/recovery.md. No write was sent.');
    const result = await waitFor(client, resourceID(content.id));
    await download(result.media_url, `${content.id}.mp4`);
    console.log(`Saved ${content.id}.mp4`);
    return;
  }
  const input = validate(content);
  const estimate = (await client.request('POST', '/videos/estimate', input)).data;
  console.log('Current estimate:', JSON.stringify(estimate, null, 2));
  if (command === 'estimate' || !flags.includes('--confirm')) {
    console.log('No video created. Review the estimate, then use create INPUT.json --confirm to spend credits.');
    return;
  }
  const key = randomUUID();
  const receiptPath = `${key}.receipt.json`;
  const receipt = { origin: client.origin, idempotency_key: key, input, created_at: new Date().toISOString() };
  await writeFile(receiptPath, JSON.stringify(receipt, null, 2), { flag: 'wx', mode: 0o600 });
  console.log(`Keep this private receipt: ${receiptPath}`);
  const created = (await client.request('POST', '/videos', input, key, 120000)).data;
  receipt.id = resourceID(created.id || created.video_id);
  // The initial receipt survives a crash during the response update.
  const updated = `${receiptPath}.part`;
  await writeFile(updated, JSON.stringify(receipt, null, 2), { flag: 'wx', mode: 0o600 });
  const { rename } = await import('node:fs/promises');
  await rename(updated, receiptPath);
  console.log(`Video: ${receipt.id}. Resume with: node javascript/generate.mjs resume ${receiptPath}`);
  const result = await waitFor(client, receipt.id);
  await download(result.media_url, `${receipt.id}.mp4`);
  console.log(`Saved ${receipt.id}.mp4`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => {
    // Do not print raw API bodies, request objects, signed URLs, or keys.
    const key = process.env.FLUXNOTE_API_KEY;
    console.error(key ? String(error.message).split(key).join('[redacted]') : error.message);
    process.exitCode = 1;
  });
}
