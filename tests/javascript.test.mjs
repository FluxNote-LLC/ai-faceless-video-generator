import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { apiOrigin, validate, mediaURL, waitFor, download } from '../javascript/generate.mjs';

test('unsafe URLs and invalid inputs are rejected', () => {
  for (const value of ['http://example.com', 'https://user:pass@example.com', 'https://example.com/path', 'https://example.com?key=x']) {
    assert.throws(() => apiOrigin(value));
  }
  for (const value of ['http://example.com/v.mp4', 'https://user:pass@example.com/v.mp4']) assert.throws(() => mediaURL(value));
  assert.throws(() => validate({ prompt: 'a', script: 'b' }));
});

test('completed, failed, review and bounded timeout', async () => {
  const fake = data => ({ request: async () => ({ data, retry: 0 }) });
  assert.equal((await waitFor(fake({ status: 'completed' }), 'id')).status, 'completed');
  await assert.rejects(waitFor(fake({ status: 'failed' }), 'id'), /failed/);
  await assert.rejects(waitFor(fake({ stage: 'review_ready' }), 'id'), /review/);
  await assert.rejects(waitFor(fake({ status: 'processing' }), 'id', 0.01, 0.005), /timed out/);
});

test('download follows safe redirects, never authenticates, and refuses overwrite', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'fluxnote-test-'));
  const output = join(dir, 'video.mp4');
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({ url, options });
    if (calls.length === 1) return new Response(null, { status: 302, headers: { Location: 'https://media.example.invalid/v.mp4' } });
    return new Response('fake-video');
  };
  try {
    await download('https://example.invalid/start', output, fetcher);
    assert.equal(await readFile(output, 'utf8'), 'fake-video');
    assert.ok(calls.every(c => !c.options.headers));
    await assert.rejects(download('https://example.invalid/start', output, fetcher));
    assert.deepEqual(await readdir(dir), ['video.mp4']);
    assert.equal(await readFile(output, 'utf8'), 'fake-video');
    await assert.rejects(download('https://example.invalid/start', join(dir, 'bad.mp4'), async () =>
      new Response(null, { status: 302, headers: { Location: 'http://example.invalid/insecure' } })), /HTTPS/);
  } finally { await rm(dir, { recursive: true, force: true }); }
});
