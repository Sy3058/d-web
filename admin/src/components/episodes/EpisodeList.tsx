import { Link } from '@tanstack/react-router';
import { useDeleteEpisode, useUnpublishEpisode } from '../../hooks/useEpisodes';
import { describeAuthError } from '../../lib/api';
import type { Episode } from '../../types';
import { EpisodeActionsMenu } from './EpisodeActionsMenu';

interface EpisodeListProps {
  workId: string;
  episodes: Episode[];
  /** 작품 기본가(works.episode_base_price). price NULL 회차의 실제 금액 표기에 쓴다. */
  basePrice?: number | null;
}

function statusBadge(episode: Episode): { label: string; className: string } {
  if (episode.is_published) return { label: '공개', className: 'bg-green-100 text-green-700' };
  // 예약 여부는 published_at 존재로 판별한다(draft + 미래 시각 = E1 스케줄러 대기).
  if (episode.published_at) return { label: '예약', className: 'bg-blue-100 text-blue-700' };
  return { label: '임시저장', className: 'bg-gray-100 text-gray-600' };
}

function priceLabel(episode: Episode, basePrice: number | null | undefined): string {
  if (episode.is_free) return '무료';
  if (episode.price != null) return `${episode.price.toLocaleString()}원`;
  // price NULL = works.episode_base_price를 따른다(A1). 기본가 로딩 전엔 '기본가'로 폴백.
  return basePrice == null ? '기본가' : `${basePrice.toLocaleString()}원`;
}

export function EpisodeList({ workId, episodes, basePrice }: EpisodeListProps) {
  const unpublishEpisode = useUnpublishEpisode(workId);
  const deleteEpisode = useDeleteEpisode(workId);

  if (episodes.length === 0) {
    return <p className="text-gray-500">아직 에피소드가 없습니다. 첫 에피소드를 등록해 보세요.</p>;
  }

  const handleDelete = (episode: Episode) => {
    // 번호 소진은 되돌릴 수 없는 결과라 누르기 전에 알려야 한다(#85 - UNIQUE가
    // deleted_at을 보지 않아 삭제된 회차가 번호를 계속 점유한다).
    const warning =
      `${episode.episode_no}화 "${episode.title}"을(를) 삭제할까요?` +
      '\n독자에게 즉시 보이지 않게 되고, 이 회차 번호는 다시 쓸 수 없습니다.';
    if (window.confirm(warning)) {
      deleteEpisode.mutate(episode.id);
    }
  };

  // 진행 중인 요청의 대상 id(라벨용). 잠금은 행이 아니라 **종류 단위**로 건다 - 훅
  // 옵저버는 가장 최근 mutate 하나만 추적하므로, 삭제가 인플라이트일 때 다른 행의 삭제를
  // 또 발사하면 앞선 요청의 실패(isError)가 화면에서 유실되고 잠금이 새 행으로 옮겨간다
  // (#85 리뷰 실측 재현). 같은 종류는 직렬화하고, 종류가 다르면(내리기 vs 삭제) 별개 훅
  // 인스턴스라 서로 간섭이 없어 잠그지 않는다.
  const unpublishingId = unpublishEpisode.isPending ? unpublishEpisode.variables : null;
  const deletingId = deleteEpisode.isPending ? deleteEpisode.variables : null;

  return (
    <>
      {unpublishEpisode.isError && (
        <p className="mb-2 text-sm text-red-600">
          비공개로 전환하지 못했습니다. {describeAuthError(unpublishEpisode.error)}
        </p>
      )}
      {deleteEpisode.isError && (
        <p className="mb-2 text-sm text-red-600">
          삭제하지 못했습니다. {describeAuthError(deleteEpisode.error)}
        </p>
      )}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-gray-500">
            <th className="px-3 py-2 font-medium">회차</th>
            <th className="px-3 py-2 font-medium">제목</th>
            <th className="px-3 py-2 font-medium">이미지</th>
            <th className="px-3 py-2 font-medium">가격</th>
            <th className="px-3 py-2 font-medium">상태</th>
            <th className="px-3 py-2">
              <span className="sr-only">관리</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {episodes.map((episode) => {
            const badge = statusBadge(episode);
            return (
              <tr key={episode.id} className="border-t border-gray-200 hover:bg-gray-50">
                <td className="px-3 py-2 text-gray-500">{episode.episode_no}화</td>
                <td className="px-3 py-2">
                  <Link
                    to="/works/$workId/episodes/$episodeId"
                    params={{ workId, episodeId: episode.id }}
                    className="block font-medium hover:underline"
                  >
                    {episode.title}
                  </Link>
                  {episode.subtitle && <p className="text-xs text-gray-400">{episode.subtitle}</p>}
                </td>
                <td className="px-3 py-2 text-gray-500">{episode.image_keys.length}장</td>
                <td className="px-3 py-2 text-gray-500">{priceLabel(episode, basePrice)}</td>
                <td className="px-3 py-2">
                  <span className={`rounded px-2 py-0.5 text-xs ${badge.className}`}>
                    {badge.label}
                  </span>
                  {episode.draft != null && (
                    <span className="ml-1 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
                      임시저장본
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right">
                  <EpisodeActionsMenu
                    episode={episode}
                    onUnpublish={() => unpublishEpisode.mutate(episode.id)}
                    onDelete={() => handleDelete(episode)}
                    isUnpublishing={unpublishingId === episode.id}
                    isDeleting={deletingId === episode.id}
                    unpublishLocked={unpublishEpisode.isPending}
                    deleteLocked={deleteEpisode.isPending}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
