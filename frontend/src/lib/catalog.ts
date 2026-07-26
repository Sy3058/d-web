import { api, ApiError } from './api';

// backend/src/schemas/catalog.py의 타입을 손으로 옮긴 계약. models/work.py의
// WorkStatus(StrEnum)과 값이 일치해야 한다(preparing/ongoing/completed/hiatus).
export type WorkStatus = 'preparing' | 'ongoing' | 'completed' | 'hiatus';

export const WORK_STATUS_LABEL: Record<WorkStatus, string> = {
  preparing: '준비중',
  ongoing: '연재중',
  completed: '완결',
  hiatus: '휴재',
};

// 백엔드가 프론트에 미러링되지 않은 새 WorkStatus를 보내면 라벨 조회가 undefined가 돼
// 배지가 빈 값으로 렌더된다 - 원값이라도 노출해 상태가 통째로 사라지지 않게 폴백한다.
export function statusLabel(status: WorkStatus): string {
  return WORK_STATUS_LABEL[status] ?? status;
}

export interface Tag {
  id: string;
  name: string;
}

export interface WorkListItem {
  id: string;
  title: string;
  cover_image_url: string | null;
  status: WorkStatus;
  tags: Tag[];
  episode_count: number;
}

export interface WorkListResponse {
  items: WorkListItem[];
  total: number;
  page: number;
  size: number;
}

export interface EpisodeSummary {
  id: string;
  episode_no: number;
  title: string;
  subtitle: string | null;
  thumbnail_url: string | null;
  is_free: boolean;
  is_locked: boolean;
  is_purchased: boolean;
  price: number | null;
}

export interface PublicTag {
  id: string;
  name: string;
  work_count: number;
}

export interface WorkDetail {
  id: string;
  title: string;
  synopsis: string | null;
  cover_image_url: string | null;
  episode_base_price: number;
  status: WorkStatus;
  tags: Tag[];
  episodes: EpisodeSummary[];
}

const PAGE_SIZE = 24;

export async function getWorks(page: number, tag?: string): Promise<WorkListResponse> {
  const params = new URLSearchParams({ page: String(page), size: String(PAGE_SIZE) });
  if (tag) params.set('tag', tag);
  return api.get<WorkListResponse>(`/works?${params.toString()}`);
}

export async function getTags(): Promise<PublicTag[]> {
  return api.get<PublicTag[]>('/tags');
}

// 404(작품 없음)·422(무효 UUID 등 경로 파라미터 검증 실패)는 모두 "이 id로는 작품을
// 찾을 수 없음"(영구·정상 흐름)이라 null 반환 - lib/auth.ts의 getMe 패턴과 동일.
// 그 외 에러(5xx 등)는 그대로 던진다 - 여기서 삼키면 실제 장애가 "작품 없음"으로
// 위장돼 my/index.astro의 401 vs 5xx 구분과 같은 이유로 fail-closed를 유지한다.
export async function getWorkDetail(id: string): Promise<WorkDetail | null> {
  try {
    return await api.get<WorkDetail>(`/works/${id}`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) return null;
    throw e;
  }
}

// --- 순수 로직 (vitest 대상, 네트워크 없음) ---

export function totalPages(total: number, size: number): number {
  if (size <= 0 || total <= 0) return 1;
  return Math.ceil(total / size);
}

// 목록 페이지네이션·태그 필터 링크 공용 빌더. page=1은 기본값이라 쿼리에서
// 생략한다(?page=1과 /works가 같은 페이지를 가리키게 - 링크 정규화). 정규화가 없으면
// 캐시가 꺼지는 게 아니라 같은 내용이 두 URL 키로 쪼개져 적중률만 떨어진다.
export function buildWorksUrl(params: { page?: number; tag?: string }): string {
  const search = new URLSearchParams();
  if (params.page && params.page > 1) search.set('page', String(params.page));
  if (params.tag) search.set('tag', params.tag);
  const qs = search.toString();
  return qs ? `/works?${qs}` : '/works';
}

export function formatPrice(price: number | null): string {
  if (price === null) return '무료';
  return `${price.toLocaleString('ko-KR')}원`;
}
