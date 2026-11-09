import assert from 'node:assert/strict';
import { once } from 'node:events';
import { existsSync } from 'node:fs';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const frontendDir = fileURLToPath(new URL('../', import.meta.url));
const entry = fileURLToPath(new URL('../dist/server/entry.mjs', import.meta.url));
const ids = [
  '11111111-1111-4111-8111-111111111111',
  '22222222-2222-4222-8222-222222222222',
  '33333333-3333-4333-8333-333333333333',
  '44444444-4444-4444-8444-444444444444',
];
const episodeId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

// Production SSR 응답만 확인한다. 브라우저·쿠키 저장소·hydration은 실행하지 않는다.
test('뷰어 SSR의 공개 캐시·메타 없는 진입 셸·장애 구분', { timeout: 20_000 }, async (t) => {
  assert.ok(existsSync(entry), '먼저 pnpm --filter frontend build를 실행하세요.');
  const requests = [];
  const api = createServer((req, res) => {
    requests.push({ url: req.url, cookie: req.headers.cookie });
    res.setHeader('Content-Type', 'application/json');
    if (req.url === `/works/${ids[1]}`) {
      res.writeHead(404).end(JSON.stringify({ detail: 'PRIVATE_METADATA_MUST_NOT_LEAK' }));
    } else if (req.url === `/works/${ids[3]}`) {
      res.writeHead(503).end('{}');
    } else if ([`/works/${ids[0]}`, `/works/${ids[2]}`].includes(req.url)) {
      const workId = req.url.split('/').at(-1);
      res.end(JSON.stringify({
        id: workId,
        title: workId === ids[2] ? 'OTHER_PUBLIC_WORK' : 'PUBLIC_WORK',
        episodes: [{
          id: episodeId,
          public_id: workId === ids[2] ? 10000002 : 10000001,
          title: 'PUBLIC_EPISODE',
          subtitle: null,
          is_free: true,
        }],
      }));
    } else {
      res.writeHead(500).end('{}');
    }
  });
  let site;
  try {
    api.listen(0, '127.0.0.1');
    await once(api, 'listening');
    site = spawn(process.execPath, [entry], {
      cwd: frontendDir,
      env: {
        ...process.env,
        HOST: '127.0.0.1',
        PORT: '0',
        API_INTERNAL_URL: `http://127.0.0.1:${api.address().port}`,
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let output = '';
    const siteUrl = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`SSR 기동 시간 초과: ${output}`)), 10_000);
      site.once('error', (error) => { clearTimeout(timer); reject(error); });
      site.once('exit', (code) => {
        clearTimeout(timer);
        reject(new Error(`SSR이 종료됐습니다 (${code}): ${output}`));
      });
      const inspect = (chunk) => {
        output += chunk;
        const match = output.match(/Server listening on (http:\/\/127\.0\.0\.1:\d+)/);
        if (match) { clearTimeout(timer); resolve(match[1]); }
      };
      site.stdout.on('data', inspect);
      site.stderr.on('data', inspect);
    });

    async function read(index, publicId = '10000001') {
      const response = await fetch(`${siteUrl}/works/${ids[index]}/${publicId}`, {
        headers: { Cookie: 'login_hint=reader; access_token=FAKE_BROWSER_COOKIE' },
      });
      const html = await response.text();
      assert.ok(!html.includes('FAKE_BROWSER_COOKIE'));
      assert.ok(!html.includes('PRIVATE_METADATA_MUST_NOT_LEAK'));
      return { response, html };
    }

    await t.test('공개 회차는 기존 SSR 메타와 60초 공유 캐시를 유지한다', async () => {
      const { response, html } = await read(0);
      assert.equal(response.status, 200);
      assert.equal(response.headers.get('cache-control'), 'public, max-age=60');
      assert.ok(html.includes('PUBLIC_EPISODE'));
      assert.ok(html.includes(episodeId));
      assert.ok(!html.includes('ViewerEntry'));
    });

    for (const index of [1, 2]) {
      await t.test(index === 1 ? '비공개 작품 경로의 HTML은 메타 없는 셸이다' : '공개 목록에 없는 회차도 메타 없는 셸이다', async () => {
        const { response, html } = await read(index);
        assert.equal(response.status, 200);
        assert.equal(response.headers.get('cache-control'), 'no-store');
        assert.ok(html.includes('ViewerEntry'));
        assert.ok(!html.includes('OTHER_PUBLIC_WORK'));
        assert.ok(!html.includes('PUBLIC_EPISODE'));
        assert.ok(!html.includes(episodeId));
      });
    }

    await t.test('카탈로그 503은 404나 구매 fallback으로 바뀌지 않는다', async () => {
      const { response, html } = await read(3);
      assert.equal(response.status, 503);
      assert.equal(response.headers.get('cache-control'), 'no-store');
      assert.ok(html.includes('일시적인 오류'));
      assert.ok(!html.includes('ViewerEntry'));
    });

    await t.test('무효 회차 URL은 API 조회 없이 404/no-store다', async () => {
      const { response } = await read(0, '1e7');
      assert.equal(response.status, 404);
      assert.equal(response.headers.get('cache-control'), 'no-store');
    });

    assert.equal(requests.length, 4);
    assert.ok(requests.every((req) => !req.cookie));
    assert.ok(requests.every((req) => /^\/works\/[^/]+$/.test(req.url)));
  } finally {
    if (site && site.exitCode === null && site.signalCode === null) {
      const exit = once(site, 'exit');
      site.kill('SIGTERM');
      await exit;
    }
    if (api.listening) await new Promise((resolve, reject) => api.close((error) => error ? reject(error) : resolve()));
  }
});
