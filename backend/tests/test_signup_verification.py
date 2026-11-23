"""가입 이메일 코드와 proof 소비의 보안 회귀 테스트."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, Response
from sqlmodel import select

from src.lib.signup_verification import cookie_name as signup_cookie_name
from src.lib.signup_verification import set_signup_verification_cookie
from src.models.user import SignupEmailVerification, User
from src.services import email_service, signup_service


@pytest.fixture
def signup_mail(monkeypatch):
    sender = AsyncMock()
    monkeypatch.setattr(email_service, "send_signup_code_email", sender)
    return sender


@pytest.fixture
def registered_mail(monkeypatch):
    sender = AsyncMock()
    monkeypatch.setattr(email_service, "send_already_registered_email", sender)
    return sender


async def _verified_proof(async_client, signup_mail, email: str) -> str:
    issued = await async_client.post("/auth/signup/send-verification", json={"email": email})
    assert issued.status_code == 200
    _, code = signup_mail.await_args.args
    verified = await async_client.post(
        "/auth/signup/verify-email",
        json={"challenge_id": issued.json()["challenge_id"], "code": code},
    )
    assert verified.status_code == 200
    proof = async_client.cookies.get(signup_cookie_name())
    assert proof and proof not in verified.text
    return proof


async def test_no_user_before_final_signup_and_cross_email_is_rejected(
    async_client, db_session, signup_mail
):
    issued = await async_client.post(
        "/auth/signup/send-verification", json={"email": "bound@example.com"}
    )
    assert issued.status_code == 200
    assert not (await db_session.exec(select(User))).all()
    _, code = signup_mail.await_args.args
    verified = await async_client.post(
        "/auth/signup/verify-email",
        json={"challenge_id": issued.json()["challenge_id"], "code": code},
    )
    assert verified.status_code == 200
    assert not (await db_session.exec(select(User))).all()
    rejected = await async_client.post(
        "/auth/signup",
        json={"email": "other@example.com", "password": "Passw0rd!", "nickname": "other"},
    )
    assert rejected.status_code == 400
    assert rejected.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("is_email_verified", "deleted"),
    [(True, False), (False, False), (True, True)],
)
async def test_existing_email_gets_notice_with_expired_challenge_without_account_mutation(
    async_client,
    db_session,
    signup_mail,
    registered_mail,
    is_email_verified,
    deleted,
):
    email = "registered@example.com"
    deleted_at = datetime.now(UTC) if deleted else None
    user = User(
        email=email,
        hashed_password="existing-hash",
        nickname="existing",
        is_email_verified=is_email_verified,
        email_verified_at=datetime.now(UTC) if is_email_verified else None,
        deleted_at=deleted_at,
    )
    db_session.add(user)
    await db_session.commit()
    before = (
        user.hashed_password,
        user.nickname,
        user.is_email_verified,
        user.email_verified_at,
        user.deleted_at,
    )

    issued = await async_client.post(
        "/auth/signup/send-verification", json={"email": "  Registered@Example.COM "}
    )

    assert issued.status_code == 200
    assert set(issued.json()) == {"challenge_id", "message"}
    assert issued.headers["cache-control"] == "no-store"
    registered_mail.assert_awaited_once_with(email)
    signup_mail.assert_not_awaited()
    record = (await db_session.exec(select(SignupEmailVerification))).one()
    assert record.email == email
    assert record.expires_at <= datetime.now(UTC)

    rejected = await async_client.post(
        "/auth/signup/verify-email",
        json={"challenge_id": issued.json()["challenge_id"], "code": "000000"},
    )
    assert rejected.status_code == 400
    await db_session.refresh(user)
    assert (
        user.hashed_password,
        user.nickname,
        user.is_email_verified,
        user.email_verified_at,
        user.deleted_at,
    ) == before

    cooldown = await async_client.post(
        "/auth/signup/send-verification", json={"email": "REGISTERED@example.com"}
    )
    assert cooldown.status_code == 429
    assert cooldown.headers["cache-control"] == "no-store"
    registered_mail.assert_awaited_once()
    signup_mail.assert_not_awaited()


async def test_expired_proof_is_rejected(async_client, db_session, signup_mail):
    await _verified_proof(async_client, signup_mail, "expired@example.com")
    record = (await db_session.exec(select(SignupEmailVerification))).one()
    record.proof_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(record)
    await db_session.commit()
    response = await async_client.post(
        "/auth/signup",
        json={"email": record.email, "password": "Passw0rd!", "nickname": "expired"},
    )
    assert response.status_code == 400


async def test_external_account_insert_race_is_duplicate_without_overwrite(
    async_client, session_factory, signup_mail, monkeypatch
):
    email = "external-race@example.com"
    proof = await _verified_proof(async_client, signup_mail, email)
    async with session_factory() as signup_session:
        real_flush = signup_session.flush
        inserted = False

        async def race_flush(*args, **kwargs):
            nonlocal inserted
            if not inserted and any(isinstance(value, User) for value in signup_session.new):
                inserted = True
                async with session_factory() as external:
                    external.add(
                        User(
                            email=email,
                            hashed_password="external-hash",
                            nickname="external",
                            is_email_verified=True,
                            email_verified_at=datetime.now(UTC),
                        )
                    )
                    await external.commit()
            return await real_flush(*args, **kwargs)

        monkeypatch.setattr(signup_session, "flush", race_flush)
        result = await signup_service.complete_signup(
            email, "Passw0rd!", "signup", proof, signup_session
        )

    assert result.duplicate is True
    async with session_factory() as verify:
        users = (await verify.exec(select(User).where(User.email == email))).all()
        challenge = (await verify.exec(select(SignupEmailVerification))).one()
    assert len(users) == 1
    assert (users[0].nickname, users[0].hashed_password) == ("external", "external-hash")
    assert challenge.used_at is not None


async def test_expired_code_and_successful_code_replay_are_rejected(db_session):
    expired_tasks = BackgroundTasks()
    expired_challenge = await signup_service.send_verification(
        "expired-code@example.com", db_session, expired_tasks
    )
    expired_code = expired_tasks.tasks[0].args[1]
    expired = (await db_session.exec(select(SignupEmailVerification))).one()
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(expired)
    await db_session.commit()
    with pytest.raises(signup_service.SignupVerificationError):
        await signup_service.verify_email(expired_challenge, expired_code, db_session)

    fresh_tasks = BackgroundTasks()
    fresh_challenge = await signup_service.send_verification(
        "replay-code@example.com", db_session, fresh_tasks
    )
    fresh_code = fresh_tasks.tasks[0].args[1]
    await signup_service.verify_email(fresh_challenge, fresh_code, db_session)
    with pytest.raises(signup_service.SignupVerificationError):
        await signup_service.verify_email(fresh_challenge, fresh_code, db_session)


async def test_five_wrong_codes_lock_challenge_even_for_correct_code(db_session):
    tasks = BackgroundTasks()
    challenge_id = await signup_service.send_verification(
        "attempt-limit@example.com", db_session, tasks
    )
    correct_code = tasks.tasks[0].args[1]
    wrong_code = "000000" if correct_code != "000000" else "999999"

    for _ in range(5):
        with pytest.raises(signup_service.SignupVerificationError):
            await signup_service.verify_email(challenge_id, wrong_code, db_session)

    record = (await db_session.exec(select(SignupEmailVerification))).one()
    assert record.attempts == 5
    with pytest.raises(signup_service.SignupVerificationError):
        await signup_service.verify_email(challenge_id, correct_code, db_session)


async def test_concurrent_wrong_codes_are_bounded_at_five(db_session, session_factory):
    import asyncio

    tasks = BackgroundTasks()
    challenge_id = await signup_service.send_verification(
        "attempt-race@example.com", db_session, tasks
    )
    correct_code = tasks.tasks[0].args[1]
    wrong_code = "000000" if correct_code != "000000" else "999999"

    async def fail_code():
        async with session_factory() as session:
            with pytest.raises(signup_service.SignupVerificationError):
                await signup_service.verify_email(challenge_id, wrong_code, session)

    await asyncio.gather(*(fail_code() for _ in range(8)))
    await db_session.rollback()
    record = (await db_session.exec(select(SignupEmailVerification))).one()
    assert record.attempts == 5


async def test_resend_rotates_challenge_and_invalidates_proof(db_session):
    first_tasks = BackgroundTasks()
    old_challenge = await signup_service.send_verification(
        "rotate@example.com", db_session, first_tasks
    )
    old_code = first_tasks.tasks[0].args[1]
    _, proof = await signup_service.verify_email(old_challenge, old_code, db_session)
    record = (await db_session.exec(select(SignupEmailVerification))).one()
    record.last_sent_at = datetime.now(UTC) - signup_service.RESEND_COOLDOWN
    db_session.add(record)
    await db_session.commit()

    second_tasks = BackgroundTasks()
    new_challenge = await signup_service.send_verification(
        "rotate@example.com", db_session, second_tasks
    )
    assert new_challenge != old_challenge
    assert await signup_service.get_verified_email(proof, db_session) is None
    with pytest.raises(signup_service.SignupVerificationError):
        await signup_service.verify_email(old_challenge, old_code, db_session)


async def test_verification_status_none_valid_and_consumed(async_client, signup_mail):
    empty = await async_client.get("/auth/signup/verification")
    assert empty.json() == {"email": None}
    assert empty.headers["cache-control"] == "no-store"
    await _verified_proof(async_client, signup_mail, "status@example.com")
    valid = await async_client.get("/auth/signup/verification")
    assert valid.json() == {"email": "status@example.com"}
    assert valid.headers["cache-control"] == "no-store"
    completed = await async_client.post(
        "/auth/signup",
        json={"email": "status@example.com", "password": "Passw0rd!", "nickname": "status"},
    )
    assert completed.status_code == 200
    assert (await async_client.get("/auth/signup/verification")).json() == {"email": None}


def test_production_cookie_is_host_secure_http_only_and_strict(monkeypatch):
    monkeypatch.setattr(signup_service.settings, "env", "production")
    response = Response()
    set_signup_verification_cookie(response, "secret-proof")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-signup_verification=")
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert "Path=/" in cookie and "Domain=" not in cookie


async def test_same_code_concurrently_creates_only_one_proof(db_session, session_factory):
    import asyncio

    tasks = BackgroundTasks()
    challenge_id = await signup_service.send_verification(
        "verify-race@example.com", db_session, tasks
    )
    code = tasks.tasks[0].args[1]

    async def verify():
        async with session_factory() as session:
            return await signup_service.verify_email(challenge_id, code, session)

    results = await asyncio.gather(verify(), verify(), return_exceptions=True)
    assert sum(isinstance(result, tuple) for result in results) == 1
    assert (
        sum(isinstance(result, signup_service.SignupVerificationError) for result in results) == 1
    )
