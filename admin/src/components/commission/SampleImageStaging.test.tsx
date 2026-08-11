import { fireEvent, render, screen } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SampleImageStaging } from './SampleImageStaging';

function makeFile(name: string): File {
  return new File(['x'], name, { type: 'image/jpeg' });
}

describe('SampleImageStaging', () => {
  beforeEach(() => {
    let sequence = 0;
    URL.createObjectURL = vi.fn(() => `blob:preview-${sequence++}`);
    URL.revokeObjectURL = vi.fn();
  });

  it('파일을 선택하면 onChange가 기존 목록 뒤에 이어붙인 배열로 호출된다', () => {
    const onChange = vi.fn();
    render(<SampleImageStaging files={[makeFile('a.jpg')]} onChange={onChange} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const newFile = makeFile('b.jpg');
    fireEvent.change(input, { target: { files: [newFile] } });

    expect(onChange).toHaveBeenCalledWith([expect.any(File), newFile]);
  });

  it('오른쪽으로 이동은 순서를 바꾼 배열로 onChange를 호출한다', () => {
    const onChange = vi.fn();
    const files = [makeFile('a.jpg'), makeFile('b.jpg')];
    render(<SampleImageStaging files={files} onChange={onChange} />);

    fireEvent.click(screen.getAllByRole('button', { name: '오른쪽으로 이동' })[0]);

    expect(onChange).toHaveBeenCalledWith([files[1], files[0]]);
  });

  it('삭제는 해당 파일을 뺀 배열로 onChange를 호출한다', () => {
    const onChange = vi.fn();
    const files = [makeFile('a.jpg'), makeFile('b.jpg')];
    render(<SampleImageStaging files={files} onChange={onChange} />);

    fireEvent.click(screen.getAllByRole('button', { name: '삭제' })[0]);

    expect(onChange).toHaveBeenCalledWith([files[1]]);
  });

  it('10장에 도달하면 이미지 추가 버튼이 비활성화된다', () => {
    const files = Array.from({ length: 10 }, (_, i) => makeFile(`img-${i}.jpg`));
    render(<SampleImageStaging files={files} onChange={vi.fn()} />);

    expect(screen.getByRole('button', { name: '이미지 추가' })).toBeDisabled();
  });

  it('이미지가 아닌 파일을 선택하면 에러를 보여주고 onChange를 호출하지 않는다', () => {
    const onChange = vi.fn();
    render(<SampleImageStaging files={[]} onChange={onChange} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const badFile = new File(['x'], 'doc.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [badFile] } });

    expect(screen.getByText(/이미지 파일이 아닙니다/)).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('StrictMode 재마운트와 파일 교체·unmount에서 생성한 blob URL을 전부 회수한다', () => {
    const first = makeFile('a.jpg');
    const second = makeFile('b.jpg');
    const { rerender, unmount } = render(
      <StrictMode>
        <SampleImageStaging files={[first]} onChange={vi.fn()} />
      </StrictMode>,
    );

    rerender(
      <StrictMode>
        <SampleImageStaging files={[second]} onChange={vi.fn()} />
      </StrictMode>,
    );
    unmount();

    const created = vi
      .mocked(URL.createObjectURL)
      .mock.results.map((result) => result.value as string);
    expect(created.length).toBeGreaterThan(0);
    expect(vi.mocked(URL.revokeObjectURL).mock.calls.map(([url]) => url)).toEqual(created);
  });
});
