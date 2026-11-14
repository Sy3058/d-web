import { api } from './api';

export type PurchaseStatus = 'active' | 'refund_pending' | 'refunded' | 'review_required';
export interface PurchaseHistoryItem {
  id: string;
  payment_id: string;
  item_title: string;
  order_name: string;
  work_title?: string | null;
  thumbnail_url?: string | null;
  amount: number;
  currency: string;
  paid_at: string;
  status: PurchaseStatus;
  first_viewed_at: string | null;
  refunded_at: string | null;
  refund_amount: number | null;
  receipt_url: string | null;
  viewer_path: string | null;
}
export interface PurchaseHistoryRead {
  items: PurchaseHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}
export const MAX_PURCHASE_PAGE = 2_147_483_647;
export function parsePurchasePage(value: string | null): number {
  if (value === null || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  return Number.isSafeInteger(page) && page <= MAX_PURCHASE_PAGE ? page : 1;
}
export function getPurchaseHistory(page: number): Promise<PurchaseHistoryRead> {
  return api.get<PurchaseHistoryRead>(`/my/purchases?page=${parsePurchasePage(String(page))}`, { cache: 'no-store' });
}
export function safeReceiptUrl(value: string | null): string | null {
  if (!value || /[\s\\]/.test(value)
    || [...value].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
export function safeViewerPath(item: Pick<PurchaseHistoryItem, 'status' | 'viewer_path'>): string | null {
  return item.status === 'active' && item.viewer_path !== null
    && /^\/works\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/[1-9]\d{7}$/i.test(item.viewer_path)
    ? item.viewer_path : null;
}
