import { useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { describeAuthError, isSessionExpired } from '../../lib/api';
import { useAdminTotpConfirm, useAdminTotpSetup } from '../../hooks/useAuth';
import { TotpInput } from './TotpInput';
import type { TotpInput as TotpInputValue } from '../../lib/validation';

interface TotpEnrollProps {
  onComplete: () => void;
  /** pending 서명쿠키(10분) 만료 등으로 1단계부터 다시 밟아야 할 때. */
  onExpired: () => void;
}

export function TotpEnroll({ onComplete, onExpired }: TotpEnrollProps) {
  const setup = useAdminTotpSetup();
  const confirm = useAdminTotpConfirm();

  // QR 발급 자체가 401이면 게이트 쿠키가 만료된 것 - 에러 문구만 띄우면 사용자가
  // 아무것도 할 수 없는 화면에 갇히므로 로그인 1단계로 돌려보낸다.
  const setupExpired = setup.isError && isSessionExpired(setup.error);
  useEffect(() => {
    if (setupExpired) {
      onExpired();
    }
  }, [setupExpired, onExpired]);

  const handleSubmit = (data: TotpInputValue) => {
    confirm.mutate(data, {
      onSuccess: onComplete,
      onError: (err) => {
        if (isSessionExpired(err)) onExpired();
      },
    });
  };

  if (setup.isPending) {
    return <p className="text-sm text-gray-500">QR 코드를 생성하는 중...</p>;
  }

  if (setup.isError) {
    return <p className="text-sm text-red-600">{describeAuthError(setup.error)}</p>;
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <p className="max-w-xs text-center text-sm text-gray-600">
        인증 앱(Google Authenticator 등)으로 아래 QR 코드를 스캔한 뒤, 생성된 6자리 코드를
        입력해 등록을 완료하세요.
      </p>
      <QRCodeSVG value={setup.data.otpauth_uri} size={200} />
      <TotpInput
        onSubmit={handleSubmit}
        isPending={confirm.isPending}
        error={confirm.isError ? describeAuthError(confirm.error) : null}
      />
    </div>
  );
}
