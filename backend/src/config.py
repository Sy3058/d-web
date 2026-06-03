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

    # 앱 URL (이 두 값으로 아래 항목들을 조립)
    app_base_url: str
    admin_base_url: str

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

    # 모니터링
    sentry_dsn: str = ""

    # 2FA / TOTP
    totp_issuer: str = "dweb-admin"

    # ── 조립 필드 ──────────────────────────────────────────────────────────────

    @computed_field
    @property
    def kakao_redirect_uri(self) -> str:
        return f"{self.app_base_url}/auth/callback/kakao"

    @computed_field
    @property
    def google_redirect_uri(self) -> str:
        return f"{self.app_base_url}/auth/callback/google"

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        return [self.app_base_url, self.admin_base_url]


settings = Settings()
