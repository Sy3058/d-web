"""인증 표면 rate limit (M1 F1 / council I2).

IP 단위 슬라이딩 윈도우. limits(유지보수되는 코어)를 FastAPI 의존성으로 감싼다.
slowapi(2024 정체·alpha) 대신 limits 직접: 데코레이터 + 엔드포인트마다 request 주입을
강제하는 대신 Depends 합성에 맞고, 429 응답 모양·키 함수를 완전히 제어한다. 나중에
분산 한도가 필요하면 storage를 async+redis://로 교체(코드 한 줄).

키 = 클라이언트 IP only. 엔드포인트 로직 '전에' 429를 던지므로 회원 존재 여부와 무관해
비열거(non-enumeration) 중립이다. 이메일을 키에 섞지 않는다(한도·헤더 차이로 회원 여부가
새는 enumeration 방지).

⚠️ 멀티워커: MemoryStorage는 프로세스별이라 N워커면 실효 한도 ≈ N×limit. coarse한
anti-automation 속도 제한이라 초기 단일/소수 워커에선 허용한다(I1의 "인메모리 앱 상태는
워커 간 신뢰 불가"와 동일 한계). 엄밀한 분산 한도는 Redis storage로 전환.

⚠️ 배포 (신뢰 경계 2겹 - 둘 다 필요): Caddy 뒤에서 request.client.host가 '실제 클라이언트
IP'가 되려면,
  (1) uvicorn --proxy-headers --forwarded-allow-ips=<caddy>: 외부가 uvicorn에 직접 연결해
      XFF를 위조하는 경로 차단(Caddy 우회 방지). 미설정 시 모든 요청이 프록시 IP 한 키로
      묶여 전역 한도(자기 DoS).
  (2) Caddy가 X-Forwarded-For를 append가 아닌 overwrite로 정화
      (header_up X-Forwarded-For {http.request.remote.host}). XFF는 프록시마다 append되는
      리스트라, append만 하면 클라가 보낸 위조값이 왼쪽에 남아 uvicorn(옛 기본은 leftmost
      채택)이 그걸 믿을 수 있다. overwrite로 위조값을 버리고 실제 peer만 남긴다.
  (1)만으론 Caddy를 통과시킨 위조 XFF 밀반입을 못 막는다. → infra 후속 과제.
"""

from fastapi import HTTPException, Request, status
from limits import RateLimitItem, parse
from limits.aio import storage, strategies

_RATE_LIMIT_MESSAGE = "요청이 너무 많습니다. 잠시 후 다시 시도하세요"


def _new_limiter() -> tuple[storage.MemoryStorage, strategies.MovingWindowRateLimiter]:
    store = storage.MemoryStorage()
    return store, strategies.MovingWindowRateLimiter(store)


# 모듈 단위 단일 storage/limiter. 프로세스 수명 동안 공유한다.
# __call__이 호출 시점에 모듈 전역을 다시 조회하므로 reset_rate_limits로 교체 가능.
_storage, _limiter = _new_limiter()


def _client_key(request: Request) -> str:
    """rate limit 키 = 클라이언트 IP.

    ASGITransport(테스트) 등 client 정보가 없을 땐 단일 fallback 키로 묶는다.
    """
    if request.client is None:
        return "anonymous"
    return request.client.host


class RateLimit:
    """IP 단위 rate limit FastAPI 의존성. 윈도우 초과 시 429(Retry-After 포함).

    scope로 엔드포인트별 버킷을 분리한다(login 5/분과 signup 5/분이 서로 독립).
    """

    def __init__(self, limit: str, scope: str) -> None:
        self._item: RateLimitItem = parse(limit)
        self._scope = scope

    async def __call__(self, request: Request) -> None:
        if not await _limiter.hit(self._item, self._scope, _client_key(request)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=_RATE_LIMIT_MESSAGE,
                headers={"Retry-After": str(self._item.get_expiry())},
            )


def reset_rate_limits() -> None:
    """테스트 격리용: rate limit 카운터를 모두 비운다. 운영 코드에서 호출 금지.

    storage/limiter를 새 인스턴스로 교체한다. 생성은 이벤트 루프가 필요 없는 동기
    연산이라, 동기 테스트(test_cookies 등)에도 autouse 픽스처로 안전하게 걸 수 있다.
    (storage.reset()은 async라 동기 테스트와 충돌 → 재생성 방식 채택.)
    """
    global _storage, _limiter
    _storage, _limiter = _new_limiter()
