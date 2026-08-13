import { useEffect, useRef, useState } from 'react';
import Cropper, { type Area } from 'react-easy-crop';
import { getCroppedImageFile } from '../../lib/cropImage';

// 서버에 올라가는 건 크롭된 결과물이지 이 원본이 아니다(cropImage가 1600px로 캡한다).
// 그래서 이 상한은 백엔드 용량 제한의 미러가 아니라, 브라우저가 거대한 이미지를 디코드하다
// 탭이 죽는 걸 막는 클라이언트 쪽 방어선이다.
const MAX_FILE_BYTES = 20 * 1024 * 1024;
const MAX_FILE_MB = MAX_FILE_BYTES / (1024 * 1024);

interface ImageCropModalProps {
  title: string;
  aspect: number;
  cropShape?: 'rect' | 'round';
  outputFileName: string;
  onClose: () => void;
  onComplete: (file: File) => void | Promise<void>;
}

export function ImageCropModal({
  title,
  aspect,
  cropShape = 'rect',
  outputFileName,
  onClose,
  onComplete,
}: ImageCropModalProps) {
  const [step, setStep] = useState<'select' | 'crop'>('select');
  const [rawImageUrl, setRawImageUrl] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [cropError, setCropError] = useState<string | null>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<Area | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const processingRef = useRef(false);

  // blob URL은 명시적으로 revoke하지 않으면 원본(최대 20MB)이 페이지 수명 내내 메모리에
  // 남는다. 정리 시점을 상태가 아니라 ref로 잡는 이유: useEffect([url])로 걸면
  // StrictMode의 mount→cleanup→mount에서 아직 <img>가 쓰는 URL을 revoke해 미리보기가 깨진다.
  const objectUrlRef = useRef<string | null>(null);
  useEffect(
    () => () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    },
    [],
  );

  const setRawImage = (file: File | null) => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    objectUrlRef.current = file ? URL.createObjectURL(file) : null;
    setRawImageUrl(objectUrlRef.current);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      setFileError(`이미지가 너무 큽니다 (최대 ${MAX_FILE_MB}MB)`);
      setFileName(null);
      setRawImage(null);
      return;
    }
    setFileError(null);
    setFileName(file.name);
    setRawImage(file);
  };

  const handleComplete = async () => {
    if (!rawImageUrl || !croppedAreaPixels || processingRef.current) return;
    processingRef.current = true;
    setIsProcessing(true);
    setCropError(null);
    try {
      const file = await getCroppedImageFile(rawImageUrl, croppedAreaPixels, outputFileName);
      await onComplete(file);
    } catch {
      // canvas.toBlob이 null을 주거나(브라우저 캔버스 면적 상한 초과) 이미지 디코드가
      // 실패하는 경우 - 안 잡으면 '완료'가 아무 반응 없이 먹통이 된다.
      setCropError('이미지를 자르지 못했습니다. 다른 이미지를 사용해 주세요.');
    } finally {
      processingRef.current = false;
      setIsProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex w-full max-w-md flex-col gap-4 rounded bg-white p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={isProcessing}
            className="text-gray-500 hover:text-gray-800"
            aria-label="닫기"
          >
            ×
          </button>
        </div>

        {step === 'select' && (
          <>
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2 rounded border border-gray-300 px-3 py-2">
                <span className="flex-1 truncate text-sm text-gray-500">
                  {fileName ?? '파일을 선택해 주세요.'}
                </span>
                <label className="shrink-0 cursor-pointer rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50">
                  파일 선택
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                </label>
              </div>
              {fileError ? (
                <p className="text-xs text-red-600">{fileError}</p>
              ) : (
                <p className="text-xs text-gray-500">
                  최대 {MAX_FILE_MB}MB의 이미지 파일을 올릴 수 있어요.
                </p>
              )}
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={isProcessing}
                className="rounded border border-gray-300 px-3 py-2"
              >
                취소
              </button>
              <button
                type="button"
                disabled={!rawImageUrl}
                onClick={() => setStep('crop')}
                className="rounded bg-gray-900 px-3 py-2 text-white disabled:opacity-50"
              >
                다음
              </button>
            </div>
          </>
        )}

        {step === 'crop' && rawImageUrl && (
          <>
            <div className="relative h-80 w-full bg-gray-900">
              <Cropper
                image={rawImageUrl}
                crop={crop}
                zoom={zoom}
                aspect={aspect}
                cropShape={cropShape}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={(_, areaPixels) => setCroppedAreaPixels(areaPixels)}
              />
            </div>
            <label className="flex flex-col gap-1 text-sm">
              확대/축소
              <input
                type="range"
                min={1}
                max={3}
                step={0.1}
                value={zoom}
                onChange={(e) => setZoom(Number(e.target.value))}
              />
            </label>
            {cropError && <p className="text-sm text-red-600">{cropError}</p>}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={isProcessing}
                className="rounded border border-gray-300 px-3 py-2"
              >
                취소
              </button>
              <button
                type="button"
                disabled={isProcessing || !croppedAreaPixels}
                onClick={handleComplete}
                className="rounded bg-gray-900 px-3 py-2 text-white disabled:opacity-50"
              >
                {isProcessing ? '처리 중...' : '완료'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
