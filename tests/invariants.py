"""tests/invariants.py

이체 한도 기능이 어떤 경로로 조작되든 항상 참이어야 하는 규칙들.

개별 테스트 케이스가 "이 조건에서 이렇게 동작하는가"를 묻는다면,
불변식은 "무슨 일이 있어도 이것만은 깨지면 안 된다"를 묻는다.
돈이 오가는 기능에서 회귀를 잡아내는 건 대체로 후자다.

각 함수는 위반 사유 문자열을 반환하고, 문제가 없으면 None을 반환한다.
"""

from pages.transfer_page import TransferPage

Violation = str | None


def ledger_matches_used(page: TransferPage) -> Violation:
    """INV-01 · 화면의 소진액은 SQLite 원장의 당일 합계와 일치해야 한다.

    소진액은 브라우저가 들고 있는 값이고, 원장은 서버가 SQLite에
    저장하는 원본이다. 둘은 완전히 분리된 경로로 갱신되므로, 어긋나는
    순간 화면의 잔여 한도를 신뢰할 수 없게 된다.
    """
    expected = page.ledger_total_today()
    actual = page.daily_used
    if expected != actual:
        return f"INV-01 원장 불일치: 화면 소진액 {actual:,} vs 원장 합계 {expected:,}"
    return None


def used_never_exceeds_daily_limit(page: TransferPage) -> Violation:
    """INV-02 · 소진액은 1일 한도를 넘을 수 없다.

    한도의 존재 이유 그 자체. 넘는 순간 한도는 기능하지 않은 것이다.
    """
    if page.daily_used > page.daily_limit:
        return f"INV-02 한도 초과: 소진 {page.daily_used:,} > 한도 {page.daily_limit:,}"
    return None


def remaining_is_never_negative(page: TransferPage) -> Violation:
    """INV-03 · 잔여 한도는 음수가 될 수 없다.

    음수 잔여는 사용자에게 노출되면 안 되는 상태이며,
    이후 계산이 전부 오염된다.
    """
    if page.daily_remaining < 0:
        return f"INV-03 잔여 한도 음수: {page.daily_remaining:,}"
    return None


def remaining_equals_limit_minus_used(page: TransferPage) -> Violation:
    """INV-04 · 잔여 한도 = 1일 한도 - 소진액.

    화면에 표시되는 세 숫자가 서로 어긋나지 않아야 한다.
    """
    expected = page.daily_limit - page.daily_used
    if page.daily_remaining != expected:
        return (
            f"INV-04 잔여 한도 계산 오류: 표시 {page.daily_remaining:,} "
            f"vs 기대 {expected:,}"
        )
    return None


def screen_sum_matches_ledger_sum(page: TransferPage) -> Violation:
    """INV-06 · 화면(JS)이 계산한 원장 합계와, SQLite를 SQL로 직접 집계한 값이 같아야 한다.

    화면의 집계 로직 자체가 SQLite의 실제 데이터와 어긋나는 경우를 잡는다.
    """
    if page.ledger_sum_today != page.ledger_total_today():
        return (
            f"INV-06 원장 집계 오류: 표시 {page.ledger_sum_today:,} "
            f"vs 레코드 합계 {page.ledger_total_today():,}"
        )
    return None


def no_single_transfer_exceeds_once_limit(page: TransferPage) -> Violation:
    """INV-05 · 완료된 이체는 그 시점의 1회 한도 이하여야 한다.

    한도 하향은 미래 이체에만 적용되므로, 현재 상한이 아니라
    이체 시점에 적용됐던 상한과 대조해야 한다. 이 구분이 없으면
    한도를 낮추는 것만으로 과거 정상 거래가 위반으로 잡힌다.
    """
    for h in page.ledger():
        if h["status"] == "완료" and h["amount"] > h["once_limit_at_time"]:
            return (
                f"INV-05 1회 한도 초과 건 존재: #{h['id']} {h['amount']:,} "
                f"> 이체 시점 한도 {h['once_limit_at_time']:,}"
            )
    return None


ALL_INVARIANTS = [
    ledger_matches_used,
    used_never_exceeds_daily_limit,
    remaining_is_never_negative,
    remaining_equals_limit_minus_used,
    no_single_transfer_exceeds_once_limit,
    screen_sum_matches_ledger_sum,
]


def check_all(page: TransferPage, context: str = "") -> list[str]:
    """모든 불변식을 검사하고 위반 목록을 반환한다."""
    violations = []
    for rule in ALL_INVARIANTS:
        result = rule(page)
        if result:
            violations.append(f"{result}{f'  (직전 동작: {context})' if context else ''}")
    return violations


def assert_all(page: TransferPage, context: str = "") -> None:
    violations = check_all(page, context)
    assert not violations, "\n".join(violations)
