"""관리자 부트스트랩 + role 기본값 테스트 (M1.5 B1)."""

from scripts.promote_admin import promote_user
from src.models.user import RoleEnum, User
from src.services import auth_service


async def test_new_user_defaults_to_reader(db_session):
    u = User(email="reader@example.com", nickname="r")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    assert u.role == RoleEnum.READER


async def test_promote_verified_user_to_owner(db_session):
    user = await auth_service.create_user("owner@example.com", "Passw0rd!", "own", db_session)
    user.is_email_verified = True
    db_session.add(user)
    await db_session.commit()

    result = await promote_user("owner@example.com", db_session)

    assert result == "promoted"
    refreshed = await db_session.get(User, user.id)
    assert refreshed.role == RoleEnum.OWNER


async def test_promote_refuses_unverified(db_session):
    # create_user는 is_email_verified=False로 생성한다.
    await auth_service.create_user("unv@example.com", "Passw0rd!", "unv", db_session)
    await db_session.commit()
    assert await promote_user("unv@example.com", db_session) == "unverified"


async def test_promote_missing_user(db_session):
    assert await promote_user("nope@example.com", db_session) == "not_found"


async def test_promote_idempotent_for_owner(db_session):
    user = await auth_service.create_user("own2@example.com", "Passw0rd!", "o2", db_session)
    user.is_email_verified = True
    db_session.add(user)
    await db_session.commit()
    assert await promote_user("own2@example.com", db_session) == "promoted"
    assert await promote_user("own2@example.com", db_session) == "already_owner"


async def test_promote_refuses_social_only(db_session):
    # 비번 없는 계정을 승격하면 /admin/login(비번)도 구글(owner 봉쇄)도 못 써 락아웃 (B3).
    u = User(email="social-only@example.com", nickname="s", is_email_verified=True)
    db_session.add(u)
    await db_session.commit()
    assert await promote_user("social-only@example.com", db_session) == "no_password"
    refreshed = await db_session.get(User, u.id)
    assert refreshed.role == RoleEnum.READER


async def test_promote_revokes_existing_sessions(db_session):
    # 승격 전에 열린(비-TOTP) refresh 체인은 owner 권한을 얻으면 안 된다 - 승격이 전부 revoke.
    user = await auth_service.create_user("pr@example.com", "Passw0rd!", "pr", db_session)
    user.is_email_verified = True
    db_session.add(user)
    await db_session.commit()
    raw = await auth_service.create_refresh_token(user.id, db_session)
    await db_session.commit()

    assert await promote_user("pr@example.com", db_session) == "promoted"

    record = await auth_service.get_refresh_token(raw, db_session)
    assert record is not None
    assert record.revoked_at is not None
