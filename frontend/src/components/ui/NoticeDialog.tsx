import { Dialog } from '@base-ui/react/dialog';
import { useRef, type RefObject } from 'react';
import { controlBase, ghostControl } from './controlStyles';

interface NoticeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  message: string;
  confirmLabel?: string;
  returnFocus?: RefObject<HTMLElement | null>;
}

export default function NoticeDialog({
  open,
  onOpenChange,
  title = '알림',
  message,
  confirmLabel = '확인',
  returnFocus,
}: NoticeDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  return (
    <Dialog.Root open={open} onOpenChange={(nextOpen) => onOpenChange(nextOpen)}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-[70] bg-black/30" />
        <Dialog.Popup
          initialFocus={confirmRef}
          finalFocus={returnFocus}
          className="fixed left-1/2 top-1/2 z-[80] w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-control border border-line bg-paper p-6 shadow-lg outline-none"
        >
          <Dialog.Title className="pr-10 text-base font-semibold text-ink">{title}</Dialog.Title>
          <Dialog.Description className="mt-4 whitespace-pre-line break-words text-sm leading-relaxed text-muted">{message}</Dialog.Description>
          <Dialog.Close type="button" aria-label="닫기" className={`${ghostControl} absolute right-2 top-2 p-0`}>
            <span aria-hidden="true">×</span>
          </Dialog.Close>
          <div className="mt-6 flex justify-end">
            <Dialog.Close type="button" ref={confirmRef} className={`${controlBase} bg-ink px-5 py-2 text-paper hover:bg-ink-strong`}>
              {confirmLabel}
            </Dialog.Close>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
