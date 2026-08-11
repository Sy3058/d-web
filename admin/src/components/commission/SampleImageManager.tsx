import { useRef, useState } from 'react';
import type { CommissionItem } from '../../types';
import {
  useUpdateCommissionItem,
  useUploadCommissionSample,
} from '../../hooks/useCommissionItems';
import { describeAuthError } from '../../lib/api';
import { MAX_SAMPLES_PER_ITEM } from '../../lib/validation';
import { validateImageFile } from '../episodes/imageUpload';

interface SampleImageManagerProps {
  item: CommissionItem;
}

/** 카드 편집 화면 전용 샘플 이미지 관리 - 업로드·재배열·삭제.
 *
 * PR1 인계 계약(IMPLEMENTATION_COMMISSION_API.md): 재배열·삭제 PUT은 sample_image_keys
 * 기준으로 보내고, 렌더(썸네일 URL)는 sample_images를 쓴다. 이 컴포넌트는 항상
 * item.sample_image_keys에서 배열을 재구성해 PUT하고, item.sample_images로 그린다 -
 * 두 배열은 서버가 같은 순서로 보장한다(스키마 computed_field가 keys를 그대로 순회).
 */
export function SampleImageManager({ item }: SampleImageManagerProps) {
  const uploadSample = useUploadCommissionSample();
  const updateItem = useUpdateCommissionItem();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const atLimit = item.sample_image_keys.length >= MAX_SAMPLES_PER_ITEM;
  const busy = uploadSample.isPending || updateItem.isPending;

  const handleFilesSelected = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploadError(null);

    const remaining = MAX_SAMPLES_PER_ITEM - item.sample_image_keys.length;
    const selected = Array.from(files).slice(0, Math.max(remaining, 0));
    if (selected.length < files.length) {
      setUploadError(`카드당 샘플 이미지는 최대 ${MAX_SAMPLES_PER_ITEM}장입니다.`);
    }

    // 순차 업로드는 실패 지점 이후를 통째로 건너뛴다 - 몇 장이 올라갔는지 함께 알리지 않으면
    // 5장 중 3번째가 실패했을 때 4·5번째가 조용히 누락된 사실을 화면 어디서도 알 수 없다.
    const stopped = (reason: string, uploaded: number) =>
      selected.length > 1
        ? `${reason} (${selected.length}장 중 ${uploaded}장 업로드됨, 나머지는 중단)`
        : reason;

    let uploaded = 0;
    for (const file of selected) {
      const validationError = validateImageFile(file);
      if (validationError) {
        setUploadError(stopped(validationError, uploaded));
        break;
      }
      try {
        // Promise.all로 동시 전송하지 않는다 - 서버 append는 expected_len 기반 조건부
        // UPDATE인데 R2 업로드가 그보다 먼저 실행돼(PR1), 동시 요청은 R2엔 이미 올라간 채로
        // 조건부 UPDATE만 409로 실패한다. 그 객체는 매니페스트에 못 들어가 공개 버킷에
        // 미참조 파일로 남는다(IMPLEMENTATION_COMMISSION_SCREENS.md §3).
        await uploadSample.mutateAsync({ itemId: item.id, file });
        uploaded += 1;
      } catch (err) {
        setUploadError(stopped(describeAuthError(err), uploaded));
        break;
      }
    }

    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const reorderTo = (newKeys: string[]) => {
    updateItem.mutate({ itemId: item.id, body: { sample_image_keys: newKeys } });
  };

  const moveSample = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= item.sample_image_keys.length) return;
    const keys = [...item.sample_image_keys];
    [keys[index], keys[target]] = [keys[target], keys[index]];
    reorderTo(keys);
  };

  const deleteSample = (index: number) => {
    // 범위 밖이면 그냥 나간다. `sample && !confirm(...)`으로 묶으면 방어 조건이 역방향이 돼
    // (sample이 없을 때) 확인창을 건너뛰고 삭제 PUT까지 진행하는 모양이 된다.
    if (index < 0 || index >= item.sample_image_keys.length) return;
    if (!window.confirm('이 샘플 이미지를 삭제할까요?')) return;
    reorderTo(item.sample_image_keys.filter((_, i) => i !== index));
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          샘플 이미지 ({item.sample_image_keys.length}/{MAX_SAMPLES_PER_ITEM})
        </span>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={atLimit || busy}
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

      {uploadError && <p className="text-sm text-red-600">{uploadError}</p>}
      {updateItem.isError && (
        <p className="text-sm text-red-600">
          변경하지 못했습니다. {describeAuthError(updateItem.error)}
        </p>
      )}

      {item.sample_images.length === 0 ? (
        <p className="text-sm text-gray-500">등록된 샘플 이미지가 없습니다.</p>
      ) : (
        <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4">
          {item.sample_images.map((sample, index) => (
            <li key={sample.key} className="flex flex-col gap-1">
              <div className="aspect-square overflow-hidden rounded border border-gray-200 bg-gray-100">
                {sample.url ? (
                  <img src={sample.url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-[11px] text-gray-400">
                    미리보기 없음
                  </div>
                )}
              </div>
              <div className="flex items-center justify-between gap-1">
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => moveSample(index, -1)}
                    disabled={index === 0 || busy}
                    aria-label="왼쪽으로 이동"
                    className="flex h-6 w-6 items-center justify-center text-gray-400 hover:text-gray-700 disabled:opacity-30"
                  >
                    ◀
                  </button>
                  <button
                    type="button"
                    onClick={() => moveSample(index, 1)}
                    disabled={index === item.sample_images.length - 1 || busy}
                    aria-label="오른쪽으로 이동"
                    className="flex h-6 w-6 items-center justify-center text-gray-400 hover:text-gray-700 disabled:opacity-30"
                  >
                    ▶
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => deleteSample(index)}
                  disabled={busy}
                  aria-label="삭제"
                  className="flex h-6 w-6 items-center justify-center text-red-500 hover:text-red-700 disabled:opacity-30"
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
