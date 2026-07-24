import { api, ApiError } from './api';

// backend/src/schemas/viewer.py의 계약을 손으로 옮긴다(catalog.ts와 동일 관례). image 노드
// attrs는 저장 스키마의 key가 아니라 presigned URL이 담긴 src로 치환돼 있다(M2 B2
// IMPLEMENTATION_FREE_CONTENT_API.md "치환은 재조립" - 서버·에디터·뷰어 3곳 동일 스키마
// 규칙의 의도된 예외). paywall 노드는 서버가 항상 제거하므로 이 타입엔 등장하지 않는다.
export interface ContentDocNode {
  type: string;
  content?: ContentDocNode[];
  text?: string;
  marks?: { type: string; attrs?: Record<string, unknown> }[];
  attrs?: Record<string, unknown>;
}

export interface ContentDoc {
  type: 'doc';
  content: ContentDocNode[];
}

export interface EpisodeContentResponse {
  episode_id: string;
  content: ContentDoc;
  has_paid_part: boolean;
}

export interface ProgressRead {
  episode_id: string;
  page_no: number;
  updated_at: string;
}

// 404(회차 없음·미공개·soft-delete 작품)는 정상 흐름 - lib/catalog.ts getWorkDetail과 동일
// 원칙으로 null 반환. 그 외(5xx 등)는 그대로 던져 fail-closed를 유지한다.
export async function getEpisodeContent(episodeId: string): Promise<EpisodeContentResponse | null> {
  try {
    return await api.get<EpisodeContentResponse>(`/episodes/${episodeId}/content`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

// 401(비로그인)·404(저장된 진행도 없음) 모두 "복원할 값 없음"으로 취급한다 - 비로그인
// 열람은 정상 흐름이라 여기서 로그인 유도로 승격하지 않는다(C1: PUT만 인증 필수, GET은
// 이 뷰어가 애초에 로그인 상태에서만 호출한다 - login_hint 게이트는 Viewer.tsx 소관).
export async function getProgress(episodeId: string): Promise<ProgressRead | null> {
  try {
    return await api.get<ProgressRead>(`/episodes/${episodeId}/progress`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 404)) return null;
    throw e;
  }
}

// 저장 실패는 조용히 무시한다(C1 결정 - 진행도는 열람을 막지 않는 부가 기능).
export async function putProgress(episodeId: string, pageNo: number): Promise<void> {
  try {
    await api.put(`/episodes/${episodeId}/progress`, { page_no: pageNo });
  } catch {
    /* no-op */
  }
}

// --- 순수 로직 (vitest 대상, 네트워크 없음) ---

// 결정 6 "앞 2~3장"의 상한. 전체 이미지 순번(top-level 텍스트 블록 개수와 무관) 기준.
const FIRST_HIGH_PRIORITY_IMAGES = 3;

/** 최상위 이미지 노드의 순번(0-based, 그 이미지 이전에 등장한 이미지 개수)으로 우선순위를
 * 정한다. 앞 2~3장만 high, 나머지는 low(결정 6 - 우선순위 없는 eager는 채택안이 아니다). */
export function imageFetchPriority(imageOrdinal: number): 'high' | 'low' {
  return imageOrdinal < FIRST_HIGH_PRIORITY_IMAGES ? 'high' : 'low';
}

const LOGIN_HINT_PREFIX = 'login_hint=';

/** login_hint 쿠키(비-HttpOnly 표시용, Navbar.astro와 동일 판별 원천 - DECISIONS "네비
 * 로그인 표시")의 존재로 로그인 여부를 판별한다. 진행도 GET/PUT을 비로그인에서 아예
 * 안 쏘기 위한 게이트 - 401을 받고 나서 처리하는 대신 요청 자체를 막는다. */
export function isLoggedIn(cookieString: string): boolean {
  return cookieString.split('; ').some((c) => c.indexOf(LOGIN_HINT_PREFIX) === 0);
}

/** 저장된 진행도(page_no)를 현재 블록 수 범위로 자른다. 본문 수정으로 블록이 줄면 저장된
 * 인덱스가 범위를 넘을 수 있다(계획 검증 2026-07-23 보강 - 클램프 없으면 스크롤 복원이
 * 존재하지 않는 블록을 가리켜 무동작하거나 예외를 낸다). */
export function clampBlockIndex(pageNo: number, blockCount: number): number {
  if (blockCount <= 0) return 0;
  return Math.min(Math.max(pageNo, 0), blockCount - 1);
}
