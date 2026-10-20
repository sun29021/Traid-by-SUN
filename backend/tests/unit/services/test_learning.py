import math

import pytest

from app.services.learning import DEFAULTS, acceptance_rate, ema_params, update_typical_region


def test_ema_moves_a_fifth_of_the_way_and_drops_defaults() -> None:
    first = ema_params({}, {**DEFAULTS, "dx": 5.0})
    assert first == {"dx": 1.0}

    second = ema_params(first, {**DEFAULTS, "dx": 5.0})
    assert second["dx"] == pytest.approx(1.8)

    # Accepting with default adjustments decays the learned value back.
    decayed = ema_params(second, dict(DEFAULTS))
    assert decayed["dx"] == pytest.approx(1.44)
    assert "scale" not in decayed and "grain" not in decayed


def test_ema_converges_to_the_owners_habit() -> None:
    learned: dict[str, float] = {}
    for _ in range(40):
        learned = ema_params(learned, {**DEFAULTS, "ink_tone": 0.4, "grain": 1.5})
    assert learned["ink_tone"] == pytest.approx(0.4, abs=1e-3)
    assert learned["grain"] == pytest.approx(1.5, abs=1e-3)


def test_typical_region_running_mean_and_spread() -> None:
    def quad(cx: float, cy: float) -> list[list[float]]:
        return [[cx - 50, cy - 10], [cx + 50, cy - 10], [cx + 50, cy + 10], [cx - 50, cy + 10]]

    region = update_typical_region(None, quad(500, 400), 1000, 800)
    assert region["count"] == 1
    assert region["cx"] == pytest.approx(0.5) and region["sx"] == 0.0
    assert region["w"] == pytest.approx(0.1)

    for cx in (600, 700):
        region = update_typical_region(region, quad(cx, 400), 1000, 800)

    assert region["count"] == 3
    assert region["cx"] == pytest.approx(0.6)
    assert region["sx"] == pytest.approx(math.sqrt(((0.1**2) * 2) / 2), abs=1e-4)
    assert region["cy"] == pytest.approx(0.5) and region["sy"] == pytest.approx(0.0, abs=1e-6)


def test_acceptance_rate() -> None:
    assert acceptance_rate(0, 0) is None
    assert acceptance_rate(3, 1) == 0.75
