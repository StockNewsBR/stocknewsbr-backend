from datetime import datetime, timezone

from app.social.db import utc_social_datetime


def test_social_datetime_treats_naive_database_values_as_utc():
    naive = utc_social_datetime(datetime(2026, 7, 18, 13, 25))
    aware = utc_social_datetime(datetime(2026, 7, 18, 13, 25, tzinfo=timezone.utc))

    assert naive == aware
    assert naive.isoformat().replace("+00:00", "Z") == "2026-07-18T13:25:00Z"
    assert utc_social_datetime(None) is None
