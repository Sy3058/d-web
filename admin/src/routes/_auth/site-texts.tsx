import { createFileRoute, Link } from '@tanstack/react-router';
import { SiteTextEditor } from '../../components/commission/SiteTextEditor';
import type { SiteTextKey } from '../../types';

export const Route = createFileRoute('/_auth/site-texts')({
  component: SiteTextsPage,
});

const SLOTS: { key: SiteTextKey; label: string; help: string }[] = [
  { key: 'landing_intro', label: '랜딩 소개', help: '메인 랜딩(/) 히어로에 노출되는 작가 소개 문구.' },
  {
    key: 'commission_notes',
    label: '커미션 유의사항',
    help: '/commission 페이지에 노출되는 접수 유의사항.',
  },
];

function SiteTextsPage() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">사이트 문구 편집</h1>
        <Link
          to="/commission"
          className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
        >
          커미션 관리로
        </Link>
      </div>
      {SLOTS.map((slot) => (
        <SiteTextEditor key={slot.key} slotKey={slot.key} label={slot.label} help={slot.help} />
      ))}
    </main>
  );
}
