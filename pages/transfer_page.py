"""pages/transfer_page.py

이체 한도 시뮬레이터의 Page Object.

화면 접근을 이 클래스 안에만 두어, 마크업이 바뀌어도 테스트 코드는
건드리지 않도록 한다. 모든 요소는 data-testid로만 접근한다.

DB 조회(ledger_* 계열)는 화면과 무관한 별도 경로다. 앱이 렌더한 값이
아니라, 브라우저에 내장된 SQLite(sql.js)에 실제로 적재된 값을
page.evaluate로 SQL을 직접 실행해 읽어온다. 서버가 없어도 동작하므로
정적 페이지 그대로 배포해 링크 하나로 접속할 수 있다.
"""

from datetime import date, timedelta

from playwright.sync_api import Page

# 시뮬레이터의 기준 영업일. 화면은 날짜로 표시하고,
# 내부 계산과 DB(biz_date)는 이 날짜를 기준으로 한 실제 날짜 문자열을 쓴다.
BASE_DATE = date(2026, 9, 14)


class TransferPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    # ---------- 이동 ----------

    def open(self) -> "TransferPage":
        self.page.goto(self.base_url)
        self.page.wait_for_function("() => window.__dbInitDone === true")
        return self

    # ---------- 조회 ----------

    def _number(self, testid: str) -> int:
        text = self.page.get_by_test_id(testid).inner_text()
        return int(text.replace(",", ""))

    @property
    def once_limit(self) -> int:
        return self._number("once-limit")

    @property
    def daily_limit(self) -> int:
        return self._number("daily-limit")

    @property
    def daily_used(self) -> int:
        return self._number("daily-used")

    @property
    def daily_remaining(self) -> int:
        return self._number("daily-remaining")

    @property
    def current_date(self) -> date:
        """화면에 표시된 영업일(날짜)."""
        return date.fromisoformat(
            self.page.get_by_test_id("current-day").inner_text().strip()
        )

    @property
    def current_day(self) -> int:
        """기준일로부터의 영업일 오프셋. DB의 biz_date와 같은 단위."""
        return (self.current_date - BASE_DATE).days

    @property
    def error_visible(self) -> bool:
        return self.page.get_by_test_id("error-message").is_visible()

    @property
    def error_text(self) -> str:
        return self.page.get_by_test_id("error-message").inner_text()

    @property
    def success_visible(self) -> bool:
        return self.page.get_by_test_id("success-message").is_visible()

    @property
    def ledger_sum_today(self) -> int:
        """화면이 원장에서 직접 집계해 표시하는 당일 합계."""
        return self._number("ledger-sum-today")

    def _run_sql(self, sql: str, params: list | None = None) -> list[dict]:
        """브라우저에 내장된 SQLite(sql.js)에 SQL을 직접 실행한다.

        window.__runSQL은 앱이 노출해둔 함수로, db.exec()를 감싸
        컬럼명과 값을 매핑한 딕셔너리 목록을 돌려준다. 화면(state)이
        아니라 실제 SQLite 엔진에 대고 쿼리하는 것이므로, 화면 값과
        대조하면 독립적인 검증이 된다.
        """
        return self.page.evaluate(
            "([sql, params]) => window.__runSQL(sql, params)",
            [sql, params or []],
        )

    def ledger(self) -> list[dict]:
        """원장 레코드를 SQL로 직접 조회한다. 아직 한 건도 없으면 빈 리스트."""
        rows = self._run_sql(
            """SELECT id, amount, channel, status,
                      biz_date AS day, limit_at_time AS once_limit_at_time
               FROM transfer_ledger ORDER BY id"""
        )
        for r in rows:
            r["day"] = (date.fromisoformat(r["day"]) - BASE_DATE).days
        return rows

    def ledger_total_today(self) -> int:
        """당일 완료 건 합계를 SQL로 직접 집계한다.

        SELECT COALESCE(SUM(amount), 0) WHERE status='완료' AND biz_date=오늘
        화면의 소진액과는 완전히 분리된 경로이므로, 이 값과 대조해야
        표시값과 원장이 어긋난 상태를 잡아낼 수 있다.
        """
        today_str = (BASE_DATE + timedelta(days=self.current_day)).isoformat()
        rows = self._run_sql(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM transfer_ledger "
            "WHERE status = '완료' AND biz_date = ?",
            [today_str],
        )
        return rows[0]["s"] if rows else 0

    # ---------- 동작 ----------

    def _wait_for_db_sync(self) -> None:
        """sql.js 초기화 대기(dbReady)가 끝날 때까지 기다린다.

        최초 로드 시 WebAssembly 초기화가 비동기이므로, 화면 갱신 직후
        SQLite 적재가 아직 안 끝났을 수 있다. DB를 조회하기 전에는
        항상 이 대기를 거친다.
        """
        self.page.wait_for_function(
            "() => document.querySelector('[data-testid=\"pending-writes\"]').textContent === '0'"
        )

    def transfer(self, amount: int, channel: str = "app") -> "TransferPage":
        self.page.get_by_test_id("amount-input").fill(str(amount))
        self.page.get_by_test_id("channel-select").select_option(channel)
        self.page.get_by_test_id("transfer-btn").click()
        self._wait_for_db_sync()
        return self

    def transfer_concurrently(self, amount: int, channel: str = "app") -> "TransferPage":
        """동일 금액 2건을 동시에 요청한다."""
        self.page.get_by_test_id("amount-input").fill(str(amount))
        self.page.get_by_test_id("channel-select").select_option(channel)
        self.page.get_by_test_id("concurrent-btn").click()
        self._wait_for_db_sync()
        return self

    def cancel(self, transfer_id: int) -> "TransferPage":
        self.page.get_by_test_id(f"cancel-btn-{transfer_id}").click()
        self._wait_for_db_sync()
        return self

    def set_limits(self, once: int, daily: int) -> "TransferPage":
        self.page.get_by_test_id("new-once-input").fill(str(once))
        self.page.get_by_test_id("new-daily-input").fill(str(daily))
        self.page.get_by_test_id("apply-limit-btn").click()
        return self

    def advance_day(self) -> "TransferPage":
        self.page.get_by_test_id("advance-day-btn").click()
        return self

    def reset(self) -> "TransferPage":
        self.page.get_by_test_id("reset-btn").click()
        return self
