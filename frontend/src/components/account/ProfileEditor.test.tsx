// @vitest-environment jsdom
import { act, StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import type { User } from '@/lib/auth';
import ProfileEditor from './ProfileEditor';

const { put, getMe, cropCallbacks } = vi.hoisted(() => ({ put: vi.fn(), getMe: vi.fn(), cropCallbacks: [] as Array<(file: File) => void> }));
vi.mock('@/lib/api', async (original) => {
  const module = await original<typeof import('@/lib/api')>();
  return { ...module, api: { ...module.api, put } };
});
vi.mock('@/lib/auth', () => ({ getMe }));
vi.mock('./ProfileImageCropper', () => ({
  default: ({ onApply, onCancel }: { onApply: (file: File) => void; onCancel: () => void }) => {
    cropCallbacks.push(onApply);
    return (
    <div>
      <button type="button" onClick={() => onApply(new File(['cropped'], 'profile.png', { type: 'image/png' }))}>선택 영역 적용</button>
      <button type="button" onClick={onCancel}>자르기 취소</button>
    </div>
  ); },
}));
const user: User = {
  id: 'reader-1', email: 'reader@example.com', nickname: '독자', profile_image: null,
  role: 'reader', has_password: true, is_email_verified: true, created_at: '2026-11-16T00:00:00Z',
};
let root: Root;
let container: HTMLDivElement;
const revoke = vi.fn();
const createObjectUrl = vi.fn();
beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  cropCallbacks.length = 0;
  getMe.mockReset(); getMe.mockResolvedValue(user);
  put.mockReset(); revoke.mockReset(); createObjectUrl.mockReset(); createObjectUrl.mockReturnValue('blob:preview');
  const OriginalURL = URL;
  vi.stubGlobal('URL', class extends OriginalURL { static createObjectURL = createObjectUrl; static revokeObjectURL = revoke; });
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); });
async function render(initialUser = user) { await act(async () => root.render(<ProfileEditor initialUser={initialUser} />)); }
async function nickname(value: string) {
  await act(async () => {
    const field = container.querySelector<HTMLInputElement>('#profile-nickname')!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, value);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
async function choose(file: File, apply = true) {
  await act(async () => {
    const field = container.querySelector<HTMLInputElement>('#profile-image')!;
    Object.defineProperty(field, 'files', { configurable: true, value: [file] });
    field.dispatchEvent(new Event('change', { bubbles: true }));
  });
  const applyButton = Array.from(container.querySelectorAll<HTMLButtonElement>('button'))
    .find((button) => button.textContent === '선택 영역 적용');
  if (apply && applyButton) await act(async () => applyButton.click());
}
function saveButton() { return container.querySelector<HTMLButtonElement>('button[type="submit"]')!; }
async function save() { await act(async () => saveButton().click()); }
async function press(label: string) { await act(async () => container.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!.click()); }

async function transition(type: 'pagehide' | 'pageshow', persisted = true) {
  await act(async () => window.dispatchEvent(new PageTransitionEvent(type, { persisted })));
}

describe('프로필 편집', () => {
  it('자르기 적용 전에는 저장하지 않고 자르기 취소는 기존 프로필을 유지한다', async () => {
    await render({ ...user, profile_image: 'https://assets.example.com/old.webp' });
    await nickname('새 이름');
    await choose(new File(['raw'], 'raw.png', { type: 'image/png' }), false);
    expect(saveButton().disabled).toBe(true);
    expect(put).not.toHaveBeenCalled();
    const cancel = Array.from(container.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent === '자르기 취소')!;
    await act(async () => cancel.click());
    expect(container.querySelector('img')?.getAttribute('src')).toBe('https://assets.example.com/old.webp');
    expect(saveButton().disabled).toBe(false);
    expect(revoke).toHaveBeenCalledWith('blob:preview');
    expect(put).not.toHaveBeenCalled();
  });
  it('저장 성공 알림을 확인으로 닫고 다시 수정한 뒤 재사용한다', async () => {
    await render();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    put.mockResolvedValueOnce({ ...user, nickname: '첫 수정' });
    await nickname('첫 수정');
    await save();
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('프로필 정보를 수정했어요.');
    const confirm = Array.from(document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'))
      .find((button) => button.textContent === '확인')!;
    await act(async () => confirm.click());
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(container.querySelector<HTMLInputElement>('#profile-nickname')?.value).toBe('첫 수정');
    put.mockResolvedValueOnce({ ...user, nickname: '두 번째 수정' });
    await nickname('두 번째 수정');
    await save();
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('프로필 정보를 수정했어요.');
    expect(put).toHaveBeenCalledTimes(2);
  });

  it('저장 실패는 성공 모달을 띄우지 않는다', async () => {
    put.mockRejectedValueOnce(new ApiError(422, '{"detail":"저장할 수 없어요"}'));
    await render();
    await nickname('수정');
    await save();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(container.textContent).toContain('저장할 수 없어요');
  });
  it('이미지와 닉네임을 미리 편집하고 저장할 때만 한 요청으로 보낸다', async () => {
    put.mockResolvedValue({ ...user, nickname: '새 독자', profile_image: 'https://assets.example.com/new.webp' });
    const updated = vi.fn(); window.addEventListener('dweb:account-updated', updated);
    try {
      await render(); await nickname('  새 독자  '); await choose(new File(['image'], 'image.png', { type: 'image/png' }));
      expect(put).not.toHaveBeenCalled(); expect(container.querySelector('img')?.getAttribute('src')).toBe('blob:preview');
      await save();
      expect(put).toHaveBeenCalledOnce();
      const [path, json, options] = put.mock.calls[0];
      expect(path).toBe('/auth/me/profile'); expect(json).toBeUndefined(); expect(options.headers).toBeUndefined();
      expect(options.body).toBeInstanceOf(FormData); expect(options.body.get('nickname')).toBe('새 독자');
      expect(options.body.get('file').name).toBe('profile.png'); expect(options.body.has('remove_image')).toBe(false);
      expect(container.querySelector<HTMLInputElement>('#profile-nickname')!.value).toBe('새 독자');
      expect(container.querySelector('img')?.getAttribute('src')).toBe('https://assets.example.com/new.webp');
      expect(updated).toHaveBeenCalledOnce(); expect(revoke).toHaveBeenCalledWith('blob:preview');
      expect(saveButton().disabled).toBe(true); expect(document.querySelector('[role="dialog"]')?.textContent).toContain('프로필 정보를 수정했어요.');
    } finally { window.removeEventListener('dweb:account-updated', updated); }
  });

  it('닉네임만 저장하면 이미지 변경이나 제거를 보내지 않는다', async () => {
    put.mockResolvedValue({ ...user, nickname: '새 독자' });
    await render(); await nickname('새 독자'); await save();
    const body = put.mock.calls[0][2].body;
    expect(Array.from(body.keys())).toEqual(['nickname']);
  });

  it('취소 링크는 계정으로 이동하고 화면을 벗어나면 미저장 이미지를 폐기한다', async () => {
    await render(); await nickname('미저장'); await choose(new File(['a'], 'a.png', { type: 'image/png' }));
    const cancel = container.querySelector('a[href="/my"]'); expect(cancel?.textContent).toBe('취소'); expect(cancel?.hasAttribute('data-astro-reload')).toBe(true);
    await act(async () => root.render(<div />));
    expect(revoke).toHaveBeenCalledWith('blob:preview'); expect(put).not.toHaveBeenCalled();
  });

  it('기존 이미지는 X로 제거할 수 있고 저장 전에는 서버를 바꾸지 않는다', async () => {
    put.mockResolvedValue(user);
    await render({ ...user, profile_image: 'https://assets.example.com/old.webp' });
    await press('프로필 이미지 삭제');
    expect(container.querySelector('img')).toBeNull(); expect(put).not.toHaveBeenCalled();
    expect(container.textContent).toContain('저장하면 기존 프로필 이미지를 삭제');
    await save();
    const body = put.mock.calls[0][2].body;
    expect(body.get('nickname')).toBe('독자'); expect(body.get('remove_image')).toBe('true'); expect(body.has('file')).toBe(false);
  });

  it('선택 이미지의 X는 선택만 취소하고 기존 이미지를 복원한다', async () => {
    await render({ ...user, profile_image: 'https://assets.example.com/old.webp' });
    await choose(new File(['a'], 'a.png', { type: 'image/png' })); await press('선택 이미지 취소');
    expect(container.querySelector('img')?.getAttribute('src')).toBe('https://assets.example.com/old.webp');
    expect(revoke).toHaveBeenCalledWith('blob:preview'); expect(saveButton().disabled).toBe(true); expect(put).not.toHaveBeenCalled();
  });

  it('이미지 삭제 취소와 새 이미지 선택은 제거 요청을 남기지 않는다', async () => {
    put.mockResolvedValue({ ...user, profile_image: 'https://assets.example.com/new.webp' });
    await render({ ...user, profile_image: 'https://assets.example.com/old.webp' }); await press('프로필 이미지 삭제');
    await act(async () => Array.from(container.querySelectorAll('button')).find((item) => item.textContent === '이미지 삭제 취소')!.click());
    expect(saveButton().disabled).toBe(true); await press('프로필 이미지 삭제');
    await choose(new File(['a'], 'a.png', { type: 'image/png' })); await save();
    expect(put.mock.calls[0][2].body.has('remove_image')).toBe(false); expect(put.mock.calls[0][2].body.has('file')).toBe(true);
  });

  it('빈 닉네임과 제어 문자는 서버에 보내지 않는다', async () => {
    await render(); await nickname('   '); await save(); expect(container.textContent).toContain('닉네임을 입력해 주세요.');
    await nickname('독자\u200b'); await save(); expect(container.textContent).toContain('제어 문자'); expect(put).not.toHaveBeenCalled();
  });

  it('잘못된 파일 형식과 5MB 초과 파일은 저장 대상으로 선택하지 않는다', async () => {
    await render(); await choose(new File(['gif'], 'a.gif', { type: 'image/gif' })); expect(container.textContent).toContain('JPEG, PNG 또는 정적 WebP');
    await choose(new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'a.png', { type: 'image/png' })); expect(container.textContent).toContain('최대 5MB');
    expect(createObjectUrl).not.toHaveBeenCalled(); expect(put).not.toHaveBeenCalled(); expect(saveButton().disabled).toBe(true);
  });

  it('파일을 바꾸면 이전 미리보기를 해제한다', async () => {
    await render(); await choose(new File(['a'], 'a.png', { type: 'image/png' })); createObjectUrl.mockReturnValue('blob:second');
    await choose(new File(['b'], 'b.png', { type: 'image/png' })); expect(revoke).toHaveBeenCalledWith('blob:preview');
    expect(container.querySelector('img')?.getAttribute('src')).toBe('blob:second');
  });

  it('동일 tick 중복 저장을 막고 요청 중 입력을 잠근다', async () => {
    let finish!: (value: User) => void; put.mockReturnValue(new Promise<User>((resolve) => { finish = resolve; }));
    await render(); await nickname('새 독자');
    await act(async () => { saveButton().click(); saveButton().click(); }); expect(put).toHaveBeenCalledOnce();
    expect(container.querySelector('fieldset')?.disabled).toBe(true);
    await act(async () => finish({ ...user, nickname: '새 독자' })); expect(container.querySelector('fieldset')?.disabled).toBe(false);
  });

  it('서버 검증 실패는 닉네임과 이미지 초안을 유지한다', async () => {
    put.mockRejectedValue(new ApiError(422, '{"detail":"이미지를 확인해 주세요"}'));
    await render(); await nickname('새 독자'); await choose(new File(['a'], 'a.png', { type: 'image/png' })); await save();
    expect(container.textContent).toContain('이미지를 확인해 주세요'); expect(container.querySelector<HTMLInputElement>('#profile-nickname')!.value).toBe('새 독자');
    expect(container.querySelector('img')?.getAttribute('src')).toBe('blob:preview'); expect(saveButton().disabled).toBe(false);
  });

  it('통신 오류는 저장 결과를 단정하지 않고 최종 401은 초안을 정리한다', async () => {
    put.mockRejectedValueOnce(new TypeError('network')); await render(); await nickname('새 독자'); await save();
    expect(container.textContent).toContain('저장 결과를 확인하지 못했어요');
    await choose(new File(['a'], 'a.png', { type: 'image/png' })); put.mockRejectedValueOnce(new ApiError(401, 'unauthenticated')); await save();
    expect(container.textContent).toContain('로그인이 만료됐어요'); expect(revoke).toHaveBeenCalledWith('blob:preview');
    expect(container.querySelector('a[href="/auth/login"]')).not.toBeNull(); expect(saveButton().disabled).toBe(true);
  });

  it('화면 종료 뒤 늦은 성공 응답으로 이벤트나 UI를 갱신하지 않는다', async () => {
    let finish!: (value: User) => void; put.mockReturnValue(new Promise<User>((resolve) => { finish = resolve; }));
    const updated = vi.fn(); window.addEventListener('dweb:account-updated', updated);
    try {
      await render(); await nickname('새 독자'); await save(); await act(async () => root.render(<div />));
      await act(async () => finish({ ...user, nickname: '새 독자' })); expect(updated).not.toHaveBeenCalled();
    } finally { window.removeEventListener('dweb:account-updated', updated); }
  });

  it.each(['applied', 'raw', 'remove'] as const)('BFCache에서 %s 이미지 초안과 닉네임을 버리고 저장 기준을 복원한다', async (draft) => {
    getMe.mockResolvedValue({ ...user, profile_image: 'https://assets.example.com/old.webp' });
    await render({ ...user, profile_image: 'https://assets.example.com/old.webp' });
    await nickname('미저장');
    if (draft === 'remove') await press('프로필 이미지 삭제');
    else {
      createObjectUrl.mockReturnValueOnce('blob:raw').mockReturnValueOnce('blob:cropped');
      await choose(new File(['raw'], 'raw.png', { type: 'image/png' }), draft === 'applied');
    }
    await transition('pageshow', false);
    expect(container.querySelector<HTMLInputElement>('#profile-nickname')!.value).toBe('미저장');
    expect(getMe).not.toHaveBeenCalled();
    await transition('pagehide');
    expect(container.querySelector<HTMLInputElement>('#profile-nickname')!.value).toBe(user.nickname);
    if (draft !== 'remove') expect(revoke).toHaveBeenCalledWith('blob:raw');
    if (draft === 'applied') expect(revoke).toHaveBeenCalledWith('blob:cropped');
    await transition('pageshow');
    expect(container.querySelector('img')?.getAttribute('src')).toBe('https://assets.example.com/old.webp');
    expect(container.querySelector<HTMLInputElement>('#profile-image')!.value).toBe('');
    expect(container.textContent).not.toContain('저장하면 기존 프로필 이미지를 삭제');
    expect(container.textContent).not.toContain('선택 영역 적용');
    expect(saveButton().disabled).toBe(true);
    expect(put).not.toHaveBeenCalled();
  });

  it('pagehide에서 적용 미리보기와 새 자르기 원본 URL을 모두 즉시 해제하고 늦은 자르기를 무시한다', async () => {
    await render();
    createObjectUrl.mockReturnValueOnce('blob:first-raw').mockReturnValueOnce('blob:applied').mockReturnValueOnce('blob:second-raw');
    await choose(new File(['first'], 'first.png', { type: 'image/png' }));
    await choose(new File(['second'], 'second.png', { type: 'image/png' }), false);
    const apply = cropCallbacks.at(-1)!;
    revoke.mockClear();
    await transition('pagehide');
    expect(revoke.mock.calls).toEqual([['blob:applied'], ['blob:second-raw']]);
    await act(async () => apply(new File(['late'], 'late.png', { type: 'image/png' })));
    expect(createObjectUrl).toHaveBeenCalledTimes(3);
    await transition('pageshow');
    expect(container.querySelector('img')).toBeNull();
    expect(put).not.toHaveBeenCalled();
  });

  it('복귀는 이미지 실패를 지우고 최신 조회가 익명이면 재로그인을 요구한다', async () => {
    getMe.mockResolvedValue(null);
    await render({ ...user, profile_image: 'https://assets.example.com/old.webp' });
    await act(async () => container.querySelector('img')!.dispatchEvent(new Event('error')));
    expect(container.querySelector('img')).toBeNull();
    await nickname('수정'); put.mockRejectedValueOnce(new ApiError(401, 'unauthenticated')); await save();
    await transition('pagehide'); await transition('pageshow');
    expect(container.querySelector('img')?.getAttribute('src')).toBe('https://assets.example.com/old.webp');
    expect(container.textContent).toContain('로그인이 만료됐어요');
    expect(container.querySelector('a[href="/auth/login"]')).not.toBeNull();
    expect(container.querySelector('fieldset')!.disabled).toBe(true);
  });

  it('BFCache 복귀는 저장 성공한 최신 프로필을 유지하고 알림과 검증 오류를 정리한다', async () => {
    getMe.mockResolvedValue({ ...user, nickname: '저장됨', profile_image: 'https://assets.example.com/saved.webp' });
    put.mockResolvedValue({ ...user, nickname: '저장됨', profile_image: 'https://assets.example.com/saved.webp' });
    await render(); await nickname('저장됨'); await save();
    await transition('pagehide'); await transition('pageshow');
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    await nickname(' '); await save();
    expect(container.textContent).toContain('닉네임을 입력해 주세요.');
    await transition('pagehide'); await transition('pageshow');
    expect(container.querySelector<HTMLInputElement>('#profile-nickname')!.value).toBe('저장됨');
    expect(container.querySelector('img')?.getAttribute('src')).toBe('https://assets.example.com/saved.webp');
    expect(container.textContent).not.toContain('닉네임을 입력해 주세요.');
    expect(put).toHaveBeenCalledOnce();
  });

  it.each(['resolve', 'reject'] as const)('복원은 이전 요청 %s를 기다리고 최신 서버 닉네임으로 이미지 변경을 저장한다', async (outcome) => {
    let resolveOld!: (value: User) => void; let rejectOld!: (cause: unknown) => void; let resolveGet!: (value: User) => void;
    put.mockReturnValueOnce(new Promise<User>((resolve, reject) => { resolveOld = resolve; rejectOld = reject; }))
      .mockResolvedValueOnce({ ...user, nickname: '최신 서버 이름' });
    getMe.mockReturnValueOnce(new Promise<User>((resolve) => { resolveGet = resolve; }));
    const updated = vi.fn(); window.addEventListener('dweb:account-updated', updated);
    try {
      await render({ ...user, profile_image: 'https://assets.example.com/old.webp' }); await nickname('새 이름'); await save();
      await transition('pagehide'); await transition('pageshow');
      expect(saveButton().textContent).toBe('정보 확인 중...');
      expect(container.querySelector('fieldset')!.disabled).toBe(true);
      expect(getMe).not.toHaveBeenCalled();
      await save(); expect(put).toHaveBeenCalledOnce();
      await act(async () => { if (outcome === 'resolve') resolveOld({ ...user, nickname: '새 이름' }); else rejectOld(new ApiError(401, 'unauthenticated')); });
      expect(getMe).toHaveBeenCalledOnce();
      expect(container.querySelector('fieldset')!.disabled).toBe(true);
      expect(document.querySelector('[role="dialog"]')).toBeNull();
      expect(updated).not.toHaveBeenCalled();
      const cancel = new MouseEvent('click', { bubbles: true, cancelable: true });
      await act(async () => container.querySelector('a[href="/my"]')!.dispatchEvent(cancel));
      expect(cancel.defaultPrevented).toBe(true);
      await act(async () => resolveGet({ ...user, nickname: '최신 서버 이름', profile_image: 'https://assets.example.com/old.webp' }));
      expect(container.querySelector('fieldset')!.disabled).toBe(false);
      expect(container.querySelector<HTMLInputElement>('#profile-nickname')!.value).toBe('최신 서버 이름');
      expect(updated).toHaveBeenCalledOnce();
      await press('프로필 이미지 삭제'); await save();
      expect(put).toHaveBeenCalledTimes(2);
      expect(put.mock.calls[1][2].body.get('nickname')).toBe('최신 서버 이름');
      expect(put.mock.calls[1][2].body.get('remove_image')).toBe('true');
    } finally { window.removeEventListener('dweb:account-updated', updated); }
  });

  it('pagehide 중 요청이 이미 완료돼도 복원 시 최신 서버 기준을 조회한다', async () => {
    let finish!: (value: User) => void; put.mockReturnValueOnce(new Promise<User>((resolve) => { finish = resolve; }));
    await render(); await nickname('서버 저장됨'); await save(); await transition('pagehide');
    await act(async () => finish({ ...user, nickname: '서버 저장됨' }));
    getMe.mockResolvedValueOnce({ ...user, nickname: '서버 저장됨' });
    await transition('pageshow');
    expect(getMe).toHaveBeenCalledOnce();
    expect(container.querySelector<HTMLInputElement>('#profile-nickname')!.value).toBe('서버 저장됨');
  });

  it('복원 조회 실패는 이전 기준으로 저장하지 못하게 잠그고 새 페이지 확인을 안내한다', async () => {
    getMe.mockRejectedValueOnce(new TypeError('network'));
    await render(); await nickname('미저장'); await transition('pagehide'); await transition('pageshow');
    expect(container.textContent).toContain('페이지를 새로 열어 변경 여부를 확인');
    expect(container.querySelector('fieldset')!.disabled).toBe(true);
    await save(); expect(put).not.toHaveBeenCalled();
  });

  it.each(['resolve', 'reject'] as const)('이전 복원 조회의 늦은 %s는 다음 복원 잠금과 결과를 바꾸지 않는다', async (outcome) => {
    let resolveOld!: (value: User) => void; let rejectOld!: (cause: unknown) => void; let resolveNew!: (value: User) => void;
    getMe.mockReturnValueOnce(new Promise<User>((resolve, reject) => { resolveOld = resolve; rejectOld = reject; }))
      .mockReturnValueOnce(new Promise<User>((resolve) => { resolveNew = resolve; }));
    await render(); await transition('pagehide'); await transition('pageshow');
    await transition('pagehide'); await transition('pageshow');
    await act(async () => { if (outcome === 'resolve') resolveOld({ ...user, nickname: '이전 복원' }); else rejectOld(new TypeError('network')); });
    expect(container.querySelector('fieldset')!.disabled).toBe(true);
    expect(container.textContent).not.toContain('페이지를 새로 열어');
    expect(container.querySelector<HTMLInputElement>('#profile-nickname')!.value).toBe(user.nickname);
    await act(async () => resolveNew({ ...user, nickname: '최신 복원' }));
    expect(container.querySelector('fieldset')!.disabled).toBe(false);
    expect(container.querySelector<HTMLInputElement>('#profile-nickname')!.value).toBe('최신 복원');
  });

  it('언마운트 뒤 복원 조회가 완료되어도 이벤트를 보내지 않는다', async () => {
    let finish!: (value: User) => void; getMe.mockReturnValueOnce(new Promise<User>((resolve) => { finish = resolve; }));
    const updated = vi.fn(); window.addEventListener('dweb:account-updated', updated);
    try {
      await render(); await transition('pageshow'); await act(async () => root.render(<div />));
      await act(async () => finish(user)); expect(updated).not.toHaveBeenCalled();
    } finally { window.removeEventListener('dweb:account-updated', updated); }
  });

  it('늦은 자르기 결과를 무시하고 StrictMode 재설정 뒤 페이지 리스너를 제거한다', async () => {
    await act(async () => root.render(<StrictMode><ProfileEditor initialUser={user} /></StrictMode>));
    await choose(new File(['raw'], 'raw.png', { type: 'image/png' }), false);
    const apply = cropCallbacks.at(-1)!;
    await transition('pagehide'); await transition('pageshow');
    await act(async () => apply(new File(['late'], 'late.png', { type: 'image/png' })));
    expect(createObjectUrl).toHaveBeenCalledOnce();
    expect(container.querySelector('img')).toBeNull();
    const remove = vi.spyOn(window, 'removeEventListener');
    await act(async () => root.render(<div />));
    expect(remove).toHaveBeenCalledWith('pagehide', expect.any(Function));
    expect(remove).toHaveBeenCalledWith('pageshow', expect.any(Function));
    remove.mockRestore();
  });

  it('기존 이미지의 실행 가능 스킴은 표시하지 않는다', async () => {
    await render({ ...user, profile_image: 'javascript:alert(1)' }); expect(container.querySelector('img')).toBeNull();
  });
});
