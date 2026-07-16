import { useEffect, useReducer } from 'react';
import type { Editor } from '@tiptap/react';

interface EditorToolbarProps {
  editor: Editor;
  onInsertImage: () => void;
  disabled: boolean;
}

/** 선택·활성 상태는 트랜잭션마다 바뀌므로 구독해 리렌더한다. useEditor는
 * shouldRerenderOnTransaction=false(v3 기본)라 이 구독이 없으면 버튼 활성표시가 안 따라온다. */
function useEditorTick(editor: Editor): void {
  const [, bump] = useReducer((x: number) => x + 1, 0);
  useEffect(() => {
    editor.on('transaction', bump);
    return () => {
      editor.off('transaction', bump);
    };
  }, [editor]);
}

export function EditorToolbar({ editor, onInsertImage, disabled }: EditorToolbarProps) {
  useEditorTick(editor);

  const cls = (active: boolean) =>
    `rounded px-2 py-1 text-sm ${
      active ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
    } disabled:opacity-40`;

  const setLink = () => {
    const prev = editor.getAttributes('link').href as string | undefined;
    const url = window.prompt('링크 URL (http/https)', prev ?? 'https://');
    if (url === null) return; // 취소
    if (url === '') {
      editor.chain().focus().extendMarkRange('link').unsetLink().run();
      return;
    }
    // 서버 화이트리스트도 http(s)만 허용(422)하지만, 프롬프트 단계에서 막아 혼란스러운 저장
    // 실패와 에디터 상태 오염(javascript: 등)을 예방한다.
    if (!/^https?:\/\//i.test(url)) {
      window.alert('http:// 또는 https:// 로 시작하는 링크만 넣을 수 있습니다.');
      return;
    }
    editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run();
  };

  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-gray-200 pb-2">
      <button
        type="button"
        disabled={disabled}
        onClick={() => editor.chain().focus().toggleBold().run()}
        className={cls(editor.isActive('bold'))}
        aria-label="굵게"
      >
        <b>B</b>
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => editor.chain().focus().toggleItalic().run()}
        className={cls(editor.isActive('italic'))}
        aria-label="기울임"
      >
        <i>I</i>
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => editor.chain().focus().toggleUnderline().run()}
        className={cls(editor.isActive('underline'))}
        aria-label="밑줄"
      >
        <u>U</u>
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => editor.chain().focus().toggleStrike().run()}
        className={cls(editor.isActive('strike'))}
        aria-label="취소선"
      >
        <s>S</s>
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={setLink}
        className={cls(editor.isActive('link'))}
        aria-label="링크"
      >
        링크
      </button>

      <span className="mx-1 h-5 w-px bg-gray-200" aria-hidden />

      <button
        type="button"
        disabled={disabled}
        onClick={() => editor.chain().focus().setHorizontalRule().run()}
        className={cls(false)}
      >
        구분선
      </button>
      <button type="button" disabled={disabled} onClick={onInsertImage} className={cls(false)}>
        이미지
      </button>
    </div>
  );
}
