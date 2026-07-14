import { createFileRoute, Link } from '@tanstack/react-router';
import { useWorks } from '../../../hooks/useWorks';
import { WorkList } from '../../../components/works/WorkList';
import { describeAuthError } from '../../../lib/api';

export const Route = createFileRoute('/_auth/works/')({
  component: WorksPage,
});

function WorksPage() {
  const { data: works, isLoading, isError, error } = useWorks();

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">
          작품 관리{works && <span className="ml-2 text-gray-400">{works.length}</span>}
        </h1>
        <Link to="/works/new" className="rounded bg-gray-900 px-3 py-2 text-white">
          + 작품 등록
        </Link>
      </div>
      {isLoading && <p className="text-gray-500">불러오는 중...</p>}
      {isError && <p className="text-sm text-red-600">{describeAuthError(error)}</p>}
      {works && <WorkList works={works} />}
    </main>
  );
}
