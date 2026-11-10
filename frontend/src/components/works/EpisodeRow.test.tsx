// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { EpisodeSummary } from '../../lib/catalog';
import EpisodeRow from './EpisodeRow';

const episode: EpisodeSummary = {
  id: 'a', public_id: 12345678, title: '첫 화', subtitle: null,
  thumbnail_url: 'https://example.com/old.jpg', is_free: false,
  is_locked: true, price: 500, first_published_at: null,
};
let container: HTMLDivElement;
let root: Root | undefined;
const row = (url = episode.thumbnail_url) => <EpisodeRow workId="work" episode={{ ...episode, thumbnail_url: url }} purchased={false} />;

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
});
afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  vi.restoreAllMocks();
  container.remove();
});

async function hydrateImage(complete: boolean, naturalWidth: number) {
  container.innerHTML = renderToString(row());
  const image = container.querySelector('img')!;
  Object.defineProperties(image, { complete: { value: complete }, naturalWidth: { value: naturalWidth } });
  // hydration 이전의 error는 React handler에 전달되지 않는다.
  image.dispatchEvent(new Event('error'));
  await act(async () => { root = hydrateRoot(container, row()); });
  return image;
}

describe('EpisodeRow thumbnail', () => {
  it('SSR 이미지를 유지하고 hydration 이전 완료된 실패만 제거한다', async () => {
    expect(renderToString(row())).toContain('<img');
    await hydrateImage(true, 0);
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('첫 화');
  });

  it.each([[true, 200], [false, 0]])('정상 이미지와 아직 로딩 중인 lazy 이미지를 유지한다: %s/%s', async (complete, width) => {
    const image = await hydrateImage(complete, width);
    expect(container.querySelector('img')).toBe(image);
  });

  it('URL 변경으로 노출한 새 이미지의 완료 상태도 재검사한다', async () => {
    root = createRoot(container);
    await act(async () => root!.render(row()));
    expect(container.querySelector('img')).not.toBeNull();
    vi.spyOn(HTMLImageElement.prototype, 'complete', 'get').mockReturnValue(true);
    vi.spyOn(HTMLImageElement.prototype, 'naturalWidth', 'get').mockReturnValue(0);
    await act(async () => root!.render(row('https://example.com/new.jpg')));
    expect(container.querySelector('img')).toBeNull();
  });

  it('hydration 뒤 error도 제거하며 새 URL에서 복구하고 이전 이벤트를 무시한다', async () => {
    root = createRoot(container);
    await act(async () => root!.render(row()));
    const oldImage = container.querySelector('img')!;
    await act(async () => oldImage.dispatchEvent(new Event('error')));
    expect(container.querySelector('img')).toBeNull();
    await act(async () => root!.render(row('https://example.com/new.jpg')));
    const newImage = container.querySelector('img');
    expect(newImage?.getAttribute('src')).toBe('https://example.com/new.jpg');
    await act(async () => oldImage.dispatchEvent(new Event('error')));
    expect(container.querySelector('img')).toBe(newImage);
    await act(async () => newImage!.dispatchEvent(new Event('error')));
    expect(container.querySelector('img')).toBeNull();
  });
});
