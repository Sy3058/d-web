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
