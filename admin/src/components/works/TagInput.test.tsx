import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { TagInput } from './TagInput';

function ControlledTagInput() {
  const [tags, setTags] = useState<string[]>([]);
  return <TagInput value={tags} onChange={setTags} />;
}

describe('TagInput', () => {
  it('Enter로 태그를 추가한다', () => {
    render(<ControlledTagInput />);
    const input = screen.getByPlaceholderText('태그 입력 후 Enter');
    fireEvent.change(input, { target: { value: '로맨스' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(screen.getByText('로맨스')).toBeInTheDocument();
  });

  it('같은 이름을 중복 추가하지 않는다 (get-or-create 백엔드와 정합)', () => {
    render(<ControlledTagInput />);
    const input = screen.getByPlaceholderText('태그 입력 후 Enter');
    fireEvent.change(input, { target: { value: '로맨스' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.change(input, { target: { value: '로맨스' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(screen.getAllByText('로맨스')).toHaveLength(1);
  });

  it('× 버튼으로 태그를 삭제한다', () => {
    render(<ControlledTagInput />);
    const input = screen.getByPlaceholderText('태그 입력 후 Enter');
    fireEvent.change(input, { target: { value: '액션' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.click(screen.getByLabelText('액션 태그 삭제'));

    expect(screen.queryByText('액션')).not.toBeInTheDocument();
  });
});
