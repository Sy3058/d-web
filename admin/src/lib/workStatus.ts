import type { WorkStatus } from '../types';

// 연재 상태의 단일 출처. 목록(뱃지)·폼(select)·zod enum이 전부 여기서 파생된다.
// Record<WorkStatus, string>이라 백엔드가 상태 값을 추가하면 codegen 타입이 바뀌면서
// 여기 라벨 누락이 컴파일 타임에 잡힌다.
export const WORK_STATUS_LABEL: Record<WorkStatus, string> = {
  preparing: '준비중',
  ongoing: '연재중',
  completed: '완결',
  hiatus: '휴재',
};

// 목록 배지 색. 공개 여부 배지(공개=초록·비공개=노랑)와 겹치지 않는 색을 쓴다 - 두 배지가
// 나란히 붙어 있어 같은 색이면 어느 축인지 구분이 안 된다. preparing은 기본 짝이
// 비공개(노랑)라 amber/orange 계열도 피한다.
export const WORK_STATUS_BADGE_CLASS: Record<WorkStatus, string> = {
  preparing: 'bg-rose-100 text-rose-700',
  ongoing: 'bg-blue-100 text-blue-700',
  completed: 'bg-purple-100 text-purple-700',
  hiatus: 'bg-gray-100 text-gray-600',
};

// z.enum은 최소 1개를 요구하는 튜플 타입을 받는다.
export const WORK_STATUS_VALUES = Object.keys(WORK_STATUS_LABEL) as [WorkStatus, ...WorkStatus[]];

export const WORK_STATUS_OPTIONS = WORK_STATUS_VALUES.map((value) => ({
  value,
  label: WORK_STATUS_LABEL[value],
}));
