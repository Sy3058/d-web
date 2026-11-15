import { createFileRoute, Link } from '@tanstack/react-router';
import { useCommissionItems } from '../../../hooks/useCommissionItems';
import { CommissionList } from '../../../components/commission/CommissionList';
import { describeAuthError } from '../../../lib/api';

export const Route = createFileRoute('/_auth/commission/')({
  component: CommissionPage,
});

function CommissionPage() {
  const { data: items, isLoading, isError, error } = useCommissionItems();

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">
          커미션 관리{items && <span className="ml-2 text-gray-400">{items.length}</span>}
        </h1>
        <div className="flex gap-2">
          <Link
            to="/site-texts"
            className="admin-control admin-control-outline"
          >
            사이트 문구 편집
          </Link>
          <Link to="/commission/new" className="admin-control admin-control-primary">
            + 카드 등록
          </Link>
        </div>
      </div>
      {isLoading && <p className="text-gray-500">불러오는 중...</p>}
      {isError && <p className="text-sm text-red-600">{describeAuthError(error)}</p>}
      {items && <CommissionList items={items} />}
    </main>
  );
}
