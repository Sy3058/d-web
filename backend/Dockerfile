FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/

EXPOSE 8000

# --proxy-headers + --forwarded-allow-ips: Caddy 뒤에서 X-Forwarded-For를 신뢰해
# request.client.host를 실제 클라이언트 IP로 만든다(rate limit 키 정확화, I2 후속).
# 미설정 시 allow-ips 기본값(127.0.0.1)이라 Caddy 컨테이너 IP를 신뢰하지 않아
# 전 요청이 Caddy IP 1개로 묶임 = 전역 1키 self-DoS.
# docker 네트워크는 Caddy 컨테이너 IP가 동적이라 '*'로 두고, 위조 방지는 Caddy의
# X-Forwarded-For 덮어쓰기(Caddyfile)가 담당. 직접 경로(127.0.0.1:8000)는 로컬 전용.
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
