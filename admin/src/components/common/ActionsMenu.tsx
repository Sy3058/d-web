import { type ReactNode, useEffect, useRef, useState } from 'react';

interface ActionsMenuProps {
  /** 트리거 버튼의 접근성 이름. 목록은 행마다 메뉴가 하나씩이라 "메뉴"만으로는 구분이 안 된다. */
  label: string;
  /** 메뉴 폭. 항목 문구 길이에 맞춰 호출자가 정한다(기본값은 "수정/삭제" 기준). */
  width?: string;
  /** 열린 메뉴의 내용. 항목을 누를 때 close()를 직접 호출해 닫는다. */
  children: (close: () => void) => ReactNode;
}

/** 메뉴 항목 버튼의 공통 모양. 색(text-red-600 등)만 호출자가 덧붙인다. */
export const ACTION_ITEM_CLASS =
  'block w-full px-4 py-2 text-left text-sm hover:bg-gray-50 disabled:opacity-50';

/** 목록 행의 "···" 드롭다운 껍데기 - 열림 상태와 바깥 클릭 닫기만 담당한다.
 *
 * 항목 구성은 호출자가 children으로 넣는다. 작품·회차 메뉴가 각자 이 로직을 복사하고
 * 있으면 한쪽만 고치는 드리프트가 생긴다(#85에서 추출).
 */
export function ActionsMenu({ label, width = 'w-32', children }: ActionsMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex h-8 w-8 items-center justify-center rounded-full text-lg leading-none text-gray-400 hover:bg-gray-100 hover:text-gray-700"
        aria-label={label}
      >
        ···
      </button>
      {open && (
        <div
          className={`absolute right-0 top-full z-10 mt-1 ${width} rounded-lg border border-gray-100 bg-white py-1 shadow-lg`}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}
