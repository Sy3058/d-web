"""in-process 스케줄러 (M1.5 E1, ADM-04 + 이슈 #57 토큰 cleanup).

마일스톤 확정: APScheduler AsyncIOScheduler를 FastAPI lifespan에서 기동
(cron+엔드포인트는 외부 의존이라 미채택 - 단일 VPS 단순성). 단일 uvicorn 워커
전제 - 멀티워커 전환 시 잡 중복 발화는 결과가 멱등이라 무해하나 낭비
(advisory lock은 후속, M1.5_foundation E1 결정).

잡 본체는 session 주입 순수 함수로 두고 스케줄러용 래퍼만 자체 세션을 연다.
테스트가 본체에 conftest test_engine 세션을 주입해 기존 격리(테이블 DELETE)
안에서 검증하기 위함 - 잡이 lib/db 세션을 직접 열면 test_database_url 설정 시
dev DB를 건드린다(E1 계획 리뷰).
"""

from datetime import UTC, datetime

import sentry_sdk
import structlog
from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, update
from sqlalchemy.sql import func
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.db import async_session_maker
from src.models.user import EmailVerification, RefreshToken, TrustedDevice
from src.models.work import Episode

log = structlog.get_logger(__name__)

# 예약 공개 폴링 주기(초). 예약 시각 도달 후 공개까지의 체감 지연 상한.
PUBLISH_POLL_SECONDS = 60
# 만료 토큰 정리 주기(시간). 기동 직후 1회 + 이후 24시간마다.
CLEANUP_INTERVAL_HOURS = 24

_CLEANUP_MODELS = (RefreshToken, TrustedDevice, EmailVerification)


async def publish_due_episodes(session: AsyncSession) -> int:
    """예약 시각이 지난 에피소드를 공개 전환. 반환 = 전환된 행 수.

    원자 UPDATE 1문이라 멱등: 한 번 true가 된 행은 WHERE에서 영구히 빠지고,
    재시작·중복 발화·밀린 틱 몰아치기 전부 무해하다. 시각 비교는 DB now() 기준
    (앱 시계 불사용). published_at은 공개 후 "공개 시각" 데이터로 역할이 바뀌므로
    지우지 않는다(독자 정렬·표시가 소비 - idx_episodes_published_at).
    """
    result = await session.exec(
        update(Episode)
        .where(
            Episode.is_published.is_(False),
            Episode.published_at.is_not(None),
            Episode.published_at <= func.now(),
            # D3 리뷰 인계: 이미지 0장 draft에 걸린 예약이 빈 회차를 공개하는 것 차단
            # ("메타 먼저" 워크플로 - 이후 첫 이미지가 붙으면 다음 틱에 공개됨)
            func.jsonb_array_length(Episode.image_keys) > 0,
        )
        .values(is_published=True)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    if result.rowcount:
        log.info("episodes_published", count=result.rowcount)
    return result.rowcount


async def cleanup_expired_tokens(session: AsyncSession) -> dict[str, int]:
    """만료(expires_at 경과) 토큰 행 삭제 (#57). 반환 = 테이블별 삭제 행 수.

    삭제 기준은 expires_at 경과 하나다. revoked_at 행을 만료 전에 지우면 refresh
    회전 재사용 탐지(M1 C4)의 근거가 사라져 세션 전체 revoke가 조용한 401로
    퇴화한다 - 이슈 #57 본문("revoked 삭제")과의 의도적 차이. 만료되면 revoked
    여부와 무관하게 삭제되므로 결국 전부 정리된다. 세 테이블은 FK 의존이 없어
    순서 무관, 한 트랜잭션으로 커밋한다.
    """
    deleted: dict[str, int] = {}
    for model in _CLEANUP_MODELS:
        result = await session.exec(delete(model).where(model.expires_at <= func.now()))
        deleted[model.__tablename__] = result.rowcount
    await session.commit()
    log.info("expired_tokens_cleaned", **deleted)
    return deleted


async def _run_publish_job() -> None:
    async with async_session_maker() as session:
        await publish_due_episodes(session)


async def _run_cleanup_job() -> None:
    async with async_session_maker() as session:
        await cleanup_expired_tokens(session)


def _on_job_error(event: JobExecutionEvent) -> None:
    # APScheduler는 잡 예외를 삼키고 다음 틱에 재시도한다(스케줄러는 안 죽음).
    # 자체 로거(ERROR)로만 남으면 반복 실패를 못 알아채므로 Sentry로 승격.
    log.error("scheduler_job_failed", job_id=event.job_id, exc_info=event.exception)
    sentry_sdk.capture_exception(event.exception)


def create_scheduler() -> AsyncIOScheduler:
    """스케줄러 조립. start()는 호출하지 않는다 - lifespan 몫(실행 중 루프에 바인딩)."""
    scheduler = AsyncIOScheduler(
        timezone=UTC,  # tzlocal 추정(환경 의존·경고) 대신 명시
        job_defaults={
            # 3.x 기본값이지만 단일 실행 보장 의도를 코드에 박아둔다
            "coalesce": True,
            "max_instances": 1,
            # 기본값(1초)은 그만큼 늦은 틱을 통째로 스킵 - 24h 잡이면 하루를 날린다.
            "misfire_grace_time": None,  # 멱등 잡이라 늦어도 무조건 실행이 안전
        },
    )
    scheduler.add_job(
        _run_publish_job,
        "interval",
        seconds=PUBLISH_POLL_SECONDS,
        id="publish_due_episodes",
    )
    scheduler.add_job(
        _run_cleanup_job,
        "interval",
        hours=CLEANUP_INTERVAL_HOURS,
        id="cleanup_expired_tokens",
        # 첫 발화가 기동+24h면 잦은 재배포에서 영영 안 돈다 - 기동 직후 1회 실행
        next_run_time=datetime.now(UTC),
    )
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    return scheduler
