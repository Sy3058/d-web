// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getProfileCroppedFile } from './profileCrop';

let width: number;
let height: number;
let failLoad: boolean;
const drawImage = vi.fn();
beforeEach(() => {
  width = 800; height = 600; failLoad = false; drawImage.mockReset();
  vi.stubGlobal('Image', class {
    naturalWidth = width;
    naturalHeight = height;
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    set src(_value: string) { queueMicrotask(() => failLoad ? this.onerror?.() : this.onload?.()); }
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => {
    return { drawImage } as unknown as CanvasRenderingContext2D;
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((callback) => callback(new Blob(['png'], { type: 'image/png' })));
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const area = { x: 100, y: 50, width: 300, height: 300 };
describe('프로필 이미지 재인코딩', () => {
  it('선택 좌표를 256px PNG 파일로 그린다', async () => {
    const file = await getProfileCroppedFile('blob:source', area);
    expect(file.name).toBe('profile.png'); expect(file.type).toBe('image/png');
    expect(file.size).toBe(3);
    const canvas = vi.mocked(HTMLCanvasElement.prototype.getContext).mock.contexts[0] as HTMLCanvasElement;
    expect(canvas.width).toBe(256); expect(canvas.height).toBe(256);
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 100, 50, 300, 300, 0, 0, 256, 256);
    expect(canvas.toBlob).toHaveBeenCalledWith(expect.any(Function), 'image/png');
  });
  it('1px 반올림 차이를 가운데 정사각형으로 보정한다', async () => {
    await getProfileCroppedFile('blob:source', { ...area, width: 301 });
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 100.5, 50, 300, 300, 0, 0, 256, 256);
  });
  it.each([
    { ...area, x: NaN }, { ...area, y: -1 }, { ...area, width: 0 },
    { ...area, height: Infinity }, { ...area, height: 302 },
    { ...area, x: 501 }, { ...area, y: 301 },
  ])('잘못된 영역을 거부한다: %o', async (invalid) => {
    await expect(getProfileCroppedFile('blob:source', invalid)).rejects.toThrow();
    expect(drawImage).not.toHaveBeenCalled();
  });
  it.each([[0, 600], [4001, 4000]])('유효하지 않거나 16Mpx 초과인 이미지를 거부한다', async (w, h) => {
    width = w; height = h;
    await expect(getProfileCroppedFile('blob:source', area)).rejects.toThrow();
    expect(drawImage).not.toHaveBeenCalled();
  });
  it('디코딩 오류를 반환한다', async () => {
    failLoad = true;
    await expect(getProfileCroppedFile('blob:source', area)).rejects.toThrow();
  });
  it('canvas context 실패를 반환한다', async () => {
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(null);
    await expect(getProfileCroppedFile('blob:source', area)).rejects.toThrow();
  });
  it('인코딩 실패를 반환한다', async () => {
    vi.mocked(HTMLCanvasElement.prototype.toBlob).mockImplementation((callback) => callback(null));
    await expect(getProfileCroppedFile('blob:source', area)).rejects.toThrow();
  });
});
