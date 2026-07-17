"""오프셋 페이지네이션 헬퍼 (M2 결정 5 - 단일 작가·소규모 카탈로그라 keyset 불필요).

목록 API가 공통으로 쓰는 page/size 파라미터를 (offset, limit)으로 변환한다.
total count는 엔티티마다 필터가 달라 호출자(catalog_service)가 자체 쿼리로 채운다.
"""

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def compute_offset(page: int, size: int) -> tuple[int, int]:
    """1-based page/size를 (offset, limit)으로 변환. 범위 밖 값은 클램프한다.

    page < 1이면 1로, size는 [1, MAX_PAGE_SIZE]로 클램프(과도한 size로 풀스캔 방지).
    """
    page = max(page, 1)
    size = min(max(size, 1), MAX_PAGE_SIZE)
    return (page - 1) * size, size
