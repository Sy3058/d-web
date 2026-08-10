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
  public_id: number;
  title: string;
  subtitle: string | null;
  thumbnail_url: string | null;
  is_free: boolean;
  is_locked: boolean;
  is_purchased: boolean;
  price: number | null;
  // 최초 공개 시각(E3). BE의 first_published_at을 그대로 옮긴 것 - 재공개해도 안
  // 바뀐다(published_at은 재공개마다 갱신되므로 목록 표시엔 안 쓴다). offset 붙은 ISO
  // 문자열(tz-aware). 예약만 걸리고 한 번도 공개된 적 없으면 null.
  first_published_at: string | null;
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

export type EpisodeOrder = 'asc' | 'desc';

// 회차 목록 정렬 토글(E3). 기본값은 최신순(desc) - 무효값(오타·낡은 링크)도 조용히
// desc로 폴백한다(422 없음, works/[id].astro는 파라미터 검증 대상 API가 아니라
// 사람이 클릭하는 페이지라 잘못된 쿼리로 에러 화면을 보여줄 이유가 없다).
export function parseOrder(raw: string | null): EpisodeOrder {
  return raw === 'asc' ? 'asc' : 'desc';
}

// 서버가 이미 sort_order 오름차순으로 준 배열(episodes)을 화면 정렬에 맞춰 뒤집는다.
// 새 배열을 반환한다(원본 불변) - 원본은 "첫 화 보기"(뒤집기 전 episodes[0])가
// 여전히 참조해야 하므로, in-place reverse를 쓰면 그 참조가 같이 뒤집혀 버린다.
export function orderEpisodes<T>(episodes: T[], order: EpisodeOrder): T[] {
  return order === 'asc' ? episodes : [...episodes].reverse();
}

// 회차 공개일 표시(E3). Intl.DateTimeFormat(timeZone:'Asia/Seoul') 대신 수동 +9h
// 시프트 - 프로덕션 SSR 이미지의 ICU 타임존 데이터 유무에 기대지 않기 위함(있으면
// 되고 없으면 서버만 UTC로 조용히 어긋나는 리스크를 원천 차단). KST는 DST가 없어
// 고정 오프셋(+9h)이 항상 정확하다 - 다른 타임존이었다면 이 방식이 틀렸을 것.
// 응답이 SSR HTML로 60초 공유 캐시되므로(applyCatalogCache) 절대 날짜만 쓴다 -
// "3일 전" 같은 상대 표기는 캐시 수명 안에서 낡는다.
export function formatEpisodeDate(isoString: string | null): string | null {
  if (isoString === null) return null;
  const kst = new Date(new Date(isoString).getTime() + 9 * 60 * 60 * 1000);
  const y = kst.getUTCFullYear();
  const m = String(kst.getUTCMonth() + 1).padStart(2, '0');
  const d = String(kst.getUTCDate()).padStart(2, '0');
  return `${y}.${m}.${d}`;
}
