import { useState } from 'react';
import { useSiteText, useUpdateSiteText } from '../../hooks/useSiteTexts';
import { describeAuthError } from '../../lib/api';
import { SITE_TEXT_MAX } from '../../lib/validation';
import type { SiteText, SiteTextKey } from '../../types';

interface SiteTextEditorProps {
  slotKey: SiteTextKey;
  label: string;
  help: string;
}

/** RHF 미사용 - 필드가 textarea 하나뿐이라 폼 라이브러리를 얹을 이유가 없다(YAGNI).
 * 로딩·에러 게이트는 여기서 처리하고, 편집 상태는 data가 확정된 뒤에만 마운트되는
 * SiteTextForm이 갖는다(works/$workId처럼 `{work && <WorkForm .../>}` 패턴과 동일 -
 * useEffect로 로컬 상태에 복사하지 않아도 useState 초기값이 마운트 시점에 한 번만 seed된다). */
export function SiteTextEditor({ slotKey, label, help }: SiteTextEditorProps) {
  const { data, isLoading, isError, error } = useSiteText(slotKey);

  return (
    <section className="flex flex-col gap-2 rounded border border-gray-200 p-4">
      <div>
        <h2 className="font-medium">{label}</h2>
        <p className="text-xs text-gray-500">{help}</p>
      </div>
      {isLoading && <p className="text-sm text-gray-500">불러오는 중...</p>}
      {isError && <p className="text-sm text-red-600">{describeAuthError(error)}</p>}
      {data && <SiteTextForm slotKey={slotKey} label={label} data={data} />}
    </section>
  );
}

function SiteTextForm({
  slotKey,
  label,
  data,
}: {
  slotKey: SiteTextKey;
  label: string;
  data: SiteText;
}) {
  const updateSiteText = useUpdateSiteText(slotKey);
  const [body, setBody] = useState(data.body);

  const handleSave = () => {
    updateSiteText.mutate({ body });
  };

  return (
    <>
      <label className="flex flex-col gap-1">
        <span className="sr-only">{label}</span>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          maxLength={SITE_TEXT_MAX}
          rows={6}
          className="rounded border border-gray-300 px-3 py-2"
        />
      </label>
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">
          {data.updated_at
            ? `마지막 저장: ${new Date(data.updated_at).toLocaleString('ko-KR')}`
            : '아직 저장된 적 없음'}
        </span>
        <button
          type="button"
          onClick={handleSave}
          disabled={updateSiteText.isPending}
          className="rounded bg-gray-900 px-3 py-2 text-sm text-white disabled:opacity-50"
        >
          {updateSiteText.isPending ? '저장 중...' : '저장'}
        </button>
      </div>
      {updateSiteText.isError && (
        <p className="text-sm text-red-600">
          저장하지 못했습니다. {describeAuthError(updateSiteText.error)}
        </p>
      )}
    </>
  );
}
