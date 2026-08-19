export const CONTROLS_HIDE_DISTANCE_PX = 48;
export const CONTROLS_SHOW_DISTANCE_PX = 24;

type ScrollDirection = 'up' | 'down' | null;

export interface ViewerControlsScrollState {
  visible: boolean;
  lastY: number;
  direction: ScrollDirection;
  distance: number;
}

export function createViewerControlsScrollState(scrollY: number): ViewerControlsScrollState {
  return {
    visible: true,
    lastY: Math.max(scrollY, 0),
    direction: null,
    distance: 0,
  };
}

export function syncViewerControlsScrollState(
  state: ViewerControlsScrollState,
  scrollY: number,
): ViewerControlsScrollState {
  return {
    ...state,
    visible: true,
    lastY: Math.max(scrollY, 0),
    direction: null,
    distance: 0,
  };
}

export function updateViewerControlsScrollState(
  state: ViewerControlsScrollState,
  scrollY: number,
  maxScrollY: number,
): ViewerControlsScrollState {
  const currentY = Math.min(Math.max(scrollY, 0), Math.max(maxScrollY, 0));

  if (currentY <= 0 || currentY >= maxScrollY) {
    return syncViewerControlsScrollState(state, currentY);
  }

  const delta = currentY - state.lastY;
  if (delta === 0) return state;

  const direction: ScrollDirection = delta > 0 ? 'down' : 'up';
  const distance =
    state.direction === direction ? state.distance + Math.abs(delta) : Math.abs(delta);
  const threshold =
    direction === 'down' ? CONTROLS_HIDE_DISTANCE_PX : CONTROLS_SHOW_DISTANCE_PX;
  const visible = distance >= threshold ? direction === 'up' : state.visible;

  return {
    visible,
    lastY: currentY,
    direction,
    distance: distance >= threshold ? 0 : distance,
  };
}
