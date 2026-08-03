import { Link } from '@tanstack/react-router';
import {
  useDeleteEpisode,
  useReorderEpisodes,
  useUnpublishEpisode,
} from '../../hooks/useEpisodes';
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
  const reorderEpisodes = useReorderEpisodes(workId);

  if (episodes.length === 0) {
    return <p className="text-gray-500">아직 에피소드가 없습니다. 첫 에피소드를 등록해 보세요.</p>;
  }

  // 인접 두 회차를 맞바꾼 뒤 **전량**을 보낸다(서버가 부분 목록을 409로 거부한다 -
  // 순서는 전체 집합에 대한 진술이라 부분 적용이 의미가 없다).
  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= episodes.length) return;
    const next = [...episodes];
    [next[index], next[target]] = [next[target], next[index]];
    reorderEpisodes.mutate(next.map((episode) => episode.id));
  };

  const handleDelete = (episode: Episode) => {
    // 삭제는 soft delete라 되돌릴 API가 없다(#85) - 누르기 전에 알려야 한다.
    const warning = `"${episode.title}"을(를) 삭제할까요?\n독자에게 즉시 보이지 않게 되고, 되돌릴 수 없습니다.`;
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
      {reorderEpisodes.isError && (
        <p className="mb-2 text-sm text-red-600">
          순서를 바꾸지 못했습니다. {describeAuthError(reorderEpisodes.error)}
        </p>
      )}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-gray-500">
            <th className="px-3 py-2 font-medium">
              <span className="sr-only">순서</span>
            </th>
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
          {episodes.map((episode, index) => {
            const badge = statusBadge(episode);
            return (
              <tr key={episode.id} className="border-t border-gray-200 hover:bg-gray-50">
                <td className="px-3 py-2">
                  {/* 재배열 중에는 전 버튼을 잠근다 - 인플라이트 요청의 응답이 캐시를
                      덮기 전에 또 누르면 화면에 보이는(낡은) 순서를 기준으로 계산해
                      직전 이동을 되돌리는 요청이 나간다. */}
                  <div className="flex flex-col gap-0.5">
                    <button
                      type="button"
                      onClick={() => move(index, -1)}
                      disabled={index === 0 || reorderEpisodes.isPending}
                      aria-label={`${episode.title} 위로 이동`}
                      className="rounded px-1 leading-none text-gray-400 hover:bg-gray-200 hover:text-gray-700 disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <span aria-hidden="true">↑</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => move(index, 1)}
                      disabled={index === episodes.length - 1 || reorderEpisodes.isPending}
                      aria-label={`${episode.title} 아래로 이동`}
                      className="rounded px-1 leading-none text-gray-400 hover:bg-gray-200 hover:text-gray-700 disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <span aria-hidden="true">↓</span>
                    </button>
                  </div>
                </td>
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
