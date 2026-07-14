import { useEffect, useRef, useState } from 'react';

interface WorkActionsMenuProps {
  onEdit: () => void;
  onDelete: () => void;
  isDeleting: boolean;
}

export function WorkActionsMenu({ onEdit, onDelete, isDeleting }: WorkActionsMenuProps) {
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
        aria-label="작품 관리 메뉴"
      >
        ···
      </button>
      {open && (
        <div className="absolute right-0 top-full z-10 mt-1 w-32 rounded-lg border border-gray-100 bg-white py-1 shadow-lg">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onEdit();
            }}
            className="block w-full px-4 py-2 text-left text-sm hover:bg-gray-50"
          >
            수정
          </button>
          {/* 요청이 끝나기 전에 다시 눌러 같은 작품에 DELETE를 중복 발사하지 않도록 잠근다. */}
          <button
            type="button"
            disabled={isDeleting}
            onClick={() => {
              setOpen(false);
              onDelete();
            }}
            className="block w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-gray-50 disabled:opacity-50"
          >
            {isDeleting ? '삭제 중...' : '삭제'}
          </button>
        </div>
      )}
    </div>
  );
}
