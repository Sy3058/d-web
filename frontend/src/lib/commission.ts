import { api, ApiError } from './api';
import type { WorkListItem } from './catalog';

// backend/src/schemas/commission.py의 공개 DTO 계약을 손으로 옮긴다. admin DTO와 달리
// sample image key는 없고 공개 URL만 있다.
export interface PublicCommissionItem {
  id: string;
  title: string;
  description: string | null;
  price_text: string;
  duration_text: string | null;
  sample_image_urls: string[];
  is_open: boolean;
}

export type SiteTextKey = 'landing_intro' | 'commission_notes';

export interface SiteTextRead {
  key: SiteTextKey;
  body: string;
  updated_at: string | null;
}

export interface ArtistProfileRead {
  name: string;
  profile_image_url: string | null;
  twitter_url: string | null;
  postype_url: string | null;
}

export async function getCommissionItems(): Promise<PublicCommissionItem[]> {
  return api.get<PublicCommissionItem[]>('/commission-items');
}

export async function getArtistProfile(): Promise<ArtistProfileRead> {
  return api.get<ArtistProfileRead>('/artist-profile');
}

export function isNotFoundError(error: unknown): boolean {
  const status =
    error instanceof ApiError
      ? error.status
      : typeof error === 'object' && error !== null && 'status' in error
        ? error.status
        : undefined;
  return status === 404;
}

export async function resolveOptionalSiteText(
  request: () => Promise<SiteTextRead>,
): Promise<SiteTextRead | null> {
  try {
    return await request();
  } catch (error) {
    if (isNotFoundError(error)) return null;
    throw error;
  }
}

// 공개 GET의 404는 작가가 이 슬롯을 아직 한 번도 저장하지 않았다는 정상 상태다.
// 그 외 오류는 페이지가 실제 장애를 빈 문구로 위장하지 않도록 그대로 전파한다.
export async function getSiteText(key: SiteTextKey): Promise<SiteTextRead | null> {
  return resolveOptionalSiteText(() => api.get<SiteTextRead>(`/site-texts/${key}`));
}

export interface LandingWorks {
  recent: WorkListItem | null;
  others: WorkListItem[];
}

export function splitLandingWorks(works: WorkListItem[]): LandingWorks {
  const [recent = null, ...others] = works;
  return { recent, others };
}

export function selectLandingCommissions(
  items: PublicCommissionItem[],
  limit = 4,
): PublicCommissionItem[] {
  return items.slice(0, Math.max(0, limit));
}

export type CommissionAvailability = 'empty' | 'open' | 'closed';

export function commissionAvailability(items: PublicCommissionItem[]): CommissionAvailability {
  if (items.length === 0) return 'empty';
  return items.some((item) => item.is_open) ? 'open' : 'closed';
}
