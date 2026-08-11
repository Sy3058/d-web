"""도메인 예외. service가 raise하고 router가 HTTP 상태로 매핑한다.

service는 HTTP를 모른다(레이어 분리). 비열거 정책상 인증 실패 메시지는
router에서 동일하게 통일한다(어느 예외든 같은 401 문구).
"""


class AuthError(Exception):
    """인증 도메인 베이스 예외."""


class InvalidCredentialsError(AuthError):
    """이메일/비번 불일치 또는 미존재·소셜전용 계정 (router → 401, 동일 메시지)."""


class PwnedPasswordError(AuthError):
    """HIBP 유출 이력이 있는 비밀번호 (router → 422). 이메일 존재와 무관."""


class InvalidTokenError(AuthError):
    """refresh 토큰 무효/만료/미존재 (router → 401)."""


class TokenReuseError(InvalidTokenError):
    """revoke된 refresh 재제출 = 탈취 신호. 세션 전체 무효화 후 401."""


class EmailVerificationError(AuthError):
    """이메일 인증 토큰 무효/만료/사용됨 (router → 400, 단일 generic 메시지)."""


class OAuthError(AuthError):
    """소셜 로그인(OAuth/OIDC) 도메인 베이스 예외. router → 프론트로 generic 에러 302."""


class OAuthExchangeError(OAuthError):
    """코드 교환 실패 또는 id_token 검증 실패(서명/aud/iss/exp/nonce) (router → oauth_failed)."""


class OAuthEmailExistsError(OAuthError):
    """소셜 이메일과 같은 비-소셜 계정이 이미 존재 - 자동 병합 금지(DB_SCHEMA Q6).

    router → email_exists. 자동 병합은 계정 탈취 벡터라 의도적으로 거부한다.
    """


class ImageValidationError(ValueError):
    """업로드 이미지 검증 실패 - 비이미지/크기·해상도 초과 등 클라 귀책 (router → 4xx).

    ValueError 서브클래스: 값 검증 실패 시맨틱 + 스크립트 호출자도 자연스럽게 처리.
    (M1.5 D2. 운영자 설정 문제인 R2NotConfiguredError는 r2_service에 별도 - 5xx 귀책)
    """


class EpisodeConflictError(Exception):
    """에피소드 상태 충돌 (router → 409) - M1.5 D3.

    public_id 발급 재시도 소진, 이미지 append 경합(조건부 UPDATE rowcount=0),
    회차당 장수 상한 도달. 재시도하거나 값을 바꾸면 해소되는 충돌.
    """


class EpisodeValidationError(ValueError):
    """에피소드 요청 값이 현재 상태와 안 맞음 (router → 422) - M1.5 D3.

    image_keys 재배열에 이 회차의 키가 아닌 값/중복 키, thumbnail이 회차에
    없는 키 등. Pydantic 단독으론 못 잡는 DB 상태 의존 검증.
    """


class CommissionConflictError(Exception):
    """커미션 카드 상태 충돌 (router → 409) - M2 그룹 G.

    샘플 이미지 append 경합(조건부 UPDATE rowcount=0)·카드당 장수 상한 도달·
    재배열 요청의 카드 집합 불일치.
    EpisodeConflictError와 같은 성질 - 재시도하면 해소되는 충돌.
    """


class CommissionValidationError(ValueError):
    """커미션 요청 값이 현재 상태와 안 맞음 (router → 422) - M2 그룹 G.

    sample_image_keys 재배열에 이 카드의 키가 아닌 값/중복 키 등
    DB 상태 의존 검증(EpisodeValidationError와 같은 성질).
    """
