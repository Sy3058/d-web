import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import {
  useArtistProfile,
  useUpdateArtistProfile,
  useUploadArtistProfileImage,
} from '../../hooks/useArtistProfile';
import { describeAuthError } from '../../lib/api';
import {
  ARTIST_NAME_MAX,
  artistProfileSchema,
  type ArtistProfileInput,
} from '../../lib/validation';
import type { ArtistProfile, ArtistProfileUpdate } from '../../types';
import { ImageCropModal } from '../common/ImageCropModal';

export function ArtistProfileEditor() {
  const { data, isLoading, isError, error } = useArtistProfile();

  return (
    <section className="flex flex-col gap-3 rounded border border-gray-200 p-4">
      <div>
        <h2 className="font-medium">작가 프로필</h2>
        <p className="text-xs text-gray-500">
          메인 작가 소개에 표시할 이름, 프로필 이미지와 외부 채널을 설정합니다. 사이트
          브랜드명은 도군으로 유지됩니다.
        </p>
      </div>
      {isLoading && <p className="text-sm text-gray-500">불러오는 중...</p>}
      {isError && <p className="text-sm text-red-600">{describeAuthError(error)}</p>}
      {data && <ArtistProfileForm data={data} />}
    </section>
  );
}

function ArtistProfileForm({ data }: { data: ArtistProfile }) {
  const updateProfile = useUpdateArtistProfile();
  const uploadImage = useUploadArtistProfileImage();
  const [isCropModalOpen, setCropModalOpen] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ArtistProfileInput>({
    resolver: zodResolver(artistProfileSchema),
    defaultValues: {
      name: data.name,
      twitter_url: data.twitter_url ?? '',
      postype_url: data.postype_url ?? '',
    },
  });

  const onSubmit = (values: ArtistProfileInput) => {
    const body: ArtistProfileUpdate = {
      name: values.name,
      twitter_url: values.twitter_url || null,
      postype_url: values.postype_url || null,
    };
    updateProfile.mutate(body);
  };

  const fields: Array<{
    name: keyof ArtistProfileInput;
    label: string;
    placeholder: string;
    maxLength?: number;
  }> = [
    { name: 'name', label: '작가명', placeholder: '도군', maxLength: ARTIST_NAME_MAX },
    { name: 'twitter_url', label: 'Twitter URL', placeholder: 'https://twitter.com/account' },
    { name: 'postype_url', label: 'Postype URL', placeholder: 'https://account.postype.com' },
  ];

  const handleImageCropComplete = async (file: File) => {
    setImageError(null);
    try {
      await uploadImage.mutateAsync(file);
    } catch (error) {
      setImageError(describeAuthError(error));
    } finally {
      setCropModalOpen(false);
    }
  };

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)}>
      <div className="flex items-center gap-4">
        <div className="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-full bg-gray-100 text-sm text-gray-400">
          {data.profile_image_url ? (
            <img src={data.profile_image_url} alt="현재 프로필" className="h-full w-full object-cover" />
          ) : (
            '이미지 없음'
          )}
        </div>
        <div className="flex flex-col items-start gap-2">
          <button
            type="button"
            disabled={uploadImage.isPending}
            onClick={() => setCropModalOpen(true)}
            className="rounded border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            {uploadImage.isPending ? '업로드 중...' : '프로필 이미지 업로드'}
          </button>
          <p className="text-xs text-gray-500">1:1로 조정한 뒤 WebP로 변환됩니다.</p>
          {imageError && <p className="text-xs text-red-600">{imageError}</p>}
        </div>
      </div>
      {fields.map((field) => (
        <label key={field.name} className="flex flex-col gap-1 text-sm">
          <span>{field.label}</span>
          <input
            {...register(field.name)}
            type={field.name === 'name' ? 'text' : 'url'}
            placeholder={field.placeholder}
            maxLength={field.maxLength}
            className="rounded border border-gray-300 px-3 py-2"
          />
          {errors[field.name] && (
            <span className="text-xs text-red-600">{errors[field.name]?.message}</span>
          )}
        </label>
      ))}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={updateProfile.isPending}
          className="rounded bg-gray-900 px-3 py-2 text-sm text-white disabled:opacity-50"
        >
          {updateProfile.isPending ? '저장 중...' : '프로필 저장'}
        </button>
      </div>
      {updateProfile.isError && (
        <p className="text-sm text-red-600">
          저장하지 못했습니다. {describeAuthError(updateProfile.error)}
        </p>
      )}
      {isCropModalOpen && (
        <ImageCropModal
          title="프로필 이미지 설정"
          aspect={1}
          cropShape="round"
          outputFileName="profile.jpg"
          onClose={() => setCropModalOpen(false)}
          onComplete={handleImageCropComplete}
        />
      )}
    </form>
  );
}
