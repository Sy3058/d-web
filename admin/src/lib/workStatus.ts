import type { WorkStatus } from '../types';

// 연재 상태의 단일 출처. 목록(뱃지)·폼(select)·zod enum이 전부 여기서 파생된다.
// Record<WorkStatus, string>이라 백엔드가 상태 값을 추가하면 codegen 타입이 바뀌면서
// 여기 라벨 누락이 컴파일 타임에 잡힌다.
export const WORK_STATUS_LABEL: Record<WorkStatus, string> = {
  ongoing: '연재중',
  completed: '완결',
  hiatus: '휴재',
};

// z.enum은 최소 1개를 요구하는 튜플 타입을 받는다.
export const WORK_STATUS_VALUES = Object.keys(WORK_STATUS_LABEL) as [WorkStatus, ...WorkStatus[]];

export const WORK_STATUS_OPTIONS = WORK_STATUS_VALUES.map((value) => ({
  value,
  label: WORK_STATUS_LABEL[value],
}));
