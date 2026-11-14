import { afterEach, expect, it, vi } from 'vitest';
import { getPurchaseHistory, parsePurchasePage, safeReceiptUrl, safeViewerPath } from './purchases';
afterEach(() => vi.unstubAllGlobals());
it('page는 표준 양의 int32로 제한한다', () => {
  expect(parsePurchasePage('2147483647')).toBe(2147483647);
  for (const input of [null, '', '0', '-1', '1.5', '1e2', ' 2', '02', '2147483648']) expect(parsePurchasePage(input)).toBe(1);
});
it('구매 목록만 인증된 no-store GET으로 가져온다', async () => {
  const body = { items: [], total: 0, page: 3, page_size: 20 };
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(body)));
  vi.stubGlobal('fetch', fetch);
  await expect(getPurchaseHistory(3)).resolves.toEqual(body);
  expect(fetch).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/my/purchases?page=3'), expect.objectContaining({ credentials: 'include', cache: 'no-store' }));
});
it('HTTPS 영수증과 active의 정확한 뷰어 경로만 연결한다', () => {
  expect(safeReceiptUrl('https://receipt.example/a')).toBe('https://receipt.example/a');
  for (const url of [null, '//evil.test', 'http://evil.test', 'javascript:alert(1)', 'https://user:pass@example.com', 'https://example.com/\n', `https://example.com/${String.fromCharCode(0)}`, `https://example.com/${String.fromCharCode(127)}`]) expect(safeReceiptUrl(url)).toBeNull();
  const path = '/works/12345678-1234-1234-1234-123456789abc/12345678';
  expect(safeViewerPath({ status: 'active', viewer_path: path })).toBe(path);
  for (const status of ['refunded', 'refund_pending', 'review_required'] as const) expect(safeViewerPath({ status, viewer_path: path })).toBeNull();
  for (const viewer_path of [null, '//evil.test', '/works/not-uuid/12345678', `${path}?x=1`, `${path}/`, path.replace('12345678', '1')]) expect(safeViewerPath({ status: 'active', viewer_path })).toBeNull();
});
