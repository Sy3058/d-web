// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../lib/api';
import AccountMenu from './AccountMenu';

vi.mock('../../lib/api', () => ({ api: { post: vi.fn() } }));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  document.cookie = 'login_hint=; Max-Age=0; Path=/';
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  vi.mocked(api.post).mockReset();
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  document.cookie = 'login_hint=; Max-Age=0; Path=/';
});

async function openMenu() {
  await act(async () => container.querySelector('button')!.click());
}

describe('AccountMenu', () => {
  it('공유 SSR에는 닉네임을 넣지 않고 로그인 링크를 렌더한다', () => {
    document.cookie = `login_hint=${encodeURIComponent('독자')}; Path=/`;
    const html = renderToString(<AccountMenu />);
    expect(html).toContain('/auth/login');
    expect(html).not.toContain('독자');
  });

  it('힌트가 없거나 잘못 인코딩되면 로그인 링크를 표시한다', async () => {
    await act(async () => root.render(<AccountMenu />));
    expect(container.querySelector('a')?.getAttribute('href')).toBe('/auth/login');
    document.cookie = 'login_hint=%E0%A4; Path=/';
    await act(async () => window.dispatchEvent(new Event('focus')));
    expect(container.querySelector('a')?.textContent).toBe('로그인');
  });

  it('닉네임 메뉴에 계정 링크와 로그아웃을 제공한다', async () => {
    document.cookie = `login_hint=${encodeURIComponent('독자 닉네임')}; Path=/`;
    await act(async () => root.render(<AccountMenu />));
    expect(container.querySelector('button')?.textContent).toBe('독자 닉네임');
    expect(container.querySelector('button')?.hasAttribute('title')).toBe(false);
    await openMenu();
    const menu = document.querySelector('[role="menu"]');
    expect(menu).not.toBeNull();
    expect(Array.from(menu!.querySelectorAll('a')).map((link) => [link.textContent, link.getAttribute('href')]))
      .toEqual([['마이페이지', '/my'], ['구매내역', '/my/purchases'], ['설정', '/my/settings']]);
    expect(menu?.textContent).toContain('로그아웃');
  });

  it('포커스와 뷰어 표시 변경 때 힌트를 갱신하고 열린 메뉴를 닫는다', async () => {
    document.cookie = 'login_hint=reader; Path=/';
    await act(async () => root.render(<AccountMenu visible />));
    await openMenu();
    await act(async () => root.render(<AccountMenu visible={false} />));
    expect(document.querySelector('[role="menu"]')).toBeNull();
    document.cookie = 'login_hint=; Max-Age=0; Path=/';
    await act(async () => window.dispatchEvent(new Event('focus')));
    expect(container.querySelector('a')?.getAttribute('href')).toBe('/auth/login');
  });

  it('키보드로 열고 탐색한 뒤 Escape로 닫으면 트리거에 포커스를 돌려준다', async () => {
    document.cookie = 'login_hint=reader; Path=/';
    await act(async () => root.render(<AccountMenu />));
    const trigger = container.querySelector('button')!;
    await act(async () => {
      trigger.focus();
      trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    });
    const menu = document.querySelector('[role="menu"]')!;
    expect(menu).not.toBeNull();
    expect(document.activeElement?.textContent).toBe('마이페이지');
    await act(async () => document.activeElement!.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }),
    ));
    expect(document.activeElement?.textContent).toBe('구매내역');
    await act(async () => document.activeElement!.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
    ));
    expect(document.querySelector('[role="menu"]')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('메뉴 바깥을 누르면 포털 메뉴를 닫는다', async () => {
    document.cookie = 'login_hint=reader; Path=/';
    await act(async () => root.render(<AccountMenu />));
    await openMenu();
    expect(document.querySelector('[role="menu"]')).not.toBeNull();
    await act(async () => {
      document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      document.body.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(document.querySelector('[role="menu"]')).toBeNull();
  });

  it('로그아웃은 기존 인증 API를 호출한다', async () => {
    document.cookie = 'login_hint=reader; Path=/';
    vi.mocked(api.post).mockImplementation(() => new Promise(() => {}));
    await act(async () => root.render(<AccountMenu />));
    await openMenu();
    const logout = Array.from(document.querySelectorAll<HTMLElement>('[role="menuitem"]'))
      .find((item) => item.textContent === '로그아웃')!;
    await act(async () => logout.click());
    expect(api.post).toHaveBeenCalledExactlyOnceWith('/auth/logout', {});
  });
});
