import { describe, expect, it } from 'vitest';
import {
  createViewerControlsScrollState,
  syncViewerControlsScrollState,
  updateViewerControlsScrollState,
} from './viewerControls';

const MAX_SCROLL_Y = 1_000;

describe('viewer controls scroll state', () => {
  it('최초에는 보이고 하향 48px이 누적된 순간 숨는다', () => {
    let state = createViewerControlsScrollState(100);

    state = updateViewerControlsScrollState(state, 147, MAX_SCROLL_Y);
    expect(state.visible).toBe(true);

    state = updateViewerControlsScrollState(state, 148, MAX_SCROLL_Y);
    expect(state.visible).toBe(false);
  });

  it('숨은 뒤 상향 24px이 누적된 순간 다시 보인다', () => {
    let state = createViewerControlsScrollState(100);
    state = updateViewerControlsScrollState(state, 148, MAX_SCROLL_Y);

    state = updateViewerControlsScrollState(state, 125, MAX_SCROLL_Y);
    expect(state.visible).toBe(false);

    state = updateViewerControlsScrollState(state, 124, MAX_SCROLL_Y);
    expect(state.visible).toBe(true);
  });

  it('방향이 바뀌면 누적 거리를 새 방향 기준으로 다시 센다', () => {
    let state = createViewerControlsScrollState(100);
    state = updateViewerControlsScrollState(state, 130, MAX_SCROLL_Y);
    state = updateViewerControlsScrollState(state, 125, MAX_SCROLL_Y);
    state = updateViewerControlsScrollState(state, 140, MAX_SCROLL_Y);

    expect(state.visible).toBe(true);
    expect(state.direction).toBe('down');
    expect(state.distance).toBe(15);
  });

  it('작은 상하 흔들림만으로 표시 상태를 바꾸지 않는다', () => {
    let state = createViewerControlsScrollState(100);

    for (const scrollY of [106, 101, 108, 103, 110, 105]) {
      state = updateViewerControlsScrollState(state, scrollY, MAX_SCROLL_Y);
    }

    expect(state.visible).toBe(true);
  });

  it('문서 최상단과 최하단에서는 항상 표시한다', () => {
    let state = createViewerControlsScrollState(100);
    state = updateViewerControlsScrollState(state, 148, MAX_SCROLL_Y);
    expect(state.visible).toBe(false);

    state = updateViewerControlsScrollState(state, MAX_SCROLL_Y, MAX_SCROLL_Y);
    expect(state.visible).toBe(true);

    state = createViewerControlsScrollState(100);
    state = updateViewerControlsScrollState(state, 148, MAX_SCROLL_Y);
    expect(state.visible).toBe(false);

    state = updateViewerControlsScrollState(state, 0, MAX_SCROLL_Y);
    expect(state.visible).toBe(true);
  });

  it('프로그램적 복원 위치를 visible 기준점으로 동기화한다', () => {
    let state = createViewerControlsScrollState(0);
    state = updateViewerControlsScrollState(state, 48, MAX_SCROLL_Y);
    expect(state.visible).toBe(false);

    state = syncViewerControlsScrollState(state, 600);

    expect(state).toEqual({ visible: true, lastY: 600, direction: null, distance: 0 });
  });
});
