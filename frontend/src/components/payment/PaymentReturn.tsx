import { useEffect, useState } from 'react';
import { ApiError } from '../../lib/api';
import { completePayment, type PaymentStatus } from '../../lib/payments';
import { goToPurchasedEpisode, readPaymentReturn } from '../../lib/paymentReturn';

type State =
  | { kind: 'loading' }
  | { kind: 'invalid' }
  | { kind: 'login' }
  | { kind: 'error'; returnPath: string | null }
  | { kind: 'result'; status: PaymentStatus; returnPath: string | null };

const STATUS_TEXT: Record<PaymentStatus, string> = {
  preparing: '결제 완료가 아직 확인되지 않았어요. 다시 결제하기 전에 상태를 확인해 주세요.',
  ready: '결제 완료가 아직 확인되지 않았어요. 다시 결제하기 전에 상태를 확인해 주세요.',
  expired: '주문 시간이 지났고 결제 완료는 확인되지 않았어요. 이미 결제했다면 상태를 다시 확인해 주세요.',
  paid: '결제가 확인됐어요. 회차로 이동하고 있어요.',
  cancel_pending: '결제 취소 처리 중이에요. 취소가 확인될 때까지 다시 결제하지 말아 주세요.',
  cancelled: '결제 취소가 확인됐어요.',
  review_required: '결제 상태를 확인하고 있어요. 확인이 끝날 때까지 다시 결제하지 말아 주세요.',
};

export default function PaymentReturn() {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    // URL의 성공 문구나 PG 오류 원문은 화면과 권한 판정에 사용하지 않는다.
    void Promise.resolve().then(async () => {
      const input = readPaymentReturn(window.location.search);
      if (cancelled) return;
      if (!input) { setState({ kind: 'invalid' }); return; }
      try {
        const result = await completePayment(input.paymentId);
        if (cancelled) return;
        setState({ kind: 'result', status: result.status, returnPath: input.returnPath });
        if (result.status === 'paid' && input.returnPath) goToPurchasedEpisode(input.returnPath);
      } catch (error) {
        if (!cancelled) setState(error instanceof ApiError && error.status === 401
          ? { kind: 'login' }
          : { kind: 'error', returnPath: input.returnPath });
      }
    });
    return () => { cancelled = true; };
  }, [attempt]);

  const canRetry = state.kind === 'error' || state.kind === 'login'
    || (state.kind === 'result' && state.status !== 'paid' && state.status !== 'cancelled');
  return <section className="space-y-5" aria-label="결제 결과">
    <p role="status">{state.kind === 'loading' ? '서버에서 결제 상태를 확인하고 있어요.'
      : state.kind === 'invalid' ? '결제 복귀 정보를 확인할 수 없어요.'
        : state.kind === 'login' ? '결제 상태를 확인하려면 로그인해 주세요.'
          : state.kind === 'error' ? '결제 상태를 확인하지 못했어요. 이미 결제했다면 다시 결제하지 말고 상태를 재확인해 주세요.'
            : state.status === 'paid' && !state.returnPath
              ? '결제가 확인됐어요. 원래 회차 주소로 돌아가 열람해 주세요.'
              : STATUS_TEXT[state.status]}</p>
    {state.kind === 'login' && <a href="/auth/login" target="_blank" rel="noopener noreferrer" className="underline">새 창에서 로그인</a>}
    {canRetry && <button type="button" className="rounded border border-line px-4 py-2" onClick={() => {
      setState({ kind: 'loading' });
      setAttempt((value) => value + 1);
    }}>결제 상태 다시 확인</button>}
    {(state.kind === 'result' || state.kind === 'error') && state.returnPath
      && <a href={state.returnPath} data-astro-reload className="block underline">회차로 돌아가기</a>}
    <a href="/my" data-astro-reload className="block text-sm underline">마이페이지</a>
  </section>;
}
