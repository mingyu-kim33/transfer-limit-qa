"""tests/test_random_sequence.py

무작위 동작 시퀀스를 실행하며 매 단계마다 불변식을 검사한다.

케이스를 나열하는 방식은 사람이 상상한 조합까지만 검증한다.
여기서는 조합을 만들지 않고, 지켜져야 할 규칙만 정의한 뒤
시스템을 흔들어 규칙이 깨지는 지점을 찾는다.

위반이 발견되면 그때까지의 동작 순서를 그대로 출력해,
수동으로 재현할 수 있는 절차서가 되도록 한다.
"""

import random

import pytest

from tests import invariants

SEEDS = [1, 7, 42, 99, 2024]
STEPS_PER_SEED = 40

AMOUNTS = [1, 100_000, 500_000, 999_999, 1_000_000, 1_000_001]


def _pick_action(rng: random.Random, app):
    """다음에 수행할 동작 하나를 고른다."""
    actions = ["transfer", "transfer", "transfer", "concurrent", "advance_day", "limit"]
    if any(h["status"] == "완료" for h in app.ledger()):
        actions.append("cancel")
    return rng.choice(actions)


def _execute(action: str, rng: random.Random, app) -> str:
    """동작을 수행하고, 재현 절차에 남길 설명을 반환한다."""
    if action == "transfer":
        amount = rng.choice(AMOUNTS)
        app.transfer(amount)
        return f"{amount:,}원 이체"

    if action == "concurrent":
        amount = rng.choice(AMOUNTS)
        app.transfer_concurrently(amount)
        return f"{amount:,}원 동시 2건 요청"

    if action == "cancel":
        completed = [h["id"] for h in app.ledger() if h["status"] == "완료"]
        target = rng.choice(completed)
        app.cancel(target)
        return f"이체 #{target} 취소"

    if action == "advance_day":
        app.advance_day()
        return f"다음 날로 이동 ({app.current_date})"

    if action == "limit":
        once = rng.choice([500_000, 1_000_000, 2_000_000])
        daily = rng.choice([1_000_000, 3_000_000, 5_000_000])
        app.set_limits(once=once, daily=daily)
        return f"한도 변경 (1회 {once:,} / 1일 {daily:,})"

    raise ValueError(action)


@pytest.mark.parametrize("seed", SEEDS)
def test_invariants_hold_under_random_sequence(app, seed):
    rng = random.Random(seed)
    trail: list[str] = []

    for step in range(1, STEPS_PER_SEED + 1):
        action = _pick_action(rng, app)
        description = _execute(action, rng, app)
        trail.append(f"  {step:>2}. {description}")

        violations = invariants.check_all(app)
        if violations:
            reproduction = "\n".join(trail)
            pytest.fail(
                f"\nseed={seed}, {step}번째 동작에서 불변식 위반\n\n"
                f"[위반 내용]\n" + "\n".join(f"  {v}" for v in violations) + "\n\n"
                f"[재현 절차]\n{reproduction}\n"
            )
