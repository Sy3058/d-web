import { useState } from 'react';
import { TAG_NAME_MAX } from '../../lib/validation';

interface TagInputProps {
  value: string[];
  onChange: (tags: string[]) => void;
}

export function TagInput({ value, onChange }: TagInputProps) {
  const [draft, setDraft] = useState('');

  const addTag = () => {
    const name = draft.trim();
    if (name && !value.includes(name)) {
      onChange([...value, name]);
    }
    setDraft('');
  };

  const removeTag = (name: string) => {
    onChange(value.filter((tag) => tag !== name));
  };

  return (
    <div className="flex flex-col gap-2">
      {value.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {value.map((tag) => (
            <span
              key={tag}
              className="flex items-center gap-1 rounded bg-gray-100 px-2 py-1 text-sm"
            >
              {tag}
              <button
                type="button"
                onClick={() => removeTag(tag)}
                className="text-gray-500 hover:text-red-600"
                aria-label={`${tag} 태그 삭제`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <input
          type="text"
          value={draft}
          // 여기서 막아야 무효한 태그가 폼에 들어와 제출이 조용히 실패하는 경로가 안 생긴다.
          maxLength={TAG_NAME_MAX}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addTag();
            }
          }}
          placeholder="태그 입력 후 Enter"
          className="flex-1 rounded border border-gray-300 px-3 py-2"
        />
        <button
          type="button"
          onClick={addTag}
          disabled={!draft.trim()}
          className="rounded border border-gray-300 px-3 py-2 disabled:opacity-50"
        >
          추가
        </button>
      </div>
    </div>
  );
}
