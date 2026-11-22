import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { existsSync } from 'node:fs';
import { mkdir, rmdir, stat, unlink, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { JSDOM } from 'jsdom';

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
  let publicPrice = 500;
  const api = createServer((req, res) => {
    requests.push({ url: req.url, cookie: req.headers.cookie });
    res.setHeader('Content-Type', 'application/json');
    if (req.url === '/tags') {
      res.end(JSON.stringify([{ id: 'tag', name: '테스트 태그', work_count: 72 }]));
    } else if (req.url.startsWith('/works?')) {
      const query = new URL(req.url, 'http://localhost').searchParams;
      res.end(JSON.stringify({
        items: [{ id: ids[0], title: 'PUBLIC_WORK', cover_image_url: null, status: 'ongoing', tags: [], episode_count: 1 }],
        total: 72, page: Number(query.get('page')), size: 24,
      }));
    } else if (req.url === '/commission-items') {
      res.end(JSON.stringify([{
        id: 'commission', title: '작업 예시', description: null, price_text: '가격 문의',
        duration_text: null, sample_image_urls: [], is_open: false,
      }]));
    } else if (req.url === '/site-texts/commission_notes') {
      res.end(JSON.stringify({ key: 'commission_notes', body: '작업 전 확인', updated_at: null }));
    } else if (req.url === '/auth/refresh') {
      res.writeHead(401).end('{}');
    } else if (req.url === '/auth/me') {
      if (req.headers.cookie?.includes('access_token=VALID_ACCOUNT')) {
        res.end(JSON.stringify({
          id: 'private-reader', nickname: 'PRIVATE_ACCOUNT', email: 'private@example.com',
          profile_image: null, role: 'reader', has_password: true, is_email_verified: true,
          created_at: '2026-11-16T00:00:00Z',
        }));
      } else if (req.headers.cookie?.includes('access_token=TEMP_ERROR')) {
        res.writeHead(503).end('{}');
      } else {
        res.writeHead(401).end('{}');
      }
    } else if (req.url === `/works/${ids[1]}`) {
      res.writeHead(404).end(JSON.stringify({ detail: 'PRIVATE_METADATA_MUST_NOT_LEAK' }));
    } else if (req.url === `/works/${ids[3]}`) {
      res.writeHead(503).end('{}');
    } else if ([`/works/${ids[0]}`, `/works/${ids[2]}`].includes(req.url)) {
      const workId = req.url.split('/').at(-1);
      const price = workId === ids[0] ? publicPrice : 500;
      res.end(JSON.stringify({
        id: workId,
        title: workId === ids[2] ? 'OTHER_PUBLIC_WORK' : 'PUBLIC_WORK',
        synopsis: null,
        cover_image_url: null,
        episode_base_price: 500,
        status: 'ongoing',
        tags: [],
        episodes: [{
          id: episodeId,
          public_id: workId === ids[2] ? 10000002 : 10000001,
          title: 'PUBLIC_EPISODE',
          subtitle: null,
          is_free: price === null,
          is_locked: true,
          price,
          thumbnail_url: null,
          first_published_at: '2026-11-01T00:00:00Z',
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

    await t.test('/_image는 대소문자만 다른 정적 디렉터리로 벗어나지 않는다', async () => {
      const clientDir = fileURLToPath(new URL('../dist/client/', import.meta.url));
      const privateDir = fileURLToPath(new URL('../dist/CLIENT/', import.meta.url));
      const filename = `${randomUUID()}.svg`;
      const publicPath = fileURLToPath(new URL(`../dist/client/${filename}`, import.meta.url));
      const privatePath = fileURLToPath(new URL(`../dist/CLIENT/${filename}`, import.meta.url));
      const publicSentinel = `PUBLIC_IMAGE_${randomUUID()}`;
      const privateSentinel = `PRIVATE_IMAGE_${randomUUID()}`;
      let createdPrivateDir = false;
      let wrotePublicFile = false;
      let wrotePrivateFile = false;

      try {
        try {
          await mkdir(privateDir);
          createdPrivateDir = true;
        } catch (error) {
          if (error.code !== 'EEXIST') throw error;
        }

        const [clientIdentity, privateIdentity] = await Promise.all([stat(clientDir), stat(privateDir)]);
        assert.notDeepEqual(
          [clientIdentity.dev, clientIdentity.ino],
          [privateIdentity.dev, privateIdentity.ino],
          '이 회귀 테스트는 대소문자를 구분하는 Linux 파일시스템이 필요합니다.',
        );

        await writeFile(
          publicPath,
          `<svg xmlns="http://www.w3.org/2000/svg"><text>${publicSentinel}</text></svg>`,
          { flag: 'wx' },
        );
        wrotePublicFile = true;
        await writeFile(
          privatePath,
          `<svg xmlns="http://www.w3.org/2000/svg"><text>${privateSentinel}</text></svg>`,
          { flag: 'wx' },
        );
        wrotePrivateFile = true;

        // 공개 정적 이미지는 정상 제공돼야 한다. 이 앱은 Sharp를 직접 설치하지
        // 않으므로 최적화 성공 여부와 별개로 파일 경계가 처리 전에 거부되는지 검사한다.
        const publicResponse = await fetch(`${siteUrl}/${filename}`);
        const publicBody = await publicResponse.text();
        assert.equal(publicResponse.status, 200, `정상 이미지 응답 실패: ${publicBody}\n${output}`);
        assert.ok(publicBody.includes(publicSentinel));

        const traversalQuery = new URLSearchParams({ href: `/../CLIENT/${filename}`, w: '32', f: 'svg' });
        const traversalResponse = await fetch(`${siteUrl}/_image?${traversalQuery}`);
        const traversalBody = await traversalResponse.text();
        assert.equal(traversalResponse.status, 400, `이미지 파일 경계에서 거부되지 않았습니다: ${output}`);
        assert.ok(!traversalBody.includes(privateSentinel));
      } finally {
        try {
          if (wrotePublicFile) await unlink(publicPath);
        } finally {
          try {
            if (wrotePrivateFile) await unlink(privatePath);
          } finally {
            if (createdPrivateDir) await rmdir(privateDir);
          }
        }
      }
    });

    await t.test('공개 회차는 기존 SSR 메타와 60초 공유 캐시를 유지한다', async () => {
      const { response, html } = await read(0);
      assert.equal(response.status, 200);
      assert.equal(response.headers.get('cache-control'), 'public, max-age=60');
      assert.ok(html.includes('PUBLIC_EPISODE'));
      assert.ok(html.includes(episodeId));
      assert.ok(!html.includes('ViewerEntry'));
      const dom = new JSDOM(html);
      const heading = dom.window.document.querySelector('h1');
      assert.equal(heading?.textContent, 'PUBLIC_EPISODE');
      assert.ok(!heading?.classList.contains('sr-only'));
      assert.equal(dom.window.document.querySelector('time')?.getAttribute('datetime'), '2026-11-01T00:00:00Z');
      assert.equal(dom.window.document.querySelector('time')?.textContent, '2026.11.01');
      assert.equal(dom.window.document.querySelector('main .page-container')?.dataset.spacing, 'viewer');
      assert.equal(dom.window.document.querySelector('.page-description'), null);
      dom.window.close();
    });

    await t.test('무료 가격 셸에도 이후 유료 전환을 복구할 구매 경로를 전달한다', async () => {
      publicPrice = null;
      try {
        const { response, html } = await read(0);
        assert.equal(response.status, 200);
        assert.equal(response.headers.get('cache-control'), 'public, max-age=60');
        assert.ok(html.includes('returnPath'));
        assert.ok(html.includes('amount'));
      } finally {
        publicPrice = 500;
      }
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

    await t.test('결제 복귀는 no-store이고 개인 query·결과를 SSR에 넣지 않는다', async () => {
      const response = await fetch(`${siteUrl}/payments/return?paymentId=PRIVATE_ORDER&code=SUCCESS&message=PRIVATE_PG_MESSAGE`);
      const html = await response.text();
      assert.equal(response.status, 200);
      assert.equal(response.headers.get('cache-control'), 'no-store');
      assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
      assert.equal(response.headers.get('x-robots-tag'), 'noindex');
      assert.ok(!html.includes('PRIVATE_ORDER'));
      assert.ok(!html.includes('PRIVATE_PG_MESSAGE'));
      assert.ok(!html.includes('결제가 확인됐어요'));
      assert.ok(html.includes('서버에서 결제 상태를 확인하고 있어요'));
    });

    await t.test('작품 회차 목록 SSR은 공개 잠금 표시와 공유 캐시만 포함한다', async () => {
      const response = await fetch(`${siteUrl}/works/${ids[0]}`, {
        headers: { Cookie: 'login_hint=reader; access_token=FAKE_BROWSER_COOKIE' },
      });
      const html = await response.text();
      assert.equal(response.status, 200);
      assert.equal(response.headers.get('cache-control'), 'public, max-age=60');
      assert.ok(html.includes('PUBLIC_EPISODE'));
      assert.ok(html.includes('잠금'));
      assert.ok(!html.includes('구매완료'));
      assert.ok(!html.includes('FAKE_BROWSER_COOKIE'));
    });

    await t.test('구매 내역은 쿠키와 query에 관계없이 개인 정보 없는 no-store 셸이다', async () => {
      const before = requests.length;
      for (const cookie of [undefined, 'login_hint=PRIVATE_READER; access_token=FAKE_BROWSER_COOKIE']) {
        const response = await fetch(`${siteUrl}/my/purchases?page=2&paymentId=PRIVATE_ORDER`, {
          headers: cookie ? { Cookie: cookie } : {},
        });
        const html = await response.text();
        assert.equal(response.status, 200);
        assert.equal(response.headers.get('cache-control'), 'no-store');
        assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
        assert.equal(response.headers.get('x-robots-tag'), 'noindex');
        assert.ok(html.includes('구매 내역'));
        for (const secret of ['PRIVATE_READER', 'FAKE_BROWSER_COOKIE', 'PRIVATE_ORDER']) {
          assert.ok(!html.includes(secret));
        }
      }
      assert.equal(requests.length, before, 'SSR에서 계정·구매 목록 API를 조회하지 않는다');
    });

    assert.equal(requests.length, 6);
    assert.ok(requests.every((req) => !req.cookie));
    assert.ok(requests.every((req) => /^\/works\/[^/]+$/.test(req.url)));

    await t.test('작품 페이지네이션은 SSR 링크의 태그와 페이지 경계를 보존한다', async () => {
      for (const page of [1, 2, 3]) {
        const response = await fetch(`${siteUrl}/works?page=${page}&tag=${encodeURIComponent('테스트 태그')}`);
        assert.equal(response.status, 200);
        const dom = new JSDOM(await response.text(), { url: siteUrl });
        try {
          const nav = dom.window.document.querySelector('nav[aria-label="페이지 이동"]');
          assert.ok(nav);
          assert.equal(nav.querySelectorAll('ul > li').length, 3);
          assert.ok(nav.querySelector('[aria-current="page"]').textContent.includes(`${page}페이지`));
          const [previous, , next] = nav.querySelectorAll('li');
          for (const [item, target, unavailable] of [[previous, page - 1, page === 1], [next, page + 1, page === 3]]) {
            if (unavailable) {
              assert.equal(item.querySelector('a'), null);
              assert.ok(item.querySelector('button')?.disabled);
            } else {
              const link = new URL(item.querySelector('a').href);
              assert.equal(link.pathname, '/works');
              assert.equal(link.searchParams.get('tag'), '테스트 태그');
              assert.equal(Number(link.searchParams.get('page') ?? 1), target);
            }
          }
        } finally {
          dom.window.close();
        }
      }
    });

    await t.test('계정 영역은 페이지와 인증 상태에 관계없이 같은 폭·여백·제목 구조를 사용한다', async () => {
      let reference;
      for (const path of ['/my', '/my/purchases', '/my/settings', '/my/profile', '/my/password']) {
        for (const token of ['', 'VALID_ACCOUNT', 'TEMP_ERROR']) {
          const response = await fetch(`${siteUrl}${path}`, {
            headers: token ? { Cookie: `access_token=${token}` } : {},
          });
          const dom = new JSDOM(await response.text());
          try {
            const container = dom.window.document.querySelector('main > .page-container');
            assert.ok(container);
            const layout = [container.className, container.dataset.width, container.dataset.spacing];
            reference ??= layout;
            assert.deepEqual(layout, reference);
            assert.equal(container.querySelectorAll('h1').length, 1);
            assert.ok(container.querySelector('.page-header .page-title'));
            assert.equal(container.getAttribute('style'), null);
          } finally { dom.window.close(); }
        }
      }
    });

    await t.test('인증 레이아웃은 제목·폼과 로그인 오류 슬롯을 보존한다', async () => {
      for (const [path, title] of [['login?error=oauth_failed', '로그인'], ['signup', '회원가입'], ['verify-email', '이메일 인증']]) {
        const response = await fetch(`${siteUrl}/auth/${path}`);
        assert.equal(response.status, 200);
        const dom = new JSDOM(await response.text());
        try {
          const panel = dom.window.document.querySelector('.auth-panel');
          assert.equal(panel?.querySelector('h1')?.textContent, title);
          assert.ok(panel?.querySelector('astro-island'));
          if (title === '로그인') {
            assert.ok(panel.textContent.includes('구글 로그인에 실패했어요.'));
            assert.ok(panel.querySelector('h1').compareDocumentPosition(panel.firstElementChild) & dom.window.Node.DOCUMENT_POSITION_PRECEDING);
          }
        } finally { dom.window.close(); }
      }
    });

    await t.test('커미션은 공통 제목의 actions 슬롯과 유의사항을 표시한다', async () => {
      const response = await fetch(`${siteUrl}/commission`);
      assert.equal(response.status, 200);
      const dom = new JSDOM(await response.text());
      try {
        assert.equal(dom.window.document.querySelector('main .page-container')?.dataset.width, 'wide');
        assert.equal(dom.window.document.querySelector('h1')?.id, 'commission-list-title');
        assert.ok(dom.window.document.querySelector('.page-header-row')?.textContent.includes('현재 모든 커미션이 마감되었어요.'));
        assert.ok(dom.window.document.querySelector('#commission-notes-title'));
      } finally { dom.window.close(); }
    });

    await t.test('공유 메뉴 셸은 마운트 전 fallback만 닉네임으로 보정하고 HTML을 삽입하지 않는다', async () => {
      const response = await fetch(`${siteUrl}/my/purchases`);
      const html = await response.text();
      const nickname = '독자 <img src=x onerror=alert(1)>';
      for (const hint of ['', encodeURIComponent(nickname), '%E0%A4']) {
        const dom = new JSDOM(html, { url: siteUrl, runScripts: 'outside-only' });
        try {
          dom.window.document.cookie = `login_hint=${hint}; Path=/`;
          const script = dom.window.document.querySelector('script[data-account-bootstrap]');
          assert.ok(script, '서버 셸에 페인트 전 fallback 보정이 포함된다');
          dom.window.eval(script.textContent);
          const link = dom.window.document.querySelector('[data-account-placeholder]');
          assert.ok(link);
          assert.equal(link.textContent.trim(), hint === encodeURIComponent(nickname) ? nickname : '로그인');
          assert.equal(link.getAttribute('href'), hint === encodeURIComponent(nickname) ? '/my' : '/auth/login');
          assert.equal(link.querySelector('img'), null);
          assert.equal(link.hasAttribute('title'), false);
        } finally {
          dom.window.close();
        }
      }
      assert.ok(!html.includes(nickname));
    });

    for (const [path, title, component] of [
      ['/my', '계정', null],
      ['/my/profile', '프로필 수정', 'ProfileEditor'],
      ['/my/password', '비밀번호 변경', 'PasswordEditor'],
      ['/my/settings', '설정', null],
    ]) {
      await t.test(`${title} 페이지는 인증·개인 캐시·장애 경계를 유지한다`, async () => {
        const firstRequest = requests.length;
        for (const cookie of [undefined, 'access_token=EXPIRED_ACCOUNT; login_hint=STALE_HINT']) {
          const recovery = await fetch(`${siteUrl}${path}`, {
            redirect: 'manual',
            headers: cookie ? { Cookie: cookie } : undefined,
          });
          assert.equal(recovery.status, 200);
          assert.equal(recovery.headers.get('location'), null);
          assert.equal(recovery.headers.get('cache-control'), 'no-store');
          assert.equal(recovery.headers.get('x-robots-tag'), 'noindex');
          const html = await recovery.text();
          const dom = new JSDOM(html);
          try {
            assert.equal(dom.window.document.querySelector('h1')?.textContent, title);
            assert.ok(html.includes('AccountSessionRecovery'));
            assert.ok(html.includes('로그인 확인 중...'));
            assert.equal(dom.window.document.querySelector('form'), null);
            for (const marker of ['private@example.com', 'PRIVATE_ACCOUNT', 'STALE_HINT', 'EXPIRED_ACCOUNT', '알림 설정 기능은 준비 중']) {
              assert.ok(!html.includes(marker));
            }
          } finally { dom.window.close(); }
        }
        for (const token of ['VALID_ACCOUNT', 'TEMP_ERROR']) {
          const response = await fetch(`${siteUrl}${path}`, {
            headers: { Cookie: `access_token=${token}` },
          });
          const html = await response.text();
          assert.equal(response.status, 200);
          assert.equal(response.headers.get('cache-control'), 'no-store');
          assert.equal(response.headers.get('x-robots-tag'), 'noindex');
          if (token === 'VALID_ACCOUNT') {
            const dom = new JSDOM(html);
            try {
              assert.equal(dom.window.document.querySelector('h1')?.textContent, title);
              if (component) {
                assert.ok(html.includes(component));
                assert.equal(dom.window.document.querySelector('form')?.getAttribute('method'), 'post');
                assert.ok(dom.window.document.querySelector('a[href="/my"]'));
                assert.ok(html.includes(path.endsWith('profile') ? '변경 내용 저장' : '현재 비밀번호'));
              } else if (path === '/my/settings') {
                assert.ok(html.includes('알림 설정 기능은 준비 중'));
                assert.ok(!html.includes('PRIVATE_ACCOUNT'));
                assert.ok(!html.includes('private@example.com'));
              } else {
                assert.ok(html.includes('private@example.com'));
                assert.ok(html.includes('PRIVATE_ACCOUNT'));
                assert.ok(dom.window.document.querySelector('a[href="/my/profile"]'));
                assert.ok(dom.window.document.querySelector('a[href="/my/password"]'));
                assert.equal(dom.window.document.querySelector('form'), null);
                for (const unwanted of ['passkey', '패스키', '2단계 인증', '이메일 관리']) {
                  assert.ok(!html.includes(unwanted));
                }
              }
            } finally { dom.window.close(); }
            assert.ok(!html.includes('access_token=VALID_ACCOUNT'));
          } else {
            assert.ok(html.includes('일시적인 오류'));
            assert.ok(!html.includes('private@example.com'));
            assert.ok(!html.includes('profile-nickname'));
            assert.ok(!html.includes('current-password'));
            assert.ok(!html.includes('PRIVATE_ACCOUNT'));
          }
        }
        const authRequests = requests.slice(firstRequest).filter((req) => req.url.startsWith('/auth/'));
        assert.deepEqual(authRequests, [
          { url: '/auth/me', cookie: undefined },
          { url: '/auth/me', cookie: 'access_token=EXPIRED_ACCOUNT; login_hint=STALE_HINT' },
          { url: '/auth/me', cookie: 'access_token=VALID_ACCOUNT' },
          { url: '/auth/me', cookie: 'access_token=TEMP_ERROR' },
        ]);
      });
    }

  } finally {
    if (site && site.exitCode === null && site.signalCode === null) {
      const exit = once(site, 'exit');
      site.kill('SIGTERM');
      await exit;
    }
    if (api.listening) await new Promise((resolve, reject) => api.close((error) => error ? reject(error) : resolve()));
  }
});
