"""테스트용 도메인 객체 팩토리.

test_catalog.py(공개 카탈로그)와 test_progress.py(진행도)가 같은 Work/Episode 생성
로직을 쓴다. 원래 두 파일에 복붙돼 있었으나, 모델에 nullable=False 컬럼이 하나 추가되면
두 곳을 모두 고쳐야 하고 한쪽을 빠뜨리면 다른 테스트 파일이 IntegrityError로 깨지므로
여기로 모았다.

admin API를 거치지 않고 ORM으로 직접 생성한다 - 공개 read 경로 자체가 검증 대상이라
생성 경로와 원인을 분리한다.
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.user import User
from src.models.work import Episode, Work

# --- 본문 문서(TipTap JSON) 빌더 -------------------------------------------
# test_content_doc.py(검증기 단위)와 test_episode_content.py(B2 API)가 공유한다.
# 파일마다 복붙하면 화이트리스트에 노드가 추가될 때 한쪽만 고쳐 낡은 문서 모양을
# 검증하게 된다(이 모듈이 만들어진 이유와 같은 사고).

CONTENT_KEY = "works/w/episodes/e/page.webp"
PAYWALL: dict = {"type": "paywall"}


def doc(*nodes: dict) -> dict:
    return {"type": "doc", "content": list(nodes)}


def para(text: str, marks: list[dict] | None = None) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks is not None:
        node["marks"] = marks
    return {"type": "paragraph", "content": [node]}


def img(key: str = CONTENT_KEY) -> dict:
    return {"type": "image", "attrs": {"key": key}}


async def make_work(db_session: AsyncSession, author: User, **overrides) -> Work:
    work = Work(
        author_id=author.id,
        title=overrides.pop("title", "테스트작"),
        is_published=overrides.pop("is_published", True),
        **overrides,
    )
    db_session.add(work)
    await db_session.commit()
    await db_session.refresh(work)
    return work


_public_id_counter = 10_000_000


def _next_public_id() -> int:
    # 테스트 전용 - 프로덕션은 episode_service._generate_public_id(랜덤 + UNIQUE 재시도)를
    # 쓴다. 여기선 무작위 충돌 재시도 로직 없이 단순 증가로 유니크만 보장하면 충분하다.
    global _public_id_counter
    _public_id_counter += 1
    return _public_id_counter


_sort_order_counter = 0


def _next_sort_order() -> int:
    # 전역 증가라 작품이 여러 개여도 각 작품 안에서는 생성 순서가 그대로 유지된다
    # (sort_order는 work_id 스코프 정렬 키라 전역 연속성은 의미 없음).
    global _sort_order_counter
    _sort_order_counter += 1
    return _sort_order_counter


async def make_episode(db_session: AsyncSession, work: Work, **overrides) -> Episode:
    # `or` 대신 sentinel 비교 - sort_order=0을 명시로 넘기는 테스트가 조용히 덮이면
    # 정렬 테스트가 의도와 다른 값을 검증하게 된다.
    sort_order = overrides.pop("sort_order", None)
    ep = Episode(
        work_id=work.id,
        public_id=overrides.pop("public_id", None) or _next_public_id(),
        sort_order=_next_sort_order() if sort_order is None else sort_order,
        title=overrides.pop("title", "1화"),
        is_published=overrides.pop("is_published", True),
        **overrides,
    )
    db_session.add(ep)
    await db_session.commit()
    await db_session.refresh(ep)
    return ep
