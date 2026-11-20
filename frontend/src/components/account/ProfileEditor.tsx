import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import { z } from 'zod';
import { api, ApiError, extractDetail } from '@/lib/api';
import { getMe, type User } from '@/lib/auth';
import { FormError, TextField } from '@/components/ui/forms';
import { controlBase, ghostControl } from '@/components/ui/controlStyles';
import { safeProfileImageUrl } from './profileUtils';
import NoticeDialog from '@/components/ui/NoticeDialog';
import ProfileImageCropper from './ProfileImageCropper';

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const imageTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);
const nicknameSchema = z.string()
  .refine((value) => !/\p{C}/u.test(value), '닉네임에는 제어 문자를 사용할 수 없습니다.')
  .trim().min(1, '닉네임을 입력해 주세요.')
  .max(50, '닉네임은 50자 이하여야 합니다.');

export default function ProfileEditor({ initialUser }: { initialUser: User }) {
  const [user, setUser] = useState(initialUser);
  const [nickname, setNickname] = useState(initialUser.nickname);
  const [nicknameError, setNicknameError] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>();
  const [cropSource, setCropSource] = useState<string>();
  const [removeImage, setRemoveImage] = useState(false);
  const [failedImage, setFailedImage] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [needsLogin, setNeedsLogin] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreFailed, setRestoreFailed] = useState(false);
  const lock = useRef(false);
  const mounted = useRef(true);
  const generation = useRef(0);
  const pendingRequest = useRef<Promise<User> | null>(null);
  const previewRef = useRef<string | undefined>(undefined);
  const cropSourceRef = useRef<string | undefined>(undefined);
  const fileInput = useRef<HTMLInputElement>(null);
  const nicknameInput = useRef<HTMLInputElement>(null);
  const disabled = busy || needsLogin || restoreFailed;
  const image = preview ?? (removeImage ? undefined : safeProfileImageUrl(user.profile_image));
  const dirty = nickname !== user.nickname || file !== null || removeImage;

  const clearSelection = useCallback(() => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = undefined;
    setPreview(undefined);
    setFile(null);
    if (fileInput.current) fileInput.current.value = '';
  }, []);

  const closeCropper = useCallback(() => {
    if (cropSourceRef.current) URL.revokeObjectURL(cropSourceRef.current);
    cropSourceRef.current = undefined;
    setCropSource(undefined);
    if (fileInput.current) fileInput.current.value = '';
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current += 1;
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
      if (cropSourceRef.current) URL.revokeObjectURL(cropSourceRef.current);
      previewRef.current = undefined;
      cropSourceRef.current = undefined;
    };
  }, []);

  useEffect(() => {
    function resetDraft() {
      generation.current += 1;
      lock.current = false;
      setBusy(false);
      setRestoring(false);
      setRestoreFailed(false);
      setNickname(user.nickname);
      setNicknameError('');
      setError('');
      setNotice('');
      setRemoveImage(false);
      setFailedImage(undefined);
      clearSelection();
      closeCropper();
    }
    function pageHide() {
      mounted.current = false;
      resetDraft();
    }
    async function restoreAccount() {
      const pending = pendingRequest.current;
      resetDraft();
      mounted.current = true;
      const restoreGeneration = generation.current;
      lock.current = true;
      setBusy(true);
      setRestoring(true);
      try {
        // The previous write can still commit while the page is in BFCache.
        if (pending) await pending.catch(() => undefined);
        if (!mounted.current || restoreGeneration !== generation.current) return;
        const currentUser = await getMe();
        if (!mounted.current || restoreGeneration !== generation.current) return;
        if (!currentUser) {
          setNeedsLogin(true);
          setError('로그인이 만료됐어요. 다시 로그인해 주세요.');
          return;
        }
        setUser(currentUser);
        setNickname(currentUser.nickname);
        setNeedsLogin(false);
        window.dispatchEvent(new Event('dweb:account-updated'));
      } catch {
        if (!mounted.current || restoreGeneration !== generation.current) return;
        setRestoreFailed(true);
        setError('서버의 최신 계정 정보를 확인하지 못했어요. 페이지를 새로 열어 변경 여부를 확인해 주세요.');
      } finally {
        if (mounted.current && restoreGeneration === generation.current) {
          lock.current = false;
          setBusy(false);
          setRestoring(false);
        }
      }
    }
    function pageShow(event: PageTransitionEvent) {
      if (event.persisted) void restoreAccount();
    }
    window.addEventListener('pagehide', pageHide);
    window.addEventListener('pageshow', pageShow);
    return () => {
      window.removeEventListener('pagehide', pageHide);
      window.removeEventListener('pageshow', pageShow);
    };
  }, [user.nickname, clearSelection, closeCropper]);

  function applyCrop(cropped: File) {
    if (!mounted.current || !cropSource || cropSourceRef.current !== cropSource || lock.current || needsLogin || restoreFailed) return;
    clearSelection();
    const objectUrl = URL.createObjectURL(cropped);
    previewRef.current = objectUrl;
    setFile(cropped);
    setPreview(objectUrl);
    setRemoveImage(false);
    closeCropper();
  }

  function chooseImage(event: ChangeEvent<HTMLInputElement>) {
    if (lock.current || needsLogin || restoreFailed) return;
    const selected = event.target.files?.[0];
    if (!selected) return;
    setError('');
    setNotice('');
    if (!imageTypes.has(selected.type)) {
      setError('JPEG, PNG 또는 정적 WebP 이미지를 선택해 주세요.');
      return;
    }
    if (selected.size > MAX_IMAGE_BYTES) {
      setError('프로필 이미지는 최대 5MB까지 업로드할 수 있습니다.');
      return;
    }
    closeCropper();
    const objectUrl = URL.createObjectURL(selected);
    cropSourceRef.current = objectUrl;
    setCropSource(objectUrl);
  }

  async function saveProfile() {
    if (!mounted.current || lock.current || needsLogin || restoreFailed || !dirty || cropSource) return;
    const parsed = nicknameSchema.safeParse(nickname);
    if (!parsed.success) {
      setNicknameError(parsed.error.issues[0].message);
      return;
    }
    const requestGeneration = generation.current;
    lock.current = true;
    setBusy(true);
    setNicknameError('');
    setError('');
    setNotice('');
    let request: Promise<User> | undefined;
    try {
      const body = new FormData();
      body.append('nickname', parsed.data);
      if (file) body.append('file', file);
      if (removeImage) body.append('remove_image', 'true');
      request = api.put<User>('/auth/me/profile', undefined, { body });
      pendingRequest.current = request;
      const updated = await request;
      if (!mounted.current || requestGeneration !== generation.current) return;
      setUser(updated);
      setNickname(updated.nickname);
      clearSelection();
      setRemoveImage(false);
      setNotice('프로필 정보를 수정했어요.');
      window.dispatchEvent(new Event('dweb:account-updated'));
    } catch (cause) {
      if (!mounted.current || requestGeneration !== generation.current) return;
      if (cause instanceof ApiError) {
        if (cause.status === 401) {
          setNeedsLogin(true);
          clearSelection();
          closeCropper();
          setError('로그인이 만료됐어요. 다시 로그인해 주세요.');
        } else {
          setError(extractDetail(cause) ?? '저장하지 못했어요. 잠시 후 다시 시도해 주세요.');
        }
      } else {
        setError('통신 오류로 저장 결과를 확인하지 못했어요. 페이지를 새로 열어 변경 여부를 확인해 주세요.');
      }
    } finally {
      if (pendingRequest.current === request) pendingRequest.current = null;
      if (mounted.current && requestGeneration === generation.current) {
        lock.current = false;
        setBusy(false);
      }
    }
  }

  return (
    <form method="post" noValidate onSubmit={(event) => { event.preventDefault(); void saveProfile(); }} className="space-y-8">
      {error && <FormError message={error} />}
      <NoticeDialog open={Boolean(notice)} onOpenChange={(open) => { if (!open) setNotice(''); }} title="프로필 수정 완료" message={notice} returnFocus={nicknameInput} />
      {needsLogin && <a href="/auth/login" className={ghostControl} data-astro-reload>다시 로그인</a>}
      <fieldset disabled={disabled} className="space-y-8">
        <div>
          <h2 className="mb-5 text-sm font-medium text-ink">프로필 이미지</h2>
          <div className="flex items-start gap-4 sm:gap-6">
          <div className="relative h-24 w-24 shrink-0">
            <div className="flex h-full w-full items-center justify-center overflow-hidden rounded-full border border-line bg-hover text-muted">
              {image && failedImage !== image
                ? <img src={image} alt="프로필 이미지" className="h-full w-full object-cover" referrerPolicy="no-referrer" onError={() => setFailedImage(image)} />
                : <span aria-label="기본 프로필 이미지">{user.nickname.slice(0, 1)}</span>}
            </div>
            {(file || (!removeImage && user.profile_image)) && <button type="button" aria-label={file ? '선택 이미지 취소' : '프로필 이미지 삭제'} className={`${ghostControl} absolute -right-3 -top-3 bg-paper p-0 text-danger`} onClick={() => {
              if (lock.current || needsLogin || restoreFailed) return;
              if (file) clearSelection();
              else setRemoveImage(true);
              setNotice('');
            }}><span aria-hidden="true">×</span></button>}
          </div>
          <div className="min-w-0 flex-1">
          <label htmlFor="profile-image" className="mb-2 block text-sm text-ink">새 이미지 선택</label>
          <input ref={fileInput} id="profile-image" type="file" accept="image/jpeg,image/png,image/webp" onChange={chooseImage} aria-describedby="profile-image-helper" className="block w-full text-sm text-ink file:mr-3 file:min-h-11 file:rounded-control file:border-0 file:bg-hover file:px-3 file:text-ink" />
          <p id="profile-image-helper" className="mt-3 text-xs text-muted">JPEG·PNG·WebP, 최대 5MB. 위치와 크기를 조절한 뒤 선택 영역을 적용해 주세요.</p>
          {removeImage && <div className="mt-3 flex flex-wrap items-center gap-2"><p className="text-xs text-muted">저장하면 기존 프로필 이미지를 삭제해요.</p><button type="button" className={ghostControl} onClick={() => setRemoveImage(false)}>이미지 삭제 취소</button></div>}
          </div>
          </div>
          {cropSource && <ProfileImageCropper key={cropSource} imageSrc={cropSource} onApply={applyCrop} onCancel={closeCropper} returnFocus={fileInput} />}
        </div>
        <TextField ref={nicknameInput} id="profile-nickname" label="닉네임" autoComplete="nickname" value={nickname} maxLength={50} error={nicknameError} onChange={(event) => setNickname(event.target.value)} />
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-6">
          <button type="submit" disabled={disabled || !dirty || Boolean(cropSource)} className={`${controlBase} bg-ink px-5 py-2.5 text-paper hover:bg-ink-strong`}>{restoring ? '정보 확인 중...' : busy ? '저장 중...' : '변경 내용 저장'}</button>
          <a href="/my" className={ghostControl} aria-disabled={busy || undefined} onClick={(event) => { if (lock.current) event.preventDefault(); }} data-astro-reload>취소</a>
        </div>
      </fieldset>
    </form>
  );
}
