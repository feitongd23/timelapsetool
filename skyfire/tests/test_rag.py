from skyfire.rag import factor_vector, similar_cases_from


def test_factor_vector_normalizes_and_defaults():
    v = factor_vector({"cloud_high": 50, "cloud_mid": 20, "cloud_low": 10,
                       "rh_2m": 70, "aod": 0.4, "channel": [], "hour": "2026-05-12T19:00"})
    assert len(v) == 7
    assert v[0] == 0.5           # cloud_high/100
    assert v[4] == 0.4           # aod/1.0(缺失时 0.5 中性)
    v2 = factor_vector({"cloud_high": 50, "hour": "2026-05-12T19:00"})
    assert v2[4] == 0.5          # aod 缺失 → 中性


def test_factor_vector_channel_blocked_fraction():
    payload = {"cloud_high": 50, "hour": "2026-05-12T19:00",
               "channel": [{"km": 100, "low": 90, "total": 95},
                           {"km": 200, "low": 5, "total": 10}]}
    v = factor_vector(payload)
    assert v[5] == 0.5           # 一半采样点被堵


def test_similar_cases_ranked_by_distance():
    target = factor_vector({"cloud_high": 50, "cloud_mid": 10, "cloud_low": 5,
                            "rh_2m": 70, "aod": 0.3, "channel": [],
                            "hour": "2026-07-04T19:00"})
    cases = [
        {"case_id": 1, "date": "2026-07-10", "actual_score": 9.0,
         "payload": {"cloud_high": 55, "cloud_mid": 12, "cloud_low": 6,
                     "rh_2m": 68, "aod": 0.35, "channel": [], "hour": "2026-07-10T19:00"}},
        {"case_id": 2, "date": "2026-01-20", "actual_score": 1.0,
         "payload": {"cloud_high": 0, "cloud_mid": 0, "cloud_low": 90,
                     "rh_2m": 30, "aod": 1.5, "channel": [], "hour": "2026-01-20T17:00"}},
        {"case_id": 3, "date": "2026-06-01", "actual_score": 6.0,
         "payload": {"cloud_high": 45, "cloud_mid": 20, "cloud_low": 10,
                     "rh_2m": 75, "aod": 0.3, "channel": [], "hour": "2026-06-01T19:00"}},
    ]
    top = similar_cases_from(cases, target, k=2)
    assert [c["case_id"] for c in top] == [1, 3]   # 最像的排前
    assert top[0]["distance"] < top[1]["distance"]
