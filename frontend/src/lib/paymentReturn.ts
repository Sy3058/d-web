// 복귀 URL은 이동 편의만 제공한다. 주문 소유권과 구매 권한은 서버가 검증한다.
export function goToPurchasedEpisode(path: string) {
  window.location.replace(path);
}

export function readPaymentReturn(search: string): { paymentId: string; returnPath: string | null } | null {
  const params = new URLSearchParams(search);
  const paymentId = params.get('paymentId');
  if (params.getAll('paymentId').length !== 1 || !paymentId || !/^[a-zA-Z0-9_-]{1,64}$/.test(paymentId)) return null;
  const path = params.get('returnTo');
  const validPath = params.getAll('returnTo').length === 1 && path !== null
    && /^\/works\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\/[1-9]\d{7}$/.test(path);
  return { paymentId, returnPath: validPath ? path : null };
}
