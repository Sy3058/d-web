import { createFileRoute, Link } from '@tanstack/react-router';
import { ArtistProfileEditor } from '../../components/commission/ArtistProfileEditor';

export const Route = createFileRoute('/_auth/artist-profile')({
  component: ArtistProfilePage,
});

function ArtistProfilePage() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">작가 프로필 수정</h1>
        <Link
          to="/"
          className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
        >
          관리자 홈으로
        </Link>
      </div>
      <ArtistProfileEditor />
    </main>
  );
}
