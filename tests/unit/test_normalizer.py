from datetime import timezone
from uuid import uuid4

import pytest

from app.processing.normalizer import ActivityNormalizer


def test_normalizes_multiple_timestamp_formats_to_utc():
    normalizer = ActivityNormalizer()
    rid, uid = uuid4(), uuid4()
    rows = normalizer.normalize([
        {"source": "git", "activity_type": "commit", "activity_ts": "2026-07-18T00:00:00Z"},
        {"source": "slack", "activity_type": "message", "activity_ts": "1784360662.0"},
    ], rid, uid)
    assert all(item.activity_ts.tzinfo == timezone.utc for item in rows)


def test_missing_required_field_raises():
    with pytest.raises(ValueError):
        ActivityNormalizer().normalize([{"source": "git"}], uuid4(), uuid4())
