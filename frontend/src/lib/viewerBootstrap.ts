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
  first_published_at: string | null;
  previous_episode: BootstrapEpisodeLink | null;
  next_episode: BootstrapEpisodeLink | null;
}

export interface ViewerBootstrapResult {
  bootstrap: ViewerBootstrap;
  authenticated: boolean;
}

// bootstrap보다 먼저 API 세션을 확인해 이후 개인 UI도 같은 서버 판정을 사용한다.
export async function getViewerBootstrap(
  workId: string,
  publicId: number,
): Promise<ViewerBootstrapResult | null> {
  const authenticated = await restoreViewerSession();
  try {
    const bootstrap = await api.get<ViewerBootstrap>(
      `/works/${encodeURIComponent(workId)}/episodes/${publicId}/viewer-bootstrap`,
      { cache: 'no-store' },
    );
    return { bootstrap, authenticated };
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      return null;
    }
    throw error;
  }
}
