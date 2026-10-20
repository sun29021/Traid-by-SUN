"""How a profile learns from the owner's decisions (PRD FR-P05/P06, ARCHITECTURE §5.3).

Inside the accept/reject transaction:

1. glyph counters: accepted renders raise `accept_count` of every bank glyph used,
   rejected ones `reject_count` (selection weight = (1 + a) / (1 + a + 2r));
2. `learned_params`: exponential moving average (alpha = 0.2) of the adjustments on
   accepted jobs, used as the starting adjustments of the next job;
3. `typical_region`: running mean and spread of where the token sits in the image
   (normalised centre and size), used to preselect the right text line.

No neural network is trained; Traid "learns" by curating and ranking real data.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.db.models import EditJob, Profile, StoredFile
from app.db.models.enums import JobStatus
from app.repositories import jobs as jobs_repo
from app.schemas.jobs import RenderParamsIn

ALPHA = 0.2
PARAM_KEYS = ("dx", "dy", "scale", "spacing", "weight", "blur", "ink_tone", "grain")
DEFAULTS: dict[str, float] = {
    key: float(value) for key, value in RenderParamsIn().model_dump().items() if key in PARAM_KEYS
}
# Learned values this close to the default are dropped (keeps learned_params readable).
_EPSILON = 1e-3
HISTORY_DAYS = 14


def ema_params(learned: dict[str, Any] | None, params: dict[str, Any]) -> dict[str, float]:
    """One EMA step towards the accepted adjustments; only non-default results are kept."""
    current = {key: float((learned or {}).get(key, DEFAULTS[key])) for key in PARAM_KEYS}
    updated: dict[str, float] = {}
    for key in PARAM_KEYS:
        value = float(params.get(key, DEFAULTS[key]))
        blended = (1 - ALPHA) * current[key] + ALPHA * value
        if abs(blended - DEFAULTS[key]) > _EPSILON:
            updated[key] = round(blended, 4)
    return updated


def update_typical_region(
    typical: dict[str, Any] | None, quad: list[list[float]], width: int, height: int
) -> dict[str, Any]:
    """Welford update of the normalised token centre (cx, cy) and size (w, h)."""
    xs = [p[0] / max(width, 1) for p in quad]
    ys = [p[1] / max(height, 1) for p in quad]
    sample = {
        "cx": sum(xs) / 4,
        "cy": sum(ys) / 4,
        "w": max(xs) - min(xs),
        "h": max(ys) - min(ys),
    }
    state = dict(typical or {})
    count = int(state.get("count", 0)) + 1
    result: dict[str, Any] = {"count": count}
    for key, value in sample.items():
        mean = float(state.get(key, value))
        m2 = float(state.get(f"m2_{key}", 0.0))
        delta = value - mean
        mean = mean + delta / count if count > 1 else value
        m2 = m2 + delta * (value - mean) if count > 1 else 0.0
        result[key] = round(mean, 5)
        result[f"m2_{key}"] = round(m2, 7)
    for key, spread in (("cx", "sx"), ("cy", "sy")):
        variance = result[f"m2_{key}"] / (count - 1) if count > 1 else 0.0
        result[spread] = round(math.sqrt(variance), 5)
    return result


def on_accept(session: Session, job: EditJob) -> None:
    jobs_repo.bump_glyph_counters(session, jobs_repo.job_glyph_ids(session, job.id), accepted=True)
    profile = session.get(Profile, job.profile_id)
    if profile is None:  # pragma: no cover - FK guarantees it
        return
    profile.learned_params = ema_params(profile.learned_params, job.params or {})
    stored = session.get(StoredFile, job.input_file_id)
    if job.selected_quad and stored is not None and stored.width and stored.height:
        profile.typical_region = update_typical_region(
            profile.typical_region, job.selected_quad, stored.width, stored.height
        )


def on_reject(session: Session, job: EditJob) -> None:
    jobs_repo.bump_glyph_counters(session, jobs_repo.job_glyph_ids(session, job.id), accepted=False)


def decision_counts(session: Session, profile_ids: list[str]) -> dict[str, tuple[int, int]]:
    """(accepted, rejected) single jobs per profile."""
    rows = session.execute(
        select(EditJob.profile_id, EditJob.status, func.count())
        .where(
            EditJob.profile_id.in_(profile_ids),
            EditJob.status.in_([JobStatus.ACCEPTED.value, JobStatus.REJECTED.value]),
        )
        .group_by(EditJob.profile_id, EditJob.status)
    ).all()
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for profile_id, status, count in rows:
        counts[profile_id][0 if status == JobStatus.ACCEPTED.value else 1] += int(count)
    return {pid: (c[0], c[1]) for pid, c in counts.items()}


def acceptance_rate(accepted: int, rejected: int) -> float | None:
    decided = accepted + rejected
    return round(accepted / decided, 4) if decided else None


def summary(session: Session, profile: Profile) -> dict[str, Any]:
    accepted, rejected = decision_counts(session, [profile.id]).get(profile.id, (0, 0))
    since = utcnow() - timedelta(days=HISTORY_DAYS - 1)
    start = datetime(since.year, since.month, since.day, tzinfo=UTC)
    jobs = session.execute(
        select(EditJob.status, EditJob.accepted_at, EditJob.updated_at).where(
            EditJob.profile_id == profile.id,
            EditJob.status.in_([JobStatus.ACCEPTED.value, JobStatus.REJECTED.value]),
            EditJob.updated_at >= start,
        )
    ).all()
    days = {(start + timedelta(days=i)).date().isoformat(): [0, 0] for i in range(HISTORY_DAYS)}
    for status, accepted_at, updated_at in jobs:
        moment = accepted_at if status == JobStatus.ACCEPTED.value and accepted_at else updated_at
        bucket = days.get(moment.astimezone(UTC).date().isoformat())
        if bucket is not None:
            bucket[0 if status == JobStatus.ACCEPTED.value else 1] += 1
    typical = profile.typical_region or {}
    return {
        "accepted": accepted,
        "rejected": rejected,
        "acceptance_rate": acceptance_rate(accepted, rejected),
        "learned_params": profile.learned_params or {},
        "typical_region": (
            {k: typical[k] for k in ("count", "cx", "cy", "sx", "sy", "w", "h") if k in typical}
            or None
        ),
        "history": [
            {"date": day, "accepted": counts[0], "rejected": counts[1]}
            for day, counts in days.items()
        ],
    }
