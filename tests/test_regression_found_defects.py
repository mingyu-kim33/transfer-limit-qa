"""tests/test_regression_found_defects.py

무작위 시퀀스에서 발견된 결함을 고정 케이스로 옮겨둔 회귀 테스트.

랜덤 테스트는 매번 같은 경로를 밟지 않으므로, 한 번 발견된 결함은
반드시 결정적인 케이스로 내려 회귀를 막는다.
"""

from tests import invariants

ONCE = 1_000_000


class TestConcurrentLimitLeak:
    """DEF-01 · 한도 검사와 차감이 분리되어 동시 요청 시 한도가 새던 결함."""

    def test_concurrent_pair_cannot_exceed_daily_limit(self, app):
        app.transfer(ONCE)
        app.transfer_concurrently(ONCE)
        assert app.daily_used <= app.daily_limit
        invariants.assert_all(app, "잔여 1,000,000 상태에서 동시 2건 요청")


class TestCrossDayCancellation:
    """DEF-02 · 지난 날짜의 이체를 취소하면 오늘 소진액이 차감되던 결함.

    소진액이 음수가 되고, 그만큼 오늘 한도를 초과해 이체할 수 있었다.
    """

    def test_cancelling_yesterday_transfer_does_not_free_today_limit(self, app):
        app.transfer(ONCE)
        app.advance_day()
        assert app.daily_used == 0

        app.cancel(1)
        assert app.daily_used == 0, "전날 건 취소가 오늘 소진액을 바꿔서는 안 됨"
        invariants.assert_all(app, "전날 이체 취소")

    def test_cannot_exceed_daily_limit_via_cross_day_cancel(self, app):
        app.transfer(ONCE)
        app.advance_day()
        app.cancel(1)
        app.transfer(ONCE).transfer(ONCE).transfer(ONCE)
        app.transfer(ONCE)
        assert app.error_visible, "전날 건 취소로 오늘 한도가 늘어나서는 안 됨"
        invariants.assert_all(app, "전날 취소 후 한도 초과 시도")


class TestLimitLoweringBelowUsed:
    """DEF-03 · 소진액보다 낮게 한도를 내려 잔여가 음수가 되던 결함."""

    def test_lowering_below_used_is_rejected(self, app):
        app.transfer(ONCE).transfer(ONCE)
        app.set_limits(once=ONCE, daily=500_000)
        assert app.error_visible
        assert app.daily_remaining >= 0
        invariants.assert_all(app, "소진액 미만으로 한도 하향 시도")
