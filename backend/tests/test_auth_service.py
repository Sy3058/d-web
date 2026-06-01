"""비밀번호 해싱 단위 테스트 (M1 B1).

pytest asyncio_mode=auto 라 async 함수에 별도 데코레이터 불필요.
순수 함수라 DB 픽스처는 쓰지 않는다.
"""

from src.services.auth_service import hash_password, verify_password


async def test_hash_verify_round_trip():
    hashed = await hash_password("correct horse battery staple")
    assert await verify_password("correct horse battery staple", hashed) is True


async def test_verify_rejects_wrong_password():
    hashed = await hash_password("s3cret-password!")
    assert await verify_password("wrong-password!", hashed) is False


async def test_same_plain_yields_different_hashes():
    # salt 때문에 같은 평문도 매번 다른 해시여야 한다 (레인보우 테이블 방지)
    h1 = await hash_password("same-password")
    h2 = await hash_password("same-password")
    assert h1 != h2
    # 그래도 둘 다 원래 평문으로 검증되어야 함
    assert await verify_password("same-password", h1) is True
    assert await verify_password("same-password", h2) is True


async def test_bcrypt_hash_format():
    hashed = await hash_password("whatever")
    # bcrypt 식별자 + 라운드. cost=12 반영 확인.
    assert hashed.startswith("$2b$12$")


async def test_long_password_not_truncated():
    """pre-hash 검증: 72바이트 이후만 다른 긴 비번 2개가 서로 다른 해시로 구분돼야 한다.

    pre-hash 없이 bcrypt에 직접 넣으면 72바이트에서 잘려 두 비번이 동일 취급되거나
    (bcrypt 5.x에선) ValueError가 난다. HMAC pre-hash가 이를 모두 막는지 확인.
    """
    base = "a" * 72
    pw1 = base + "DIFFERENT-TAIL-1"
    pw2 = base + "DIFFERENT-TAIL-2"

    hashed1 = await hash_password(pw1)
    # 같은 비번은 통과
    assert await verify_password(pw1, hashed1) is True
    # 73바이트째부터만 다른 비번은 거부돼야 함 (truncate 안 됐다는 증거)
    assert await verify_password(pw2, hashed1) is False
