import { api, ApiError } from './api';
import { restoreViewerSession } from './viewerSession';

export interface BootstrapEpisodeLink {
  public_id: number;
  title: string;
}

export interface ViewerBootstrap {
  work_id: string;
  work_title: string;
  episode_id: string;
  public_id: number;
  episode_title: string;
  episode_subtitle: string | null;
  previous_episode: BootstrapEpisodeLink | null;
  next_episode: BootstrapEpisodeLink | null;
}

// effect에서 읽은 힌트는 세션 복구 시도에만 쓰고 실제 권한은 서버가 확인한다.
export async function getViewerBootstrap(
  workId: string,
  publicId: number,
  cookieString: string,
): Promise<ViewerBootstrap | null> {
  await restoreViewerSession(cookieString);
  try {
    return await api.get<ViewerBootstrap>(
      `/works/${encodeURIComponent(workId)}/episodes/${publicId}/viewer-bootstrap`,
      { cache: 'no-store' },
    );
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      return null;
    }
    throw error;
  }
}
