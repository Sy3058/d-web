// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import EpisodeCheckout from './EpisodeCheckout';
import { getMe } from '../../lib/auth';
import { ApiError } from '../../lib/api';
import { createEpisodeIntent, getEpisodeCheckoutInfo, CHECKOUT_NOTICE_VERSION } from '../../lib/payments';
const { requestPayment } = vi.hoisted(() => ({ requestPayment: vi.fn() }));
vi.mock('@portone/browser-sdk/v2', () => ({ requestPayment }));
vi.mock('../../lib/auth', () => ({ getMe: vi.fn() }));
vi.mock('../../lib/payments', async (original) => ({ ...await original<typeof import('../../lib/payments')>(), createEpisodeIntent: vi.fn(), getEpisodeCheckoutInfo: vi.fn() }));
const intent = { payment_id: 'server-payment', store_id: 'store', channel_key: 'server-channel', order_name: '서버 주문', total_amount: 500, currency: 'KRW', pay_method: 'CARD', notice_version: CHECKOUT_NOTICE_VERSION, expires_at: '', reused: false };
let root: Root;
let container: HTMLDivElement;
beforeEach(async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(getMe).mockReset().mockResolvedValue({ is_email_verified: true } as never);
  vi.mocked(createEpisodeIntent).mockReset().mockResolvedValue(intent);
  vi.mocked(getEpisodeCheckoutInfo).mockReset();
  requestPayment.mockReset().mockResolvedValue({ code: 'CANCELLED', message: 'private provider message' });
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
  await act(async () => root.render(<EpisodeCheckout episodeId="episode" title="회차" amount={500} returnPath="/works/work/123" />));
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
async function openModal() { if (!document.querySelector('[role=dialog]')) await act(async () => container.querySelector('button')!.click()); }
async function agree() { await openModal(); await act(async () => document.querySelector<HTMLInputElement>('input[type=checkbox]')!.click()); }
async function pay() { await openModal(); await act(async () => document.querySelector<HTMLButtonElement>('[data-checkout-submit]')!.click()); }
it('동의 전에는 intent를 만들지 않는다', async () => {
  await pay(); expect(createEpisodeIntent).not.toHaveBeenCalled(); expect(getMe).not.toHaveBeenCalled();
});
it('동시 클릭은 intent와 SDK를 한 번만 호출하고 서버 config로 redirect한다', async () => {
  await agree();
  await act(async () => { document.querySelector<HTMLButtonElement>('[data-checkout-submit]')!.click(); document.querySelector<HTMLButtonElement>('[data-checkout-submit]')!.click(); });
  expect(createEpisodeIntent).toHaveBeenCalledTimes(1);
  expect(requestPayment).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ paymentId: 'server-payment', channelKey: 'server-channel', totalAmount: 500, currency: 'CURRENCY_KRW', payMethod: 'CARD', forceRedirect: true, redirectUrl: new URL('/payments/return?returnTo=%2Fworks%2Fwork%2F123', window.location.origin).href }));
  expect(document.body.textContent).not.toContain('private provider message');
});
it.each(['kakaopay', 'tosspay'])('%s를 서버 간편결제 설정으로 연다', async (method) => {
  vi.mocked(createEpisodeIntent).mockResolvedValue({ ...intent, pay_method: 'EASY_PAY' });
  await openModal();
  await act(async () => document.querySelector<HTMLInputElement>(`input[value=${method}]`)!.click());
  await agree(); await pay();
  expect(requestPayment).toHaveBeenCalledWith(expect.objectContaining({ payMethod: 'EASY_PAY', easyPay: { easyPayProvider: method === 'kakaopay' ? 'KAKAOPAY' : 'TOSSPAY' } }));
});
it('구매 정보 변경은 SDK 없이 새 가격을 표시하고 재동의를 요구한다', async () => {
  vi.mocked(createEpisodeIntent).mockRejectedValueOnce(new ApiError(409, JSON.stringify({ detail: { code: 'checkout_changed', episode_id: 'episode', item_title: '새 회차', total_amount: 900, currency: 'KRW', notice_version: CHECKOUT_NOTICE_VERSION } })));
  await agree(); await pay();
  expect(document.body.textContent).toContain('새 회차'); expect(document.body.textContent).toContain('900원');
  expect(document.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked).toBe(false);
  expect(requestPayment).not.toHaveBeenCalled();
  await agree(); await pay(); expect(createEpisodeIntent).toHaveBeenLastCalledWith('episode', 900, 'card');
});
it('알 수 없는 새 고지는 기존 고지와 결제 동작을 닫는다', async () => {
  vi.mocked(createEpisodeIntent).mockRejectedValue(new ApiError(409, JSON.stringify({ detail: { code: 'checkout_changed', episode_id: 'episode', item_title: '새 회차', total_amount: 900, currency: 'KRW', notice_version: 'unknown' } })));
  await agree(); await pay(); expect(document.querySelector('input[type=checkbox]')).toBeNull();
  expect(document.querySelector<HTMLButtonElement>('[data-checkout-submit]')!.disabled).toBe(true); expect(requestPayment).not.toHaveBeenCalled();
});
it.each(['login', 'verify'])('%s 필요 시 intent를 만들지 않는다', async (mode) => {
  vi.mocked(getMe).mockResolvedValue(mode === 'login' ? null : { is_email_verified: false } as never);
  await agree(); await pay();
  expect(document.querySelector('a')!.getAttribute('href')).toBe(mode === 'login' ? '/auth/login' : '/auth/verify-email');
  expect(createEpisodeIntent).not.toHaveBeenCalled();
});
it.each(['reject', 'undefined', 'error'])('SDK %s는 고정 안내로 종료한다', async (mode) => {
  if (mode === 'reject') requestPayment.mockRejectedValue(new Error('secret'));
  else requestPayment.mockResolvedValue(mode === 'undefined' ? undefined : { code: 'ERROR', message: 'secret' });
  await agree(); await pay(); expect(document.body.textContent).toContain('결제를 시작하거나 확인할 수 없어요'); expect(document.body.textContent).not.toContain('secret');
  expect(document.querySelector('a')!.getAttribute('href')).toBe('/payments/return?returnTo=%2Fworks%2Fwork%2F123&paymentId=server-payment');
});
it('unmount 후 늦은 intent는 SDK를 열지 않는다', async () => {
  let finish!: (value: typeof intent) => void;
  vi.mocked(createEpisodeIntent).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  await agree(); await pay(); await act(async () => root.render(null));
  await act(async () => finish(intent)); expect(requestPayment).not.toHaveBeenCalled();
});

it('intent 금액 불일치는 SDK와 임의 금액 갱신을 막고 동의를 초기화한다', async () => {
  vi.mocked(createEpisodeIntent).mockResolvedValue({ ...intent, total_amount: 700 });
  await agree(); await pay();
  expect(requestPayment).not.toHaveBeenCalled();
  expect(document.body.textContent).toContain('500원');
  expect(document.body.textContent).not.toContain('700원');
  expect(document.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked).toBe(false);
  expect(document.querySelector<HTMLButtonElement>('[data-checkout-submit]')!.disabled).toBe(true);
});
it('SDK 성공 응답의 다른 ID 대신 서버 intent ID로 복귀한다', async () => {
  const assign = vi.fn();
  const browserWindow = window;
  vi.stubGlobal('window', new Proxy(browserWindow, {
    get(target, property) {
      if (property === 'location') return { origin: browserWindow.location.origin, assign };
      return Reflect.get(target, property);
    },
  }));
  try {
    requestPayment.mockResolvedValue({ paymentId: 'untrusted-provider-id' });
    await agree(); await pay();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/payments/return?returnTo=%2Fworks%2Fwork%2F123&paymentId=server-payment');
  } finally { vi.unstubAllGlobals(); }
});

it('SSR과 닫힌 상태에는 구매 버튼만 있고 열기만으로 API를 호출하지 않는다', async () => {
  const html = renderToString(<EpisodeCheckout episodeId="episode" title="회차" amount={500} returnPath="/works/work/123" />);
  expect(html).toContain('유료 회차 구매하기'); expect(html).not.toContain('role="dialog"');
  expect(document.querySelector('[role=dialog]')).toBeNull();
  await openModal();
  expect(document.querySelector('[role=dialog]')!.getAttribute('aria-modal')).toBe('true');
  expect(document.activeElement?.textContent).toBe('구매하기');
  expect(document.querySelector('h3')?.textContent).toBe('회차');
  expect(getMe).not.toHaveBeenCalled(); expect(createEpisodeIntent).not.toHaveBeenCalled(); expect(requestPayment).not.toHaveBeenCalled();
});
it('Escape로 닫고 포커스와 body 스크롤 상태를 복원한다', async () => {
  document.body.style.overflow = 'auto';
  await openModal(); expect(document.body.style.overflow).toBe('hidden');
  await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
  expect(document.querySelector('[role=dialog]')).toBeNull();
  expect(document.activeElement).toBe(container.querySelector('button'));
  expect(document.body.style.overflow).toBe('auto'); document.body.style.overflow = '';
});
it('배경과 닫기 버튼은 닫고 다시 열 때 동의를 초기화한다', async () => {
  await agree();
  await act(async () => document.querySelector<HTMLElement>('[data-checkout-backdrop]')!.click());
  expect(document.querySelector('[role=dialog]')).toBeNull();
  await openModal(); expect(document.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked).toBe(false);
  await act(async () => document.querySelector<HTMLButtonElement>('[aria-label="구매창 닫기"]')!.click());
  expect(document.querySelector('[role=dialog]')).toBeNull();
});
it('Tab과 Shift Tab 포커스를 모달 안에서 순환한다', async () => {
  await agree();
  const first = document.querySelector<HTMLButtonElement>('[aria-label="구매창 닫기"]')!;
  const last = document.querySelector<HTMLButtonElement>('[data-checkout-submit]')!;
  last.focus();
  const forward = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
  document.dispatchEvent(forward); expect(forward.defaultPrevented).toBe(true); expect(document.activeElement).toBe(first);
  const backward = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true });
  document.dispatchEvent(backward); expect(backward.defaultPrevented).toBe(true); expect(document.activeElement).toBe(last);
});
it('서버 요청 중에는 모든 닫기를 막고 오류 뒤 모달을 유지한다', async () => {
  let finish!: (value: { code: string }) => void;
  vi.mocked(createEpisodeIntent).mockReturnValue(new Promise((_, reject) => { finish = () => reject(new Error('offline')); }));
  await agree(); await pay();
  expect(document.querySelector<HTMLButtonElement>('[aria-label="구매창 닫기"]')!.disabled).toBe(true);
  await act(async () => {
    document.querySelector<HTMLButtonElement>('[aria-label="구매창 닫기"]')!.click();
    document.querySelector<HTMLElement>('[data-checkout-backdrop]')!.click();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  });
  expect(document.querySelector('[role=dialog]')).not.toBeNull();
  await act(async () => finish({ code: 'CANCELLED' }));
  expect(document.querySelector('[role=dialog]')).not.toBeNull();
  expect(document.body.textContent).toContain('결제를 시작하거나 확인할 수 없어요');
  await act(async () => document.querySelector<HTMLButtonElement>('[aria-label="구매창 닫기"]')!.click());
  await openModal(); expect(document.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked).toBe(false);
});
it('모달이 열린 컴포넌트를 unmount하면 portal과 body 잠금을 정리한다', async () => {
  await openModal(); await act(async () => root.render(null));
  expect(document.querySelector('[role=dialog]')).toBeNull(); expect(document.body.style.overflow).toBe('');
});
it('새 가격과 알 수 없는 고지의 차단은 모달을 다시 열어도 보존한다', async () => {
  vi.mocked(createEpisodeIntent).mockRejectedValue(new ApiError(409, JSON.stringify({ detail: { code: 'checkout_changed', episode_id: 'episode', item_title: '새 회차', total_amount: 900, currency: 'KRW', notice_version: 'unknown' } })));
  await agree(); await pay();
  await act(async () => document.querySelector<HTMLButtonElement>('[aria-label="구매창 닫기"]')!.click());
  await openModal(); expect(document.body.textContent).toContain('900원');
  expect(document.querySelector('input[type=checkbox]')).toBeNull();
  expect(document.querySelector<HTMLButtonElement>('[data-checkout-submit]')!.disabled).toBe(true);
});

it('SDK 실행 중 모달·trap·스크롤 잠금을 해제하고 실패 뒤 복원한다', async () => {
  let finish!: (value: { code: string }) => void;
  requestPayment.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  await agree(); await pay();
  expect(document.querySelector('[role=dialog]')).toBeNull();
  expect(document.body.style.overflow).toBe('');
  expect(container.querySelector('button')!.disabled).toBe(true);
  expect(container.textContent).toContain('결제 진행 중');
  const sdkButton = document.createElement('button'); document.body.append(sdkButton); sdkButton.focus();
  const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
  document.dispatchEvent(tab); expect(tab.defaultPrevented).toBe(false); expect(document.activeElement).toBe(sdkButton);
  await act(async () => finish({ code: 'CANCELLED' })); sdkButton.remove();
  expect(document.querySelector('[role=dialog]')).not.toBeNull();
  expect(document.body.style.overflow).toBe('hidden');
  expect(document.body.textContent).toContain('결제 상태 확인');
  expect(document.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked).toBe(false);
});
it('SDK 대기 중 컴포넌트 unmount 뒤 늦은 결과로 모달을 다시 열지 않는다', async () => {
  let finish!: (value: { code: string }) => void;
  requestPayment.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  await agree(); await pay(); await act(async () => root.render(null));
  await act(async () => finish({ code: 'CANCELLED' }));
  expect(document.querySelector('[role=dialog]')).toBeNull();
  expect(document.body.style.overflow).toBe('');
});
it('모달 내부 클릭은 배경 닫기로 처리하지 않는다', async () => {
  await openModal(); await act(async () => document.querySelector<HTMLElement>('h2')!.click());
  expect(document.querySelector('[role=dialog]')).not.toBeNull();
});

it('모달 배경을 inert로 만들고 닫으면 이전 값을 복구한다', async () => {
  const background = document.createElement('button');
  background.inert = false;
  document.body.append(background);
  await openModal();
  expect(background.inert).toBe(true);
  expect(document.querySelector<HTMLElement>('[data-checkout-backdrop]')?.inert).not.toBe(true);
  await act(async () => document.querySelector<HTMLButtonElement>('[aria-label="구매창 닫기"]')!.click());
  expect(background.inert).toBe(false);
  background.remove();
});

async function renderMissingPrice(episodeId = 'episode', workId = 'work') {
  await act(async () => root.render(<EpisodeCheckout workId={workId} episodeId={episodeId} title="캐시 회차" amount={null} returnPath="/works/work/123" />));
}
it('캐시 가격 null은 현재 공개 가격만 복구하고 버튼 클릭 전 인증·intent·SDK를 호출하지 않는다', async () => {
  vi.mocked(getEpisodeCheckoutInfo).mockResolvedValue({ title: '현재 회차', amount: 900 });
  await renderMissingPrice();
  expect(getEpisodeCheckoutInfo).toHaveBeenCalledExactlyOnceWith('work', 'episode');
  expect(document.querySelector('[role=dialog]')).toBeNull();
  expect(getMe).not.toHaveBeenCalled(); expect(createEpisodeIntent).not.toHaveBeenCalled(); expect(requestPayment).not.toHaveBeenCalled();
  await openModal(); expect(document.querySelector('h3')?.textContent).toBe('현재 회차'); expect(document.body.textContent).toContain('900원');
});
it('가격 로딩은 구매 버튼을 비활성화하고 회차 부재는 새로고침만 안내한다', async () => {
  let finish!: (value: null) => void;
  vi.mocked(getEpisodeCheckoutInfo).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  await renderMissingPrice(); expect(container.querySelector('button')!.disabled).toBe(true); expect(container.textContent).toContain('가격을 확인하고 있어요');
  await act(async () => finish(null)); expect(container.querySelector('button')).toBeNull();
  expect(container.querySelector('a')!.getAttribute('href')).toBe('/works/work/123');
});
it('가격 조회 장애는 명시적 재시도에서만 복구한다', async () => {
  vi.mocked(getEpisodeCheckoutInfo).mockRejectedValueOnce(new Error('private payload')).mockResolvedValueOnce({ title: '회복 회차', amount: 500 });
  await renderMissingPrice(); expect(container.textContent).toContain('가격을 불러올 수 없어요'); expect(container.textContent).not.toContain('private payload');
  expect(getEpisodeCheckoutInfo).toHaveBeenCalledTimes(1);
  await act(async () => container.querySelector('button')!.click());
  expect(getEpisodeCheckoutInfo).toHaveBeenCalledTimes(2); expect(container.textContent).toContain('유료 회차 구매하기');
  expect(document.querySelector('[role=dialog]')).toBeNull();
});
it('가격 복구 중 unmount한 뒤 늦은 응답은 UI를 만들지 않는다', async () => {
  let finish!: (value: { title: string; amount: number }) => void;
  vi.mocked(getEpisodeCheckoutInfo).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  await renderMissingPrice(); await act(async () => root.render(null));
  await act(async () => finish({ title: '늦은 회차', amount: 500 })); expect(container.textContent).toBe('');
});
it('회차 변경 뒤 이전 가격 조회 응답을 적용하지 않는다', async () => {
  let finish!: (value: { title: string; amount: number }) => void;
  vi.mocked(getEpisodeCheckoutInfo).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; })).mockResolvedValueOnce(null);
  await renderMissingPrice(); await renderMissingPrice('next-episode', 'next-work');
  await act(async () => finish({ title: '이전 회차', amount: 500 }));
  expect(container.textContent).not.toContain('이전 회차'); expect(container.querySelector('button')).toBeNull(); expect(getMe).not.toHaveBeenCalled();
});
