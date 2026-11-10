import { api, ApiError } from './api';

export function isCheckoutAmount(amount: unknown): amount is number {
  return typeof amount === 'number' && Number.isSafeInteger(amount) && amount > 0 && amount <= 2_147_483_647;
}
export interface EpisodeCheckoutInfo { title: string; amount: number }
export async function getEpisodeCheckoutInfo(workId: string, episodeId: string): Promise<EpisodeCheckoutInfo | null> {
  let episodes: unknown;
  try {
    episodes = await api.get<unknown>(`/works/${encodeURIComponent(workId)}/episodes`, { cache: 'no-store' });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
  if (!Array.isArray(episodes)) return null;
  const episode = episodes.find((value) => value && typeof value === 'object' && value.id === episodeId);
  if (!episode || episode.is_free !== false || !isCheckoutAmount(episode.price)
    || typeof episode.title !== 'string' || !episode.title.trim()) return null;
  return { title: episode.title, amount: episode.price };
}

export const CHECKOUT_NOTICE_VERSION = 'episode-immediate-v1';
export const CHECKOUT_NOTICE = '결제 완료 후 전체 내용이 즉시 제공됩니다. 전체 내용 제공이 시작되면 단순 변심에 따른 청약철회가 제한됩니다. 콘텐츠가 표시·광고와 다르거나 계약 내용대로 제공되지 않은 경우는 제외됩니다.';
export type PaymentMethod = 'card' | 'kakaopay' | 'tosspay';
export type PaymentStatus = 'preparing' | 'ready' | 'expired' | 'paid' | 'cancel_pending' | 'cancelled' | 'review_required';
export interface PaymentIntent {
  payment_id: string; store_id: string; channel_key: string; order_name: string;
  total_amount: number; currency: string; pay_method: string; notice_version: string;
  expires_at: string; reused: boolean;
}
export interface CheckoutChanged {
  episode_id: string; item_title: string; total_amount: number; currency: 'KRW'; notice_version: string;
}
export function parseCheckoutChanged(error: unknown, episodeId: string): CheckoutChanged | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  try {
    const value = JSON.parse(error.message).detail;
    if (!value || value.code !== 'checkout_changed' || value.episode_id !== episodeId
      || typeof value.item_title !== 'string' || !value.item_title.trim()
      || !Number.isSafeInteger(value.total_amount) || value.total_amount <= 0 || value.total_amount > 2_147_483_647
      || value.currency !== 'KRW' || typeof value.notice_version !== 'string') return null;
    return value;
  } catch { return null; }
}
export function createEpisodeIntent(episodeId: string, amount: number, method: PaymentMethod) {
  return api.post<PaymentIntent>('/payments/episode-intents', {
    episode_id: episodeId, expected_amount: amount, payment_method: method,
    checkout_notice_version: CHECKOUT_NOTICE_VERSION, immediate_supply_consented: true,
  });
}
export async function completePayment(paymentId: string): Promise<{ payment_id: string; status: PaymentStatus }> {
  const result = await api.post<{ payment_id: string; status: PaymentStatus }>(`/payments/${encodeURIComponent(paymentId)}/complete`, {});
  if (result.payment_id !== paymentId || !['preparing', 'ready', 'expired', 'paid', 'cancel_pending', 'cancelled', 'review_required'].includes(result.status)) {
    throw new Error('Invalid payment status');
  }
  return result;
}
export function paymentReturnPath(returnPath: string, paymentId?: string): string {
  const safePath = returnPath.startsWith('/') && !returnPath.startsWith('//') && !/[\\\r\n]/.test(returnPath) ? returnPath : '/my';
  const params = new URLSearchParams({ returnTo: safePath });
  if (paymentId) params.set('paymentId', paymentId);
  return `/payments/return?${params}`;
}
export function paymentRequest(intent: PaymentIntent, method: PaymentMethod, redirectUrl: string) {
  if (intent.currency !== 'KRW' || intent.notice_version !== CHECKOUT_NOTICE_VERSION
    || !Number.isSafeInteger(intent.total_amount) || intent.total_amount <= 0 || intent.total_amount > 2_147_483_647
    || !intent.payment_id || !intent.store_id || !intent.channel_key
    || intent.pay_method !== (method === 'card' ? 'CARD' : 'EASY_PAY')) throw new Error('Invalid payment config');
  return {
    storeId: intent.store_id, channelKey: intent.channel_key, paymentId: intent.payment_id,
    orderName: intent.order_name, totalAmount: intent.total_amount,
    currency: 'CURRENCY_KRW' as const, payMethod: intent.pay_method as 'CARD' | 'EASY_PAY',
    ...(method === 'card' ? {} : { easyPay: { easyPayProvider: method === 'kakaopay' ? 'KAKAOPAY' as const : 'TOSSPAY' as const } }),
    forceRedirect: true, redirectUrl,
  };
}
