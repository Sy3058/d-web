"""관리자(owner) 부트스트랩 스크립트 (M1.5 B1).

공개 관리자 가입 경로는 없다(보안 위험). 최초 owner는 운영자가 이 스크립트로 '기존
이메일 인증 유저'를 owner로 승격해 만든다. 승격된 유저는 다음 관리자 로그인에서 2FA
등록(B2)을 강제받는다.

실행(backend/ 에서):
    uv run python -m scripts.promote_admin user@example.com

멱등: 이미 owner면 아무것도 바꾸지 않는다. 미존재/미인증 유저는 거부한다.
role 부여는 권한 상승이라 실행 전 대상 이메일을 확인할 것.
"""

import asyncio
import sys

from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.db import async_session_maker
from src.models.user import RoleEnum
from src.services import auth_service


async def promote_user(email: str, session: AsyncSession) -> str:
    """이메일로 유저를 찾아 owner로 승격. 상태 문자열 반환(변경 시 commit 포함).

    세션을 인자로 받아 테스트가 테스트 세션을 주입할 수 있게 한다(IO/로직 분리).
    반환: "not_found" | "unverified" | "already_owner" | "promoted".
    """
    user = await auth_service.get_user_by_email(email, session)
    if user is None:
        return "not_found"
    if not user.is_email_verified:
        return "unverified"
    if user.role == RoleEnum.OWNER:
        return "already_owner"
    user.role = RoleEnum.OWNER
    session.add(user)
    await session.commit()
    return "promoted"


# 상태 -> (메시지 템플릿, 프로세스 종료 코드)
_RESULTS: dict[str, tuple[str, int]] = {
    "not_found": ("거부: '{email}' 유저가 없습니다(또는 탈퇴).", 1),
    "unverified": ("거부: '{email}' 는 이메일 미인증입니다. 인증 후 승격하세요.", 1),
    "already_owner": ("변경 없음: '{email}' 는 이미 owner 입니다.", 0),
    "promoted": ("승격 완료: '{email}' -> owner. 다음 로그인에서 2FA 등록이 강제됩니다.", 0),
}


async def _run(email: str) -> int:
    async with async_session_maker() as session:
        result = await promote_user(email, session)
    message, code = _RESULTS[result]
    print(message.format(email=email))
    return code


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run python -m scripts.promote_admin <email>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(_run(sys.argv[1])))


if __name__ == "__main__":
    main()
