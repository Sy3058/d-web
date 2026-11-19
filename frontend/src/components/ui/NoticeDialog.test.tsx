// @vitest-environment jsdom
import { act, useRef, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import NoticeDialog from './NoticeDialog';

let root: Root;
let container: HTMLDivElement;
const onOpenChange = vi.fn();

function Harness({ message = '저장했습니다.', title = '알림', confirmLabel = '확인' }: { message?: string; title?: string; confirmLabel?: string }) {
  const [open, setOpen] = useState(true);
  const returnFocus = useRef<HTMLInputElement>(null);
  return (
    <>
      <input aria-label="닉네임" ref={returnFocus} />
      <button type="button" onClick={() => setOpen(true)}>알림 열기</button>
      <NoticeDialog open={open} onOpenChange={(nextOpen) => { onOpenChange(nextOpen); setOpen(nextOpen); }} title={title} message={message} confirmLabel={confirmLabel} returnFocus={returnFocus} />
    </>
  );
}

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  onOpenChange.mockReset();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
async function render(props: Parameters<typeof Harness>[0] = {}) { await act(async () => root.render(<Harness {...props} />)); }
function popup() { return document.querySelector<HTMLElement>('[role="dialog"]'); }
async function clickConfirm() {
  await act(async () => Array.from(popup()!.querySelectorAll('button')).find((button) => button.textContent === '확인')!.click());
}

describe('공통 알림 Dialog', () => {
  it('제목과 본문을 접근성 이름에 연결하고 문자열을 HTML로 실행하지 않는다', async () => {
    await render({ message: '<img src=x onerror=alert(1)>\n다음 줄' });
    const dialog = popup()!;
    expect(dialog).not.toBeNull();
    expect(document.getElementById(dialog.getAttribute('aria-labelledby')!)?.textContent).toBe('알림');
    const description = document.getElementById(dialog.getAttribute('aria-describedby')!);
    expect(description?.textContent).toBe('<img src=x onerror=alert(1)>\n다음 줄');
    expect(description?.className).toContain('whitespace-pre-line');
    expect(dialog.querySelector('img')).toBeNull();
  });

  it('확인을 누르면 닫고 편집 입력으로 포커스를 돌린다', async () => {
    await render();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
    expect(document.activeElement?.textContent).toBe('확인');
    await clickConfirm();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
    expect(popup()).toBeNull();
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
    expect(document.activeElement).toBe(container.querySelector('input'));
  });

  it('우상단 닫기 버튼을 누르면 닫는다', async () => {
    await render();
    await act(async () => popup()!.querySelector<HTMLButtonElement>('button[aria-label="닫기"]')!.click());
    expect(popup()).toBeNull();
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
  });

  it('Escape로 닫는다', async () => {
    await render();
    await act(async () => document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    expect(popup()).toBeNull();
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
  });

  it('본문 안을 클릭해도 유지하고 바깥을 누르면 닫는다', async () => {
    await render();
    await act(async () => {
      popup()!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      popup()!.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      popup()!.click();
    });
    expect(popup()).not.toBeNull();
    expect(onOpenChange).not.toHaveBeenCalled();
    const backdrop = document.querySelector<HTMLElement>('.fixed[role="presentation"]')!;
    expect(backdrop).not.toBeNull();
    await act(async () => {
      backdrop.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      backdrop.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      backdrop.click();
    });
    expect(popup()).toBeNull();
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
  });

  it('닫힌 뒤 새 메시지로 다시 열 수 있고 확인 문구를 변경할 수 있다', async () => {
    await render(); await clickConfirm();
    await render({ title: '저장 완료', message: '새 닉네임을 저장했습니다.', confirmLabel: '알겠어요' });
    await act(async () => container.querySelector('button')!.click());
    expect(popup()?.textContent).toContain('저장 완료');
    expect(popup()?.textContent).toContain('새 닉네임을 저장했습니다.');
    const confirm = Array.from(popup()!.querySelectorAll('button')).find((button) => button.textContent === '알겠어요');
    expect(confirm).toBeDefined();
    await act(async () => confirm!.click());
    expect(popup()).toBeNull();
  });
});
