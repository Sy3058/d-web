import { Link, useNavigate } from '@tanstack/react-router';
import type { Work } from '../../types';
import { useDeleteWork } from '../../hooks/useWorks';
import { describeAuthError } from '../../lib/api';
import { WORK_STATUS_LABEL } from '../../lib/workStatus';
import { WorkActionsMenu } from './WorkActionsMenu';

interface WorkListProps {
  works: Work[];
}

export function WorkList({ works }: WorkListProps) {
  const navigate = useNavigate();
  const deleteWork = useDeleteWork();

  if (works.length === 0) {
    return <p className="text-gray-500">등록된 작품이 없습니다.</p>;
  }

  const goToEdit = (workId: string) => {
    navigate({ to: '/works/$workId', params: { workId } });
  };

  const handleDelete = (work: Work) => {
    if (window.confirm(`"${work.title}"을(를) 삭제할까요? 목록에서 사라집니다.`)) {
      deleteWork.mutate(work.id);
    }
  };

  // 진행 중인 DELETE의 대상 id. 그 행의 삭제 항목만 잠근다(다른 작품은 계속 조작 가능).
  const deletingWorkId = deleteWork.isPending ? deleteWork.variables : null;

  return (
    <>
      {deleteWork.isError && (
        <p className="mb-2 text-sm text-red-600">
          삭제하지 못했습니다. {describeAuthError(deleteWork.error)}
        </p>
      )}
      <ul className="flex flex-col divide-y divide-gray-100">
        {works.map((work) => (
          <li key={work.id} className="flex items-center gap-2 pr-2 hover:bg-gray-50">
            {/* 카드 본문만 링크로 감싸고 메뉴는 그 바깥 형제로 둔다 - li 자체를 role="button"으로
                만들면 그 안의 메뉴 버튼이 중첩 인터랙티브 요소가 돼 키보드·스크린리더가 깨진다. */}
            <Link
              to="/works/$workId"
              params={{ workId: work.id }}
              className="flex min-w-0 flex-1 items-center gap-4 px-2 py-4"
            >
              {/* cover_image는 URL이 아니라 R2 키(works/{id}/cover.webp)라 <img>에 바로 못 박는다.
                  표지 서빙 경로는 M2에서 만든다(2026-07-15 결정: 표지 전용 공개 버킷 + 커스텀
                  도메인 - DECISIONS "표지 서빙"). 그때까지는 placeholder. */}
              <div className="flex aspect-[3/4] w-24 shrink-0 items-center justify-center rounded border border-gray-200 bg-gray-100 text-[11px] text-gray-400">
                표지
              </div>

              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="truncate font-medium">{work.title}</span>
                {work.synopsis && (
                  <span className="truncate text-sm text-gray-500">{work.synopsis}</span>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                    {WORK_STATUS_LABEL[work.status]}
                  </span>
                  {work.tags.map((tag) => (
                    <span
                      key={tag.id}
                      className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600"
                    >
                      #{tag.name}
                    </span>
                  ))}
                </div>
                <span className="text-xs text-gray-500">총 {work.episode_count}화</span>
              </div>
            </Link>

            <WorkActionsMenu
              onEdit={() => goToEdit(work.id)}
              onDelete={() => handleDelete(work)}
              isDeleting={deletingWorkId === work.id}
            />
          </li>
        ))}
      </ul>
    </>
  );
}
