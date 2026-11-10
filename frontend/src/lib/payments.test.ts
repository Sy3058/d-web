import { describe, expect, it, vi, afterEach } from 'vitest';
import { ApiError } from './api';
import { getEpisodeCheckoutInfo, completePayment, parseCheckoutChanged, paymentRequest, paymentReturnPath, CHECKOUT_NOTICE_VERSION } from './payments';
const detail = { code: 'checkout_changed', episode_id: 'episode', item_title: '회차', total_amount: 500, currency: 'KRW', notice_version: CHECKOUT_NOTICE_VERSION };
afterEach(() => vi.unstubAllGlobals());
describe('checkout contract', () => {
  it('409 object의 회차와 KRW 양수 정수를 검증한다', () => {
    const parse = (value: unknown) => parseCheckoutChanged(new ApiError(409, JSON.stringify({ detail: value })), 'episode');
    expect(parse(detail)).toEqual(detail);
    for (const value of ['checkout_changed', { ...detail, episode_id: 'other' }, { ...detail, total_amount: 0 }, { ...detail, total_amount: 2_147_483_648 }, { ...detail, total_amount: 1.5 }, { ...detail, currency: 'USD' }]) expect(parse(value)).toBeNull();
    expect(parse({ ...detail, notice_version: 'future-v2' })?.notice_version).toBe('future-v2');
  });
  it('외부 복귀 경로를 차단한다', () => {
    expect(paymentReturnPath('//evil.test')).toContain('returnTo=%2Fmy');
    expect(paymentReturnPath('/works/one', 'payment')).toBe('/payments/return?returnTo=%2Fworks%2Fone&paymentId=payment');
  });
  it('예상하지 못한 complete 상태를 성공으로 취급하지 않는다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ payment_id: 'payment', status: 'PAID' }))));
    await expect(completePayment('payment')).rejects.toThrow('Invalid payment status');
  });
  it('서버 통화와 수단을 검증한다', () => {
    expect(() => paymentRequest({ currency: 'USD' } as never, 'card', '/return')).toThrow();
    expect(() => paymentRequest({ currency: 'KRW', notice_version: CHECKOUT_NOTICE_VERSION, total_amount: 2_147_483_648 } as never, 'card', '/return')).toThrow();
  });
});

it('공개 회차 가격은 no-store 요청 한 번에서 현재 id의 안전한 필드만 반환한다', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: 'episode', title: '현재 회차', is_free: false, price: 900, content: { secret: true }, image_keys: ['private'] }])));
  vi.stubGlobal('fetch', fetchMock);
  await expect(getEpisodeCheckoutInfo('work/a', 'episode')).resolves.toEqual({ title: '현재 회차', amount: 900 });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/works/work%2Fa/episodes'), expect.objectContaining({ credentials: 'include', cache: 'no-store' }));
});
it.each([
  [{ id: 'other', title: '다른 회차', is_free: false, price: 500 }],
  [{ id: 'episode', title: '무료 회차', is_free: true, price: 500 }],
  [{ id: 'episode', title: '유료 회차', is_free: false, price: null }],
  [{ id: 'episode', title: '유료 회차', is_free: false, price: 0 }],
  [{ id: 'episode', title: '유료 회차', is_free: false, price: 2_147_483_648 }],
  [{ id: 'episode', title: '유료 회차', is_free: false, price: 1.5 }],
  [{ id: 'episode', title: ' ', is_free: false, price: 500 }],
  null,
].map((body) => [body]))('판매 불가능한 공개 metadata는 구매 정보로 쓰지 않는다: %j', async (body) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body))));
  await expect(getEpisodeCheckoutInfo('work', 'episode')).resolves.toBeNull();
});
it('404는 판매 정보 없음으로 처리하고 장애 원문은 반환하지 않는다', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('private', { status: 404 })).mockResolvedValueOnce(new Response('private', { status: 503 })));
  await expect(getEpisodeCheckoutInfo('work', 'episode')).resolves.toBeNull();
  await expect(getEpisodeCheckoutInfo('work', 'episode')).rejects.toThrow();
});
