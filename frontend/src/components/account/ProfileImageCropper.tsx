import { Dialog } from '@base-ui/react/dialog';
import { useEffect, useRef, useState, type RefObject } from 'react';
import Cropper, { type Area } from 'react-easy-crop';
import { getProfileCroppedFile } from '@/lib/profileCrop';
import { controlBase, ghostControl } from '@/components/ui/controlStyles';

interface Props {
  imageSrc: string;
  onApply: (file: File) => void;
  onCancel: () => void;
  returnFocus?: RefObject<HTMLElement | null>;
}

export default function ProfileImageCropper(props: Props) {
  return <CropSelection key={props.imageSrc} {...props} />;
}

function CropSelection({ imageSrc, onApply, onCancel, returnFocus }: Props) {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [area, setArea] = useState<Area | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const zoomInput = useRef<HTMLInputElement>(null);
  const processing = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  async function apply() {
    if (!area || processing.current) return;
    processing.current = true;
    setBusy(true);
    setError('');
    try {
      const file = await getProfileCroppedFile(imageSrc, area);
      if (mounted.current) onApply(file);
    } catch {
      if (mounted.current) setError('이미지를 자르지 못했어요. 다시 시도하거나 다른 이미지를 선택해 주세요.');
    } finally {
      processing.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open && !processing.current) onCancel(); }}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-[70] bg-black/30" />
        <Dialog.Popup initialFocus={zoomInput} finalFocus={returnFocus} aria-busy={busy}
          className="fixed left-1/2 top-1/2 z-[80] max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 space-y-4 overflow-y-auto rounded-control border border-line bg-paper p-5 shadow-lg outline-none">
          <Dialog.Title className="pr-10 text-base font-semibold text-ink">프로필 이미지 자르기</Dialog.Title>
          <Dialog.Description className="text-sm text-muted">이미지를 움직이거나 확대해 위치를 조절해 주세요.</Dialog.Description>
          <Dialog.Close type="button" aria-label="닫기" disabled={busy} className={`${ghostControl} absolute right-2 top-2 p-0`}>
            <span aria-hidden="true">×</span>
          </Dialog.Close>
          <div className={`relative h-64 w-full overflow-hidden rounded-control bg-ink ${busy ? 'pointer-events-none' : ''}`}>
            <Cropper image={imageSrc} crop={crop} zoom={zoom} aspect={1} cropShape="round"
              minZoom={1} maxZoom={3} showGrid={false}
              cropperProps={{ 'aria-label': '이미지 위치 조절' }}
              mediaProps={{ onError: () => {
                setArea(null);
                setError('이미지를 불러오지 못했어요. 다른 이미지를 선택해 주세요.');
              } }}
              onCropChange={setCrop} onZoomChange={setZoom}
              onCropComplete={(_, pixels) => setArea(pixels)} />
          </div>
          <label className="flex flex-col gap-2 text-sm text-ink">
            확대/축소
            <input ref={zoomInput} type="range" min={1} max={3} step={0.1} value={zoom} disabled={busy}
              onChange={(event) => setZoom(Number(event.target.value))} />
          </label>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy || !area} onClick={() => void apply()}
              className={`${controlBase} bg-ink px-4 py-2 text-paper hover:bg-ink-strong`}>
              {busy ? '처리 중...' : '선택 영역 적용'}
            </button>
            <Dialog.Close type="button" disabled={busy} className={ghostControl}>자르기 취소</Dialog.Close>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
