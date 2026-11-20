// @vitest-environment jsdom
import { act, useRef, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import type { ComponentProps } from 'react';
import type Cropper from 'react-easy-crop';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ProfileImageCropper from './ProfileImageCropper';

const state = vi.hoisted(() => ({ cropper: null as ComponentProps<typeof Cropper> | null, crop: vi.fn() }));
vi.mock('react-easy-crop', () => ({ default: (props: ComponentProps<typeof Cropper>) => { state.cropper = props; return <div data-cropper />; } }));
vi.mock('@/lib/profileCrop', () => ({ getProfileCroppedFile: state.crop }));
let root: Root;
let container: HTMLDivElement;
const onApply = vi.fn();
const onCancel = vi.fn();
const area = { x: 30, y: 20, width: 100, height: 100 };
const file = new File(['crop'], 'profile.png', { type: 'image/png' });
beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  state.crop.mockReset(); state.cropper = null; onApply.mockReset(); onCancel.mockReset();
  state.crop.mockResolvedValue(file);
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
async function render(src = 'blob:source') { await act(async () => root.render(<ProfileImageCropper imageSrc={src} onApply={onApply} onCancel={onCancel} />)); }
async function select() { await act(async () => state.cropper!.onCropComplete?.(area, area)); }
function popup() { return document.querySelector<HTMLElement>('[role="dialog"]')!; }
function apply() { return Array.from(popup().querySelectorAll('button')).find((button) => ['선택 영역 적용', '처리 중...'].includes(button.textContent ?? ''))!; }
async function click() { await act(async () => apply().click()); }
describe('프로필 이미지 자르기', () => {
  it('원형 선택과 확대 범위를 제공하고 선택 전에는 적용을 막는다', async () => {
    await render();
    expect(apply().disabled).toBe(true);
    expect(state.cropper).toMatchObject({ image: 'blob:source', aspect: 1, cropShape: 'round', crop: { x: 0, y: 0 }, zoom: 1, minZoom: 1, maxZoom: 3 });
    const range = popup().querySelector<HTMLInputElement>('input')!;
    expect(range.labels?.[0].textContent).toContain('확대/축소');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(range, '2');
      range.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(state.cropper!.zoom).toBe(2);
    await act(async () => state.cropper!.onZoomChange?.(2.5));
    expect(range.value).toBe('2.5');
    await select(); await click();
    expect(state.crop).toHaveBeenCalledWith('blob:source', area);
    expect(onApply).toHaveBeenCalledWith(file);
    expect(apply().type).toBe('button');
  });
  it('실패를 안내하고 재시도할 수 있다', async () => {
    state.crop.mockRejectedValueOnce(new Error('canvas failed'));
    await render(); await select(); await click();
    expect(popup().querySelector('[role="alert"]')?.textContent).toContain('다시 시도');
    expect(onApply).not.toHaveBeenCalled();
    await click(); expect(onApply).toHaveBeenCalledWith(file);
    expect(popup().querySelector('[role="alert"]')).toBeNull();
  });
  it('원본 로드 실패를 안내하고 적용을 막는다', async () => {
    await render(); await select();
    await act(async () => state.cropper!.mediaProps?.onError?.({} as never));
    expect(popup().querySelector('[role="alert"]')?.textContent).toContain('이미지를 불러오지 못했어요');
    expect(apply().disabled).toBe(true);
    expect(state.crop).not.toHaveBeenCalled();
    expect(state.cropper!.cropperProps?.['aria-label']).toBe('이미지 위치 조절');
  });
  it('처리 중 중복 적용을 막고 해제 뒤에는 늦은 결과를 무시한다', async () => {
    let resolve!: (file: File) => void;
    state.crop.mockReturnValue(new Promise<File>((done) => { resolve = done; }));
    await render(); await select(); await click(); await click();
    expect(state.crop).toHaveBeenCalledTimes(1); expect(apply().disabled).toBe(true);
    await act(async () => root.render(null));
    await act(async () => resolve(file));
    expect(onApply).not.toHaveBeenCalled();
  });
  it('다른 원본으로 바뀌면 좌표를 초기화하고 이전 결과를 무시한다', async () => {
    let resolve!: (file: File) => void;
    state.crop.mockReturnValue(new Promise<File>((done) => { resolve = done; }));
    await render(); await select(); await click(); await render('blob:next');
    expect(apply().disabled).toBe(true); expect(state.cropper!.zoom).toBe(1);
    await act(async () => resolve(file)); expect(onApply).not.toHaveBeenCalled();
  });
  it('취소는 부모에게 전달한다', async () => {
    await render();
    await act(async () => Array.from(popup().querySelectorAll('button')).find((button) => button.textContent === '자르기 취소')!.click());
    expect(onCancel).toHaveBeenCalledOnce(); expect(state.crop).not.toHaveBeenCalled();
  });
});

async function outsideClick() {
  const backdrop = document.querySelector<HTMLElement>('.fixed[role="presentation"]')!;
  await act(async () => {
    backdrop.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    backdrop.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    backdrop.click();
  });
}
async function escape() {
  await act(async () => popup().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
}
function FocusHarness() {
  const [open, setOpen] = useState(true);
  const returnFocus = useRef<HTMLInputElement>(null);
  return <><input aria-label="새 이미지 선택" ref={returnFocus} />{open && <ProfileImageCropper imageSrc="blob:source" onApply={onApply} onCancel={() => setOpen(false)} returnFocus={returnFocus} />}</>;
}
describe('자르기 모달', () => {
  it('제목과 설명을 연결하고 확대 입력으로 포커스를 이동한다', async () => {
    await render();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
    expect(document.getElementById(popup().getAttribute('aria-labelledby')!)?.textContent).toBe('프로필 이미지 자르기');
    expect(document.getElementById(popup().getAttribute('aria-describedby')!)?.textContent).toContain('이미지를 움직이거나 확대');
    expect(document.activeElement).toBe(popup().querySelector('input[type="range"]'));
  });
  it('닫기 버튼은 취소를 전달한다', async () => {
    await render();
    await act(async () => popup().querySelector<HTMLButtonElement>('button[aria-label="닫기"]')!.click());
    expect(onCancel).toHaveBeenCalledOnce();
  });
  it('Escape는 취소를 전달한다', async () => {
    await render(); await escape(); expect(onCancel).toHaveBeenCalledOnce();
  });
  it('바깥 클릭은 취소를 전달한다', async () => {
    await render(); await outsideClick(); expect(onCancel).toHaveBeenCalledOnce();
  });
  it('처리 중 닫기와 취소, Escape와 바깥 클릭을 막는다', async () => {
    let resolve!: (file: File) => void;
    state.crop.mockReturnValue(new Promise<File>((done) => { resolve = done; }));
    await render(); await select(); await click();
    const close = popup().querySelector<HTMLButtonElement>('button[aria-label="닫기"]')!;
    const cancel = Array.from(popup().querySelectorAll('button')).find((button) => button.textContent === '자르기 취소')!;
    expect(close.disabled).toBe(true); expect(cancel.disabled).toBe(true);
    await act(async () => { close.click(); cancel.click(); });
    await escape(); await outsideClick(); expect(onCancel).not.toHaveBeenCalled();
    await act(async () => resolve(file)); expect(onApply).toHaveBeenCalledWith(file);
  });
  it('취소 후 부모가 모달을 해제하면 파일 입력으로 포커스를 돌린다', async () => {
    await act(async () => root.render(<FocusHarness />));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
    await escape();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(container.querySelector('input'));
  });
});
