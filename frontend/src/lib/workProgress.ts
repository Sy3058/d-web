import { api, ApiError } from './api';

export interface LastReadEpisode {
  id: string;
  public_id: number;
  title: string;
}

export interface WorkProgressRead {
  read_episode_ids: string[];
  last_episode: LastReadEpisode | null;
}

export interface WorkProgressSummary {
  readCount: number;
  percent: number;
}

export interface ProgressEpisode {
  id: string;
  publicId: number;
  title: string;
}

export interface ReadingCta {
  label: '첫 화 보기' | '다음 화 보기' | '마지막 화 다시 보기' | '이어 보기';
  episode: ProgressEpisode;
}

// login_hint가 남았지만 refresh까지 만료된 401은 정상적인 미렌더 상태다. 404·5xx는
// 계약/서버 오류이므로 성공 응답으로 바꾸지 않고 호출자가 부가 UI만 숨기도록 전파한다.
export async function getWorkProgress(workId: string): Promise<WorkProgressRead | null> {
  try {
    return await api.get<WorkProgressRead>(`/works/${workId}/progress`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/** 공개 SSR의 회차 수와 개인 API 응답 사이에는 최대 60초 시차가 있을 수 있다. 중복 ID를
 * 제거하고 현재 공개 회차 수로 잘라 분자가 분모를 넘거나 100%를 초과하지 않게 한다. */
export function summarizeWorkProgress(
  readEpisodeIds: readonly string[],
  totalEpisodes: number,
): WorkProgressSummary {
  const safeTotal = Math.max(0, Math.trunc(totalEpisodes));
  if (safeTotal === 0) return { readCount: 0, percent: 0 };

  const readCount = Math.min(new Set(readEpisodeIds).size, safeTotal);
  return { readCount, percent: Math.round((readCount / safeTotal) * 100) };
}

/** 공개 회차의 작가 지정 순서에서 읽을 대상을 정한다. SSR 목록과 개인 API 사이의 시차로
 * 마지막 회차가 목록에 없으면 API가 준 최신 공개 회차를 이어 보기 대상으로 사용한다. */
export function selectReadingCta(
  episodes: readonly ProgressEpisode[],
  lastEpisode: LastReadEpisode | null,
): ReadingCta | null {
  const firstEpisode = episodes[0];
  if (!firstEpisode) return null;
  if (!lastEpisode) return { label: '첫 화 보기', episode: firstEpisode };

  const lastIndex = episodes.findIndex((episode) => episode.id === lastEpisode.id);
  if (lastIndex === -1) {
    return {
      label: '이어 보기',
      episode: {
        id: lastEpisode.id,
        publicId: lastEpisode.public_id,
        title: lastEpisode.title,
      },
    };
  }

  const nextEpisode = episodes[lastIndex + 1];
  if (nextEpisode) return { label: '다음 화 보기', episode: nextEpisode };
  return { label: '마지막 화 다시 보기', episode: episodes[lastIndex] };
}
