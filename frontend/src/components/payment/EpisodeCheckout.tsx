import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { getMe } from '../../lib/auth';
import { CHECKOUT_NOTICE, CHECKOUT_NOTICE_VERSION, createEpisodeIntent, getEpisodeCheckoutInfo, isCheckoutAmount, parseCheckoutChanged, paymentRequest, paymentReturnPath, type EpisodeCheckoutInfo, type PaymentMethod } from '../../lib/payments';

interface Props { episodeId: string; workId?: string; title: string; amount: number | null; returnPath: string }
type CheckoutProps = Omit<Props, 'amount'> & { amount: number };
const FAILURE = '결제를 시작하거나 확인할 수 없어요. 이미 결제했다면 결제 상태를 확인해 주세요. 다시 시도하려면 버튼을 눌러 주세요.';
export default function EpisodeCheckout(props: Props) {
  return isCheckoutAmount(props.amount)
    ? <Checkout key={JSON.stringify(props)} {...props} amount={props.amount} />
    : <CheckoutPriceRecovery key={JSON.stringify(props)} {...props} />;
}
function CheckoutPriceRecovery({ workId, episodeId, returnPath }: Props) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ status: 'loading' | 'unavailable' | 'error' } | { status: 'ready'; item: EpisodeCheckoutInfo }>({ status: 'loading' });
  useEffect(() => {
    if (!workId) return;
    let active = true;
    getEpisodeCheckoutInfo(workId, episodeId).then(
      (item) => { if (active) setState(item ? { status: 'ready', item } : { status: 'unavailable' }); },
      () => { if (active) setState({ status: 'error' }); },
    );
    return () => { active = false; };
  }, [workId, episodeId, attempt]);
  if (state.status === 'ready') return <Checkout episodeId={episodeId} title={state.item.title} amount={state.item.amount} returnPath={returnPath} />;
  if (!workId || state.status === 'unavailable') return <p className="mt-4" role="status">현재 구매 정보를 확인할 수 없어요. <a data-astro-reload href={returnPath} className="underline">회차를 새로고침해 주세요.</a></p>;
  if (state.status === 'error') return <div className="mt-4 space-y-2"><p role="status">가격을 불러올 수 없어요. 다시 시도해 주세요.</p><button type="button" onClick={() => { setState({ status: 'loading' }); setAttempt((value) => value + 1); }} className="min-h-11 cursor-pointer rounded-control border border-line px-4 py-2">가격 다시 확인</button></div>;
  return <div className="mt-4 space-y-2"><button type="button" disabled className="min-h-11 rounded bg-ink px-5 py-3 text-paper opacity-50">유료 회차 구매하기</button><p role="status">가격을 확인하고 있어요.</p></div>;
}
function Checkout({ episodeId, title, amount, returnPath }: CheckoutProps) {
  const [item, setItem] = useState({ title, amount });
  const [open, setOpen] = useState(false);
  const [launchingSdk, setLaunchingSdk] = useState(false);
  const visible = open && !launchingSdk;
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  const [consent, setConsent] = useState(false);
  const [method, setMethod] = useState<PaymentMethod>('card');
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [message, setMessage] = useState('');
  const [auth, setAuth] = useState<'login' | 'verify' | null>(null);
  const [paymentId, setPaymentId] = useState<string | null>(null);
  const lifecycle = useRef({ active: true });
  const pending = useRef(false);
  useEffect(() => {
    if (!visible) return;
    const previousOverflow = document.body.style.overflow;
    const returnFocus = trigger.current;
    const background = [...document.body.children]
      .filter((node): node is HTMLElement => node instanceof HTMLElement && !node.contains(dialog.current))
      .map((node) => ({ node, wasInert: node.inert }));
    for (const { node } of background) node.inert = true;
    document.body.style.overflow = 'hidden';
    heading.current?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (!pending.current) setOpen(false);
      }
      if (event.key !== 'Tab') return;
      const focusable = [...(dialog.current?.querySelectorAll<HTMLElement>('button, input, a[href]') ?? [])]
        .filter((element) => !element.hasAttribute('disabled') && !element.closest('fieldset[disabled]'));
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first) { event.preventDefault(); heading.current?.focus(); return; }
      const focused = document.activeElement;
      if (event.shiftKey && (focused === first || focused === heading.current || !dialog.current?.contains(focused))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (focused === last || !dialog.current?.contains(focused))) {
        event.preventDefault(); first.focus();
      }
    }
    document.addEventListener('keydown', keydown);
    return () => {
      document.body.style.overflow = previousOverflow;
      for (const { node, wasInert } of background) node.inert = wasInert;
      document.removeEventListener('keydown', keydown);
      if (returnFocus?.isConnected) returnFocus.focus();
    };
  }, [visible]);
  useEffect(() => {
    const state = lifecycle.current;
    state.active = true;
    return () => { state.active = false; };
  }, []);
  async function checkout() {
    if (!consent || pending.current || blocked) return;
    const active = () => lifecycle.current.active;
    let launched = false;
    pending.current = true; setBusy(true); setMessage(''); setAuth(null);
    try {
      const user = await getMe();
      if (!active()) return;
      if (!user) { setAuth('login'); return; }
      if (!user.is_email_verified) { setAuth('verify'); return; }
      const intent = await createEpisodeIntent(episodeId, item.amount, method);
      if (!active()) return;
      if (intent.total_amount !== item.amount) {
        setConsent(false);
        setMessage('결제 금액을 확인할 수 없어요. 표시된 금액과 고지를 다시 확인해 주세요.');
        return;
      }
      const request = paymentRequest(intent, method, new URL(paymentReturnPath(returnPath), window.location.origin).href);
      setPaymentId(intent.payment_id);
      launched = true;
      setLaunchingSdk(true);
      const { requestPayment } = await import('@portone/browser-sdk/v2');
      if (!active()) return;
      const result = await requestPayment(request);
      if (!active()) return;
      if (!result || result.code) { setMessage(FAILURE); return; }
      window.location.assign(paymentReturnPath(returnPath, intent.payment_id));
    } catch (error) {
      if (!active()) return;
      const changed = parseCheckoutChanged(error, episodeId);
      if (changed) {
        setConsent(false);
        setItem({ title: changed.item_title, amount: changed.total_amount });
        setBlocked(changed.notice_version !== CHECKOUT_NOTICE_VERSION);
        setMessage(changed.notice_version === CHECKOUT_NOTICE_VERSION ? '구매 정보가 변경되었어요. 금액과 고지를 다시 확인하고 동의해 주세요.' : '새 구매 고지를 확인할 수 없어 결제를 진행할 수 없어요.');
      } else setMessage(FAILURE);
    } finally {
      if (active()) {
        pending.current = false; setBusy(false); setLaunchingSdk(false);
        if (launched) setConsent(false);
      }
    }
  }
  function close() { if (!pending.current) setOpen(false); }
  return <>
    <button ref={trigger} type="button" aria-haspopup="dialog" disabled={busy} onClick={() => { setConsent(false); setOpen(true); }} className="mt-4 min-h-11 rounded bg-ink px-5 py-3 text-paper cursor-pointer disabled:opacity-50">{launchingSdk ? '결제 진행 중' : '유료 회차 구매하기'}</button>
    {visible && createPortal(<div data-checkout-backdrop className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4" onClick={(event) => { if (event.target === event.currentTarget) close(); }}>
      <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby={headingId} aria-busy={busy} className="max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-xl border border-line bg-paper text-ink shadow-xl">
        <div className="flex items-center justify-between gap-4 border-b border-line px-6 py-4">
          <h2 ref={heading} id={headingId} tabIndex={-1} className="text-lg font-bold outline-none">구매하기</h2>
          <button type="button" aria-label="구매창 닫기" disabled={busy} onClick={close} className="flex min-h-11 min-w-11 cursor-pointer items-center justify-center rounded-control text-muted transition-colors hover:bg-hover disabled:cursor-default disabled:opacity-50">
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
              <path d="m6 6 12 12M18 6 6 18" />
            </svg>
          </button>
        </div>
        <div className="space-y-5 p-6">
          <div className="space-y-2">
            <h3 className="break-words text-xl font-bold leading-snug">{item.title}</h3>
            <p>{item.amount.toLocaleString('ko-KR')}원</p>
          </div>
          <fieldset disabled={busy || blocked} className="flex flex-wrap gap-x-4 gap-y-2">
            <legend className="mb-2">결제수단</legend>
            {(['card', 'kakaopay', 'tosspay'] as const).map((value, index) => (
              <label key={value} className="inline-flex min-h-11 items-center gap-2">
                <input type="radio" name={`payment-method-${episodeId}`} value={value} checked={method === value} onChange={() => setMethod(value)} />
                {['카드', '카카오페이', '토스페이'][index]}
              </label>
            ))}
          </fieldset>
          {!blocked && (
            <label className="flex items-start gap-3 border-t border-line pt-4 text-sm leading-relaxed">
              <input type="checkbox" className="mt-1 shrink-0" checked={consent} disabled={busy} onChange={(event) => setConsent(event.target.checked)} />
              <span>{CHECKOUT_NOTICE}</span>
            </label>
          )}
          <button type="button" data-checkout-submit disabled={!consent || busy || blocked} onClick={() => void checkout()} className="min-h-11 w-full cursor-pointer rounded-control bg-ink px-4 py-3 font-medium text-paper disabled:cursor-default disabled:opacity-50">
            {busy ? '결제 준비 중' : '결제하고 바로 보기'}
          </button>
          {paymentId && <p><a data-astro-reload className="underline" href={paymentReturnPath(returnPath, paymentId)}>결제 상태 확인</a></p>}
          {auth === 'login' && <p role="status"><a href="/auth/login">로그인</a> 후 이 회차로 돌아와 주세요.</p>}
          {auth === 'verify' && <p role="status"><a href="/auth/verify-email">이메일 인증</a> 후 다시 시도해 주세요.</p>}
          {message && <p role="status">{message}</p>}
        </div>
      </div>
    </div>, document.body)}
  </>;
}
