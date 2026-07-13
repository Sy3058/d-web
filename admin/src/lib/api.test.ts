import { describe, expect, it } from 'vitest';
import { ApiError } from '@d-web/shared';
import { describeAuthError, isSessionExpired } from './api';

describe('describeAuthError', () => {
  it('HTTPException detail(문자열)을 그대로 보여준다', () => {
    const err = new ApiError(401, '{"detail":"이메일 또는 비밀번호가 올바르지 않습니다"}');
    expect(describeAuthError(err)).toBe('이메일 또는 비밀번호가 올바르지 않습니다');
  });

  it('rate limit(429) detail도 그대로 보여준다', () => {
    const err = new ApiError(429, '{"detail":"요청이 너무 많습니다. 잠시 후 다시 시도하세요"}');
    expect(describeAuthError(err)).toBe('요청이 너무 많습니다. 잠시 후 다시 시도하세요');
  });

  it('pydantic 422 배열 detail에서 첫 msg를 뽑는다', () => {
    const err = new ApiError(422, '{"detail":[{"msg":"6자리 숫자를 입력해 주세요"}]}');
    expect(describeAuthError(err)).toBe('6자리 숫자를 입력해 주세요');
  });

  it('네트워크 장애(TypeError)는 ApiError가 아니므로 연결 실패로 안내한다', () => {
    // fetch는 백엔드 다운·CORS 차단 시 TypeError로 reject한다 - JSON.parse가 던지는 걸
    // 삼켜 "요청 오류"로 뭉뚱그리면 원인 파악이 막힌다.
    const err = new TypeError('Failed to fetch');
    expect(describeAuthError(err)).toBe('서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.');
  });

  it('JSON이 아닌 본문이면 폴백 문구를 쓴다', () => {
    const err = new ApiError(500, 'Internal Server Error');
    expect(describeAuthError(err)).toBe('요청 처리 중 오류가 발생했습니다.');
  });
});

describe('isSessionExpired', () => {
  it('401은 pending 쿠키 만료로 보고 로그인 1단계로 되돌린다', () => {
    expect(isSessionExpired(new ApiError(401, '{"detail":"인증이 필요합니다"}'))).toBe(true);
  });

  it('400(틀린 코드)은 재시도 가능하므로 단계를 되돌리지 않는다', () => {
    expect(isSessionExpired(new ApiError(400, '{"detail":"인증 코드가 올바르지 않습니다"}'))).toBe(
      false,
    );
  });

  it('네트워크 오류는 세션 만료가 아니다', () => {
    expect(isSessionExpired(new TypeError('Failed to fetch'))).toBe(false);
  });
});
