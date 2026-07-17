import { Link } from '@tanstack/react-router';
import type { Episode } from '../../types';

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
  if (episodes.length === 0) {
    return <p className="text-gray-500">아직 에피소드가 없습니다. 첫 에피소드를 등록해 보세요.</p>;
  }

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="text-left text-gray-500">
          <th className="px-3 py-2 font-medium">회차</th>
          <th className="px-3 py-2 font-medium">제목</th>
          <th className="px-3 py-2 font-medium">이미지</th>
          <th className="px-3 py-2 font-medium">가격</th>
          <th className="px-3 py-2 font-medium">상태</th>
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
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
