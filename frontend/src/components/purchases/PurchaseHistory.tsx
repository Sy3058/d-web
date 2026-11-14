import { useEffect, useState } from 'react';
import { ApiError } from '../../lib/api';
import { getPurchaseHistory, MAX_PURCHASE_PAGE, parsePurchasePage, safeReceiptUrl, safeViewerPath, type PurchaseHistoryRead } from '../../lib/purchases';

type State = { kind: 'loading' } | { kind: 'success'; data: PurchaseHistoryRead } | { kind: 'login' } | { kind: 'error' };
const money = (amount: number, currency: string) => `${amount.toLocaleString('ko-KR')}${currency === 'KRW' ? '원' : ` ${currency}`}`;
const date = (value: string) => new Date(value).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });

function PurchaseThumbnail({ url }: { url: string | null | undefined }) {
  const [failed, setFailed] = useState(false);
  return <span className="flex h-24 w-18 shrink-0 items-center justify-center overflow-hidden rounded-control bg-canvas text-xs text-muted">
    {url && !failed ? <img src={url} alt="" loading="lazy" className="h-full w-full object-cover" onError={() => setFailed(true)} /> : <span>이미지 없음</span>}
  </span>;
}

export default function PurchaseHistory() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State>({ kind: 'loading' });
  useEffect(() => {
    let cancelled = false;
    const requestedPage = parsePurchasePage(new URLSearchParams(window.location.search).get('page'));
    getPurchaseHistory(requestedPage).then((data) => {
      if (!cancelled) {
        setState({ kind: 'success', data });
      }
    }, (error: unknown) => {
      if (!cancelled) {
        setState({ kind: error instanceof ApiError && error.status === 401 ? 'login' : 'error' });
      }
    });
    return () => { cancelled = true; };
  }, [attempt]);

  function navigate(next: number) {
    const url = new URL(window.location.href);
    url.searchParams.set('page', String(next));
    window.history.replaceState(null, '', url);
    setState({ kind: 'loading' });
    setAttempt((value) => value + 1);
  }
  function retry() {
    setState({ kind: 'loading' });
    setAttempt((value) => value + 1);
  }

  if (state.kind === 'loading') return <p role="status" className="text-sm text-muted">구매 내역을 불러오는 중이에요.</p>;
  if (state.kind === 'login') return <div><p className="text-sm text-muted">구매 내역을 보려면 로그인해 주세요.</p><a href="/auth/login" data-astro-reload className="underline underline-offset-4">로그인</a></div>;
  if (state.kind === 'error') return <div role="alert"><p className="text-sm text-muted">구매 내역을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.</p><button type="button" onClick={retry} className="mt-4 underline underline-offset-4">다시 시도</button></div>;
  const { items, total, page_size, page } = state.data;
  return <div>
    <p className="text-sm text-muted mb-6">총 {total.toLocaleString('ko-KR')}건</p>
    {items.length === 0 ? <p className="text-sm text-muted">{page === 1 ? '구매 내역이 없어요.' : '이 페이지에 구매 내역이 없어요.'}</p> : <ul className="space-y-4">
      {items.map((item) => {
        const receipt = safeReceiptUrl(item.receipt_url);
        const viewer = safeViewerPath(item);
        const content = <>
          <PurchaseThumbnail key={item.thumbnail_url} url={item.thumbnail_url} />
          <span className="min-w-0">
            <span className="block text-sm text-muted break-words">{item.work_title || '작품 정보 없음'}</span>
            <span className="block mt-1 font-medium text-ink break-words">{item.item_title}</span>
          </span>
        </>;
        return <li key={item.id} className="rounded-control border border-line bg-paper p-4">
          <div className="flex items-center justify-between gap-4">
            {viewer ? <a href={viewer} data-astro-reload className="flex min-w-0 flex-1 items-center gap-4">{content}</a> : <div className="flex min-w-0 flex-1 items-center gap-4">{content}</div>}
            <span className="shrink-0 text-sm font-medium text-ink">{money(item.amount, item.currency)}</span>
          </div>
          <div className="mt-3 flex items-center justify-between gap-4 text-xs text-muted">
            <time dateTime={item.paid_at} className="text-muted">{date(item.paid_at)}</time>
            {receipt && <a href={receipt} target="_blank" rel="noopener noreferrer" className="shrink-0 underline underline-offset-4">영수증 보기</a>}
          </div>
        </li>;
      })}
    </ul>}
    <nav aria-label="구매 내역 페이지" className="flex items-center justify-between mt-8 text-sm">
      <button type="button" disabled={page <= 1} onClick={() => navigate(page - 1)} className="disabled:opacity-40">이전 페이지</button>
      <span aria-current="page">{page}페이지</span>
      <button type="button" disabled={page >= MAX_PURCHASE_PAGE || page * page_size >= total} onClick={() => navigate(page + 1)} className="disabled:opacity-40">다음 페이지</button>
    </nav>
  </div>;
}
