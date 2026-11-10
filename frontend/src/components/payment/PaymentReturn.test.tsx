// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PaymentReturn from './PaymentReturn';
import { goToPurchasedEpisode } from '../../lib/paymentReturn';

vi.mock('../../lib/paymentReturn', async (original) => ({
  ...await original<typeof import('../../lib/paymentReturn')>(), goToPurchasedEpisode: vi.fn(),
}));
const path = '/works/11111111-1111-4111-8111-111111111111/12345678';
let root: Root;
let container: HTMLDivElement;
let fetchMock: ReturnType<typeof vi.fn>;
function response(status: number, body: unknown) { return new Response(JSON.stringify(body), { status }); }
function result(status: string) { return response(200, { payment_id: 'server-payment', status }); }
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  window.history.replaceState(null, '', `/payments/return?paymentId=server-payment&returnTo=${encodeURIComponent(path)}&code=FAKE_SUCCESS&message=PRIVATE_PG_MESSAGE`);
  vi.mocked(goToPurchasedEpisode).mockReset();
  fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
});
async function mount() { await act(async () => root.render(<PaymentReturn />)); }
it('SSR은 결제 ID·원문·개인 결과 없이 로딩 셸만 렌더한다', () => {
  const html = renderToString(<PaymentReturn />);
  expect(html).toContain('결제 상태를 확인');
  expect(html).not.toContain('server-payment'); expect(html).not.toContain('PRIVATE_PG_MESSAGE');
  expect(fetchMock).not.toHaveBeenCalled();
});
it('쿼리 code와 무관하게 서버 paid 확인 뒤에만 회차로 자동 이동한다', async () => {
  fetchMock.mockResolvedValue(result('paid')); await mount();
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/payments/server-payment/complete'), expect.objectContaining({ method: 'POST', credentials: 'include' }));
  expect(goToPurchasedEpisode).toHaveBeenCalledExactlyOnceWith(path);
  expect(container.textContent).not.toContain('PRIVATE_PG_MESSAGE');
});
it.each(['preparing', 'ready', 'expired', 'cancel_pending', 'cancelled', 'review_required', 'UNKNOWN'])('%s는 전문 이동·성공 안내를 만들지 않는다', async (status) => {
  fetchMock.mockResolvedValue(result(status)); await mount();
  expect(goToPurchasedEpisode).not.toHaveBeenCalled(); expect(container.textContent).not.toContain('결제가 확인됐어요');
});
it('503 뒤 사용자 명시적 재확인만 complete를 다시 호출한다', async () => {
  fetchMock.mockResolvedValueOnce(response(503, { detail: 'private' })).mockResolvedValueOnce(result('paid'));
  await mount(); expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain('다시 결제하지 말고');
  await act(async () => container.querySelector('button')!.click());
  expect(fetchMock).toHaveBeenCalledTimes(2); expect(goToPurchasedEpisode).toHaveBeenCalledWith(path);
});
it('만료 access는 refresh 후 complete 재시도로 확인한다', async () => {
  fetchMock.mockResolvedValueOnce(response(401, {})).mockResolvedValueOnce(response(200, {})).mockResolvedValueOnce(result('paid'));
  await mount(); expect(fetchMock).toHaveBeenCalledTimes(3); expect(goToPurchasedEpisode).toHaveBeenCalledWith(path);
});
it('최종 401은 로그인 안내를 표시하고 성공으로 처리하지 않는다', async () => {
  fetchMock.mockImplementation(() => Promise.resolve(response(401, {}))); await mount();
  expect(goToPurchasedEpisode).not.toHaveBeenCalled(); expect(container.textContent).toContain('로그인해 주세요');
});
it.each(['?code=SUCCESS', '?paymentId=a&paymentId=b', '?paymentId=%0D%0A'])('무효 결제 식별자는 요청하지 않는다: %s', async (query) => {
  window.history.replaceState(null, '', `/payments/return${query}`); await mount();
  expect(fetchMock).not.toHaveBeenCalled(); expect(container.textContent).toContain('복귀 정보');
});
it.each(['https://evil.test', '//evil.test', '/\\evil.test', '/my?next=https://evil.test', `${path}?paymentId=another`])('외부·허용되지 않은 복귀 경로는 자동 이동하지 않는다: %s', async (target) => {
  window.history.replaceState(null, '', `/payments/return?paymentId=server-payment&returnTo=${encodeURIComponent(target)}`);
  fetchMock.mockResolvedValue(result('paid')); await mount(); expect(goToPurchasedEpisode).not.toHaveBeenCalled();
  expect([...container.querySelectorAll('a')].map((a) => a.getAttribute('href'))).toEqual(['/my']);
});
it('화면 이탈 뒤 늦은 paid 응답은 이동시키지 않는다', async () => {
  let finish!: (value: Response) => void;
  fetchMock.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  await mount(); await act(async () => root.render(null));
  await act(async () => finish(result('paid'))); expect(goToPurchasedEpisode).not.toHaveBeenCalled();
});
