import type { Episode } from '../../types';
import { ACTION_ITEM_CLASS, ActionsMenu } from '../common/ActionsMenu';

interface EpisodeActionsMenuProps {
  episode: Episode;
  onUnpublish: () => void;
  onDelete: () => void;
  /** 이 행의 요청이 진행 중 (라벨 표기용) */
  isUnpublishing: boolean;
  isDeleting: boolean;
  /** 같은 종류의 요청이 **어느 행에서든** 진행 중이면 잠근다(직렬화). 훅 옵저버는 가장
      최근 mutate 하나만 추적해서, 동시 발사를 허용하면 앞선 요청의 실패 표시(isError)가
      유실되고 행 잠금이 새 행으로 옮겨간다(#85 리뷰 실측). */
  unpublishLocked: boolean;
  deleteLocked: boolean;
}

export function EpisodeActionsMenu({
  episode,
  onUnpublish,
  onDelete,
  isUnpublishing,
  isDeleting,
  unpublishLocked,
  deleteLocked,
}: EpisodeActionsMenuProps) {
  return (
    <ActionsMenu label={`${episode.episode_no}화 관리 메뉴`} width="w-40">
      {(close) => (
        <>
          {/* 공개 중인 회차에만 띄운다 - 이미 비공개면 누를 이유가 없다. 예약(published_at만
              있고 미공개)인 회차도 대상이 아니다: 서버는 is_published:false를 받으면
              published_at까지 NULL로 밀어버려서, 이 항목을 예약 취소 겸용으로 쓰면
              "내리기"와 "예약 취소"가 한 버튼에 섞인다(#85 - 예약 취소는 후속). */}
          {episode.is_published && (
            <button
              type="button"
              disabled={unpublishLocked}
              onClick={() => {
                close();
                onUnpublish();
              }}
              className={ACTION_ITEM_CLASS}
            >
              {isUnpublishing ? '내리는 중...' : '비공개로 전환'}
            </button>
          )}
          {/* 잠금은 행 단위가 아니라 종류 단위(deleteLocked) - 같은 회차 중복 발사만 막으면
              다른 행과의 동시 발사가 앞선 요청의 실패 표시를 유실시킨다(위 주석). */}
          <button
            type="button"
            disabled={deleteLocked}
            onClick={() => {
              close();
              onDelete();
            }}
            className={`${ACTION_ITEM_CLASS} text-red-600`}
          >
            {isDeleting ? '삭제 중...' : '삭제'}
          </button>
        </>
      )}
    </ActionsMenu>
  );
}
