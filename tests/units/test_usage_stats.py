from focus.core.usage_stats import summarize_lifetime, summarize_usage


def _row(**overrides):
    row = {
        "provider_type": "openrouter",
        "model_name": "vendor/model",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "cost": None,
        "cost_details": None,
    }
    row.update(overrides)
    return row


def test_one_bubble_sums_every_call():
    rows = [
        _row(prompt_tokens=1000, completion_tokens=100, total_tokens=1100, cached_tokens=500),
        _row(
            prompt_tokens=1500, completion_tokens=50, total_tokens=1550,
            cached_tokens=1000, reasoning_tokens=20,
        ),
    ]

    stats = summarize_usage(rows)

    values = {row["label"]: row["value"] for row in stats["stat_rows"]}
    assert values == {
        "Prompt": "2,500",
        "Cached": "1,500 (60%)",
        "Completion": "150",
        "Reasoning": "20",
        "Total": "2,650",
    }
    assert [call["label"] for call in stats["calls"]] == ["Call 1", "Call 2"]
    assert stats["calls"][1]["tokens"] == "1,500 → 50"
    assert stats["origin"] == "openrouter · vendor/model"


def test_cost_totals_and_details_sum():
    rows = [
        _row(cost=0.001, cost_details='{"upstream_inference_cost": 0.001}'),
        _row(cost=0.002, cost_details='{"upstream_inference_cost": 0.002, "upstream": "openai"}'),
    ]

    stats = summarize_usage(rows)

    assert stats["cost"] == "<$0.01"
    assert stats["calls"][0]["cost"] == "<$0.01"
    details = {row["label"]: row["value"] for row in stats["details"]}
    assert details == {"Upstream inference cost": "<$0.01", "Upstream": "openai"}


def test_unreported_fields_stay_absent():
    stats = summarize_usage([_row(prompt_tokens=10, completion_tokens=5, total_tokens=15)])

    labels = [row["label"] for row in stats["stat_rows"]]
    assert "Cached" not in labels
    assert "Reasoning" not in labels
    assert stats["cost"] == "—"
    assert stats["calls"][0]["cost"] == "—"
    assert stats["details"] == []


def test_malformed_cost_details_are_ignored():
    stats = summarize_usage([_row(cost_details="{not json")])
    assert stats["details"] == []


def test_null_cost_detail_is_not_the_string_none():
    stats = summarize_usage([_row(cost_details='{"upstream": null}')])
    assert stats["details"] == [{"label": "Upstream", "value": "—"}]


def test_total_falls_back_to_the_halves():
    stats = summarize_usage([_row(prompt_tokens=400, completion_tokens=100)])
    values = {row["label"]: row["value"] for row in stats["stat_rows"]}
    assert values["Total"] == "500"


def test_lifetime_total_falls_back_to_the_halves():
    rows = [{"provider_type": "local", "model_name": "m", "calls": 1,
             "prompt_tokens": 400, "completion_tokens": 100, "total_tokens": 0,
             "cached_tokens": 0, "reasoning_tokens": 0, "cost": None}]

    stats = summarize_lifetime(rows)

    values = {row["label"]: row["value"] for row in stats["stat_rows"]}
    assert values["Total"] == "500"
    assert stats["models"][0]["tokens"] == 500
    assert stats["models"][0]["share_label"] == "100.0%"


def test_lifetime_totals_share_and_cost():
    rows = [
        {"provider_type": "openrouter", "model_name": "a/one", "calls": 3,
         "prompt_tokens": 3000, "completion_tokens": 500, "total_tokens": 3500,
         "cached_tokens": 1000, "reasoning_tokens": 0, "cost": 0.01},
        {"provider_type": "nanogpt", "model_name": "b/two", "calls": 1,
         "prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500,
         "cached_tokens": 0, "reasoning_tokens": 0, "cost": 0.005},
    ]

    stats = summarize_lifetime(rows)

    assert stats["cost"] == "$0.01"
    assert stats["calls"] == 4
    values = {row["label"]: row["value"] for row in stats["stat_rows"]}
    assert values["Prompt"] == "4,000"
    assert values["Cached"] == "1,000 (25%)"
    assert values["Total"] == "5,000"
    assert [(m["model"], m["share"], m["share_label"]) for m in stats["models"]] == [
        ("a/one", "70.0", "70.0%"),
        ("b/two", "30.0", "30.0%"),
    ]


def test_lifetime_without_usage():
    stats = summarize_lifetime([])
    assert stats["models"] == []
    assert stats["calls"] == 0
    assert stats["cost"] == "—"
