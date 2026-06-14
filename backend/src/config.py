from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 환경
    env: str = "development"
    debug: bool = False

    # 데이터베이스
    database_url: str
    test_database_url: str = ""

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # 비밀번호 해싱 (B1 - 비번 pre-hash pepper. jwt_secret/token_pepper와 별개 키)
    # 시크릿이라 default 없음(미설정 시 기동 실패). SecretStr로 로그 마스킹.
    password_pepper: SecretStr

    # 토큰 해싱 (B2 - refresh/이메일 인증 토큰 post-hash pepper. password_pepper와 별개 키)
    # post-hash라 pepper 교체 시 재-HMAC으로 무중단 로테이션 가능(password_pepper와 다름).
    token_pepper: SecretStr

    # 앱 URL (이 세 값으로 아래 항목들을 조립)
    # app=독자 사이트, admin=관리자, api=백엔드 공개 주소.
    # OAuth는 BFF 표준(백엔드가 콜백 수신)이라 redirect_uri는 api_base_url에서 조립한다.
    app_base_url: str
    admin_base_url: str
    api_base_url: str

    # OAuth
    kakao_client_id: str = ""
    kakao_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""

    # 결제 - 포트원 V2
    portone_v2_api_secret: str = ""
    portone_store_id: str = ""
    portone_webhook_secret: str = ""
    portone_channel_key_card: str = ""
    portone_channel_key_kakaopay: str = ""
    portone_channel_key_tosspay: str = ""

    # 스토리지 - Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "dweb-content"
    r2_endpoint: str = ""
    r2_signed_url_ttl_seconds: int = 300

    # 이메일 발송 (Resend - M1 E1)
    # 미설정 시 fail-open(no-op + 경고). production & 미설정이면 기동 시 추가 경고.
    # email_from 기본값은 Resend 테스트 모드 - 본인 Resend 계정 이메일로만 발송 가능.
    # DKIM 인증된 커스텀 도메인 확보 후 EMAIL_FROM만 교체(코드 변경 없음).
    resend_api_key: SecretStr = SecretStr("")
    email_from: str = "dweb <onboarding@resend.dev>"

    # 모니터링
    sentry_dsn: str = ""

    # 2FA / TOTP
    totp_issuer: str = "dweb-admin"

    # ── 조립 필드 ──────────────────────────────────────────────────────────────

    @computed_field
    @property
    def kakao_redirect_uri(self) -> str:
        # BFF 표준: 콜백을 백엔드가 받으므로 redirect_uri는 api_base_url(백엔드) 기준.
        return f"{self.api_base_url}/auth/callback/kakao"

    @computed_field
    @property
    def google_redirect_uri(self) -> str:
        # BFF 표준: 콜백을 백엔드가 받으므로 redirect_uri는 api_base_url(백엔드) 기준.
        # 구글 콘솔의 '승인된 리디렉션 URI'에 이 값과 정확히 일치하게 등록해야 한다.
        return f"{self.api_base_url}/auth/callback/google"

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        return [self.app_base_url, self.admin_base_url]

    @computed_field
    @property
    def cookie_secure(self) -> bool:
        """인증 쿠키 Secure 플래그 (B3). 로컬 http(dev)는 False, 그 외는 True.

        Secure 쿠키는 https에서만 전송되므로 로컬 http 개발에서 True면 쿠키가
        아예 안 실린다. __Host- 프리픽스도 Secure를 요구하므로 이 값에 연동된다.
        """
        return self.env != "development"


settings = Settings()
