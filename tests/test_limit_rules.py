"""tests/test_limit_rules.py

한도 규칙에 대한 케이스 기반 검증.

경계값은 손으로 나열하지 않고 한도 값에서 생성한다.
한도가 바뀌어도 테스트가 따라가도록 하기 위해서다.
"""

import pytest

from tests import invariants

ONCE = 1_000_000
DAILY = 3_000_000


def boundary_cases(limit: int):
    """한도 하나에서 -1 / 정확히 / +1 세 지점을 생성한다."""
    return [
        pytest.param(limit - 1, True, id=f"{limit:,}-1원_허용"),
        pytest.param(limit, True, id=f"{limit:,}원_정확히_허용"),
        pytest.param(limit + 1, False, id=f"{limit:,}+1원_차단"),
    ]


class TestOnceLimitBoundary:
    """1회 한도의 경계에서 허용과 차단이 갈리는 지점을 확인한다."""

    @pytest.mark.parametrize("amount,should_pass", boundary_cases(ONCE))
    def test_once_limit_boundary(self, app, amount, should_pass):
        app.transfer(amount)
        assert app.success_visible is should_pass, (
            f"{amount:,}원 이체는 {'허용' if should_pass else '차단'}되어야 함"
        )
        invariants.assert_all(app, f"{amount:,}원 이체")


class TestDailyLimitAccumulation:
    """1일 한도는 상태를 가진다. 누적이 정확한지 확인한다."""

    def test_daily_limit_blocks_on_remaining(self, app):
        app.transfer(ONCE).transfer(ONCE).transfer(ONCE)
        assert app.daily_used == DAILY
        assert app.daily_remaining == 0

        app.transfer(1)
        assert app.error_visible, "잔여 한도가 0이면 1원도 차단되어야 함"
        invariants.assert_all(app, "잔여 0에서 1원 이체 시도")

    def test_error_message_points_to_daily_not_once(self, app):
        """두 한도 중 어느 쪽에 걸렸는지 안내가 정확해야 한다."""
        app.transfer(ONCE).transfer(ONCE).transfer(ONCE)
        app.transfer(ONCE)
        assert "1일" in app.error_text, (
            f"1일 한도 초과인데 안내가 부정확함: {app.error_text}"
        )


class TestInvalidInput:
    """금액 입력 자체가 유효하지 않은 경우."""

    @pytest.mark.parametrize("amount", [0, -1, -1_000_000])
    def test_non_positive_amount_is_blocked(self, app, amount):
        app.transfer(amount)
        assert app.error_visible, f"{amount}원 이체는 차단되어야 함"
        invariants.assert_all(app, f"{amount}원 이체 시도")


class TestCancellationRestoresLimit:
    """취소된 이체는 소진액에서 빠져야 한다."""

    def test_cancel_restores_daily_used(self, app):
        app.transfer(ONCE)
        assert app.daily_used == ONCE

        app.cancel(1)
        assert app.daily_used == 0, "취소 후 소진액이 복구되어야 함"
        invariants.assert_all(app, "이체 취소")

    def test_cancelled_transfer_frees_room_for_new_one(self, app):
        app.transfer(ONCE).transfer(ONCE).transfer(ONCE)
        app.cancel(2)
        app.transfer(ONCE)
        assert app.success_visible, "취소로 확보된 한도로 재이체가 가능해야 함"
        invariants.assert_all(app, "취소 후 재이체")


class TestDayRollover:
    """일자가 바뀌면 소진액이 초기화되어야 한다."""

    def test_used_resets_on_next_day(self, app):
        app.transfer(ONCE).transfer(ONCE).transfer(ONCE)
        app.advance_day()
        assert app.daily_used == 0
        assert app.daily_remaining == DAILY

        app.transfer(ONCE)
        assert app.success_visible, "다음 날에는 다시 이체가 가능해야 함"
        invariants.assert_all(app, "일자 변경 후 이체")


class TestLimitChange:
    """한도를 낮췄을 때 이미 소진된 금액과의 관계."""

    def test_lowering_limit_below_used_is_rejected(self, app):
        """이미 소진한 금액보다 낮게 내리면 잔여가 음수가 된다. 차단되어야 한다."""
        app.transfer(ONCE).transfer(ONCE)
        app.set_limits(once=ONCE, daily=1_000_000)
        assert app.error_visible, "소진액보다 낮은 한도 설정은 차단되어야 함"
        invariants.assert_all(app, "소진액보다 낮게 한도 하향 시도")

    def test_lowering_limit_above_used_is_allowed(self, app):
        app.transfer(ONCE)
        app.set_limits(once=ONCE, daily=2_000_000)
        assert app.daily_limit == 2_000_000
        invariants.assert_all(app, "소진액보다 높게 한도 하향")


class TestConcurrency:
    """검사와 차감 사이의 간격에서 한도가 새는지 확인한다."""

    def test_concurrent_requests_do_not_exceed_daily_limit(self, app):
        app.transfer(ONCE)
        app.transfer_concurrently(ONCE)
        invariants.assert_all(app, "잔여 근접 상태에서 동시 2건 요청")
