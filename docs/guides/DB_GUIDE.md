# DB Guide

PostgreSQL + SQLModel 작업 시 반드시 확인할 주의사항 모음.

---

## 1. 기본 설정

- DB: PostgreSQL
- ORM: SQLModel (SQLAlchemy 기반)
- 마이그레이션: Alembic
- 드라이버: asyncpg (비동기)
- Primary Key: Integer (auto increment) 기본. UUID가 필요한 테이블만 명시.

---

## 2. Primary Key 전략

Integer auto increment를 기본으로 사용한다.
UUID는 외부에 노출되는 리소스(에피소드 URL, 결제 ID 등)에만 사용한다.

    # 기본 (내부용)
    class Episode(SQLModel, table=True):
        id: Optional[int] = Field(default=None, primary_key=True)

    # UUID 필요 시 (외부 노출용)
    import uuid
    class Payment(SQLModel, table=True):
        id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)

이유: Integer는 인덱스 성능이 UUID보다 빠르다.
외부에 노출되는 ID는 UUID로 해야 순서 추측이 불가능하다.

---

## 3. 시간 컬럼

모든 시간은 UTC로 저장한다. 표시할 때 KST로 변환.

    from datetime import datetime, timezone

    class Episode(SQLModel, table=True):
        created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
        updated_at: Optional[datetime] = None

⚠️ `datetime.now()` 금지 → 반드시 `datetime.now(timezone.utc)` 사용.
timezone 없는 naive datetime은 나중에 혼란을 일으킨다.

---

## 4. Soft Delete

실제 삭제 대신 deleted_at 컬럼으로 처리.
적용 대상: User, Episode, Comment

    class User(SQLModel, table=True):
        deleted_at: Optional[datetime] = None

조회 시 반드시 deleted_at IS NULL 조건 추가:

    statement = select(User).where(User.deleted_at == None)

⚠️ deleted_at 조건 누락 시 탈퇴 유저 데이터가 같이 조회됨.

---

## 5. N+1 쿼리 방지

SQLModel 관계 조회 시 lazy loading이 기본이라 N+1이 발생한다.
관계 데이터가 필요하면 반드시 selectinload 명시.

    from sqlalchemy.orm import selectinload

    # 잘못된 방식 (N+1 발생)
    episodes = session.exec(select(Episode)).all()
    for ep in episodes:
        print(ep.pages)  # 매번 추가 쿼리 발생

    # 올바른 방식
    statement = select(Episode).options(selectinload(Episode.pages))
    episodes = session.exec(statement).all()

---

## 6. Alembic 마이그레이션 규칙

이 프로젝트는 **비동기(asyncpg) 환경**이라 `migrations/env.py`가 표준과 다르다.
`create_async_engine` + `NullPool` + `run_sync()` 패턴으로 세팅되어 있음.

모델 변경 후 마이그레이션 생성 절차:

1. 새 모델 파일을 `src/models/` 에 추가
2. `migrations/env.py` 상단 주석 위치에 import 추가:

        from models import user  # noqa: F401  ← autogenerate가 metadata 읽으려면 필수

3. 마이그레이션 생성 + 적용:

        uv run alembic revision --autogenerate -m "add user table"
        uv run alembic upgrade head

⚠️ autogenerate가 모든 변경을 감지하지 못할 수 있다.
생성된 마이그레이션 파일을 반드시 직접 확인 후 적용.

⚠️ 절대 금지: 운영 DB에서 직접 ALTER TABLE 실행.
반드시 Alembic 마이그레이션을 통해서만 스키마 변경.

---

## 7. 인덱스

자주 조회하는 컬럼에 인덱스 추가:

    class Episode(SQLModel, table=True):
        work_id: int = Field(index=True)        # 작품별 에피소드 조회
        created_at: datetime = Field(index=True) # 최신순 정렬

결제 내역 조회, 유저별 구매 목록 등 자주 쓰는 쿼리는 EXPLAIN ANALYZE로 확인.

---

## 8. 트랜잭션

결제 관련 작업은 반드시 트랜잭션으로 묶는다.

    async with session.begin():
        session.add(payment)
        session.add(user_purchase)
        # 둘 다 성공해야 커밋, 하나라도 실패하면 롤백

⚠️ 결제 DB 저장과 포트원 API 호출을 같은 트랜잭션에 넣지 말 것.
외부 API 실패 시 DB 롤백이 안 된다.
순서: 포트원 검증 완료 → DB 저장.

---

## 9. 환경별 DB URL

    # .env
    DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname

    # 테스트용 (pytest)
    TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname_test

⚠️ 테스트는 반드시 별도 DB 사용. 운영 DB에 테스트 데이터 절대 금지.