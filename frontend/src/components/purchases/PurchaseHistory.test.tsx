// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PurchaseHistory from './PurchaseHistory';
import type { PurchaseHistoryItem } from '../../lib/purchases';
const item: PurchaseHistoryItem = {
  id: 'purchase', payment_id: 'payment', item_title: '구매 당시 제목', order_name: '[LOCAL FIXTURE] viewer abcd', work_title: '작품 제목', thumbnail_url: 'https://images.example/public/cover.webp', amount: 1500, currency: 'KRW', paid_at: '2026-11-01T00:00:00Z', status: 'active', first_viewed_at: null, refund_amount: null, refunded_at: null,
  receipt_url: 'https://receipt.example/pay', viewer_path: '/works/12345678-1234-1234-1234-123456789abc/12345678',
};
const response = (items = [item], page = 1, total = 21) => new Response(JSON.stringify({ items, page, page_size: 20, total }));
let container: HTMLDivElement;
let root: Root | undefined;
beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  window.history.replaceState(null, '', '/my/purchases');
  container = document.createElement('div'); document.body.append(container);
});
afterEach(async () => {
  await act(async () => root?.unmount()); root = undefined;
  container.remove(); vi.unstubAllGlobals();
});
async function mount() { await act(async () => { root = createRoot(container); root.render(<PurchaseHistory />); }); }
async function click(label: string) { await act(async () => { Array.from(container.querySelectorAll('button')).find((button) => button.textContent === label)!.click(); }); }
it('SSR는 개인 props나 요청 없이 로딩 셸만 렌더한다', () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  const html = renderToString(<PurchaseHistory />);
  expect(html).toContain('불러오는 중'); expect(html).not.toContain(item.item_title); expect(fetch).not.toHaveBeenCalled();
});
it('작품 카드에 금액과 결제 일시를 표시하고 내부 주문명과 상세 정보는 제거한다', async () => {
  const fetch = vi.fn().mockResolvedValue(response()); vi.stubGlobal('fetch', fetch);
  await mount();
  expect(container.textContent).toContain(item.item_title); expect(container.textContent).not.toContain(item.order_name);
  expect(container.textContent).toContain(item.work_title);
  expect(container.querySelector('img')?.getAttribute('src')).toBe(item.thumbnail_url);
  expect(container.querySelector('details')).toBeNull();
  expect(container.querySelector('li > div')?.textContent).toContain('1,500원');
  const paidAt = container.querySelector('time');
  expect(paidAt?.getAttribute('datetime')).toBe(item.paid_at);
  expect(paidAt?.textContent).toBe(new Date(item.paid_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }));
  expect(paidAt?.classList.contains('text-muted')).toBe(true);
  const card = container.querySelector(`a[href="${item.viewer_path}"]`)!;
  expect(card.hasAttribute('data-astro-reload')).toBe(true);
  expect(card.textContent).toContain(item.item_title);
  expect(card.querySelector('img')).not.toBeNull();
  expect(container.textContent).toContain('1,500원');
  expect(container.textContent).not.toMatch(/구매 완료|결제 정보|열람 기록|아직 열람하지 않았어요/);
  const receipt = container.querySelector('a[target="_blank"]'); expect(receipt?.getAttribute('rel')).toBe('noopener noreferrer');
  expect(container.querySelector(`a[href="${item.viewer_path}"]`)).not.toBeNull(); expect(fetch).toHaveBeenCalledTimes(1);
});
it('비활성 구매는 카드에 연결하지 않고 상태와 열람 및 환불 상세를 표시하지 않는다', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([
    { ...item, id: '1', status: 'refunded', first_viewed_at: item.paid_at, refund_amount: 1500, refunded_at: item.paid_at },
    { ...item, id: '2', status: 'refund_pending', receipt_url: null, viewer_path: null },
    { ...item, id: '3', status: 'review_required', receipt_url: 'javascript:alert(1)' },
  ])));
  await mount();
  expect(container.textContent).not.toMatch(/환불 완료|환불 처리 중|확인 필요|환불 금액|환불 일시|열람 기록|첫 열람/);
  expect(container.querySelector('details')).toBeNull();
  expect(container.querySelectorAll('li > div:first-child > a')).toHaveLength(0);
  expect(container.querySelectorAll('time')).toHaveLength(3);
  expect(container.querySelectorAll('a')).toHaveLength(1);
});
it('401 refresh 성공 시 목록을 표시한다', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response('', { status: 401 })).mockResolvedValueOnce(new Response('{}')).mockResolvedValueOnce(response());
  vi.stubGlobal('fetch', fetch); await mount();
  expect(container.textContent).toContain(item.item_title); expect(fetch.mock.calls[1][0]).toContain('/auth/refresh');
});
it.each(['401', '503', 'network'])('refresh %s 실패를 로그인 또는 일시 오류로 구분하고 명시적으로 재시도한다', async (failure) => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response('', { status: 401 }));
  if (failure === 'network') fetch.mockRejectedValueOnce(new TypeError('private network detail'));
  else fetch.mockResolvedValueOnce(new Response('private response', { status: Number(failure) }));
  vi.stubGlobal('fetch', fetch); await mount();
  expect(container.textContent).not.toContain('private');
  if (failure === '401') {
    expect(container.querySelector('a')?.getAttribute('href')).toBe('/auth/login');
    expect(container.querySelector('button')).toBeNull();
  } else {
    expect(container.querySelector('a')).toBeNull(); expect(container.textContent).toContain('불러오지 못했어요');
    fetch.mockResolvedValueOnce(response()); await click('다시 시도'); expect(container.textContent).toContain(item.item_title);
  }
});
it('깊은 빈 페이지를 보존하고 페이지 전환 중 이전 목록을 숨긴다', async () => {
  window.history.replaceState(null, '', '/my/purchases?page=3');
  let resolve!: (value: Response) => void;
  const fetch = vi.fn().mockResolvedValueOnce(response([], 3, 21)).mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done; }));
  vi.stubGlobal('fetch', fetch); await mount(); expect(container.textContent).toContain('3페이지'); expect(container.textContent).toContain('이 페이지에 구매 내역이 없어요');
  await click('이전 페이지'); expect(container.textContent).toContain('불러오는 중'); expect(container.textContent).not.toContain('3페이지');
  await act(async () => resolve(response([item], 2))); expect(container.textContent).toContain('2페이지'); expect(fetch).toHaveBeenCalledTimes(2);
});
it.each(['resolve', 'reject'])('unmount 뒤 늦은 %s를 무시하고 새 목록을 보존한다', async (kind) => {
  let resolve!: (value: Response) => void; let reject!: (error: Error) => void;
  const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>((done, fail) => { resolve = done; reject = fail; })).mockResolvedValueOnce(response([]));
  vi.stubGlobal('fetch', fetch); await mount(); await act(async () => root!.unmount()); root = undefined; await mount();
  await act(async () => { if (kind === 'resolve') resolve(response()); else reject(new Error('late')); });
  expect(container.textContent).toContain('구매 내역이 없어요'); expect(container.textContent).not.toContain(item.item_title);
});

it('page2 진입은 단일 GET이며 빈 목록이어도 페이지를 되돌리지 않는다', async () => {
  window.history.replaceState(null, '', '/my/purchases?page=2');
  const fetch = vi.fn().mockResolvedValue(response([], 2, 0)); vi.stubGlobal('fetch', fetch);
  await mount(); expect(fetch).toHaveBeenCalledTimes(1); expect(fetch.mock.calls[0][0]).toContain('/my/purchases?page=2');
  expect(container.textContent).toContain('2페이지');
});

it('누락된 작품 정보와 썸네일은 대체 표시하고 뷰어 경로가 없으면 연결하지 않는다', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([{ ...item, work_title: null, thumbnail_url: null, viewer_path: null, receipt_url: null }])));
  await mount();
  expect(container.textContent).toContain('작품 정보 없음');
  expect(container.textContent).toContain('이미지 없음');
  expect(container.textContent).not.toMatch(/열람 불가|구매 완료/);
  expect(container.querySelector('img')).toBeNull();
  expect(container.querySelector('a')).toBeNull();
});
it('썸네일 오류는 추가 API 요청 없이 대체 표시한다', async () => {
  const fetch = vi.fn().mockResolvedValue(response()); vi.stubGlobal('fetch', fetch);
  await mount();
  await act(async () => { container.querySelector('img')!.dispatchEvent(new Event('error')); });
  expect(container.querySelector('img')).toBeNull();
  expect(container.textContent).toContain('이미지 없음');
  expect(fetch).toHaveBeenCalledTimes(1);
});
