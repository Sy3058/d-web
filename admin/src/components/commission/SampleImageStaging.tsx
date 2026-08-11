import { useEffect, useRef, useState } from 'react';
import { MAX_SAMPLES_PER_ITEM } from '../../lib/validation';
import { validateImageFile } from '../episodes/imageUpload';

interface SampleImageStagingProps {
  files: File[];
  onChange: (files: File[]) => void;
}

function StagedImagePreview({ file }: { file: File }) {
  const imageRef = useRef<HTMLImageElement>(null);

  // Object URL 생성은 render 중 부작용으로 두지 않는다. commit된 파일만 URL을 만들고,
  // 파일 변경·항목 제거·StrictMode 재마운트마다 같은 effect cleanup이 정확히 회수한다.
  useEffect(() => {
    const url = URL.createObjectURL(file);
    const image = imageRef.current;
    if (image) image.src = url;
    return () => {
      if (image) image.removeAttribute('src');
      URL.revokeObjectURL(url);
    };
  }, [file]);

  return <img ref={imageRef} alt="" className="h-full w-full object-cover" />;
}

/** 등록 화면 전용 샘플 이미지 선택 - 실제 업로드는 카드 생성 후에나 가능하다(서버가
 * item_id를 요구). WorkForm의 coverFile(로컬에만 들고 있다가 작품 생성 성공 후 업로드)과
 * 같은 패턴 - 여기서는 파일을 붙들고만 있고 네트워크 요청은 부모(new.tsx)가 '등록' 제출
 * 시점에 순서대로 보낸다. */
export function SampleImageStaging({ files, onChange }: SampleImageStagingProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const atLimit = files.length >= MAX_SAMPLES_PER_ITEM;

  const handleFilesSelected = (selected: FileList | null) => {
    if (!selected || selected.length === 0) return;
    setError(null);

    const remaining = MAX_SAMPLES_PER_ITEM - files.length;
    const problems: string[] = [];
    const accepted: File[] = [];
    for (const file of Array.from(selected)) {
      const problem = validateImageFile(file);
      if (problem) {
        problems.push(problem);
        continue;
      }
      if (accepted.length >= remaining) {
        problems.push(`카드당 샘플 이미지는 최대 ${MAX_SAMPLES_PER_ITEM}장입니다.`);
        break;
      }
      accepted.push(file);
    }
    if (problems.length > 0) setError(problems.join(' '));
    if (accepted.length > 0) onChange([...files, ...accepted]);

    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeAt = (index: number) => onChange(files.filter((_, i) => i !== index));

  const moveAt = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= files.length) return;
    const next = [...files];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          샘플 이미지 ({files.length}/{MAX_SAMPLES_PER_ITEM})
        </span>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={atLimit}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
        >
          이미지 추가
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => handleFilesSelected(e.target.files)}
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {files.length === 0 ? (
        <p className="text-sm text-gray-500">
          선택한 이미지가 없습니다. 등록 시 함께 업로드됩니다.
        </p>
      ) : (
        <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4">
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`} className="flex flex-col gap-1">
              <div className="aspect-square overflow-hidden rounded border border-gray-200 bg-gray-100">
                <StagedImagePreview file={file} />
              </div>
              <div className="flex items-center justify-between gap-1">
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => moveAt(index, -1)}
                    disabled={index === 0}
                    aria-label="왼쪽으로 이동"
                    className="flex h-6 w-6 items-center justify-center text-gray-400 hover:text-gray-700 disabled:opacity-30"
                  >
                    ◀
                  </button>
                  <button
                    type="button"
                    onClick={() => moveAt(index, 1)}
                    disabled={index === files.length - 1}
                    aria-label="오른쪽으로 이동"
                    className="flex h-6 w-6 items-center justify-center text-gray-400 hover:text-gray-700 disabled:opacity-30"
                  >
                    ▶
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => removeAt(index)}
                  aria-label="삭제"
                  className="flex h-6 w-6 items-center justify-center text-red-500 hover:text-red-700"
                >
                  ×
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
