"""Layer 8 evaluation runner. Prints labeled baseline output."""

from tests.evaluation.harness import format_report, run_evaluation


def test_evaluation_runner_executes():
    # Do not use capsys: that fixture captures stdout even with pytest -s,
    # so the evaluation summary never reaches the terminal.
    report = run_evaluation()
    summary = format_report(report)
    print(summary)
    print()
    print("Case details")
    print("------------")
    for result in report.results:
        behavioral = (
            "PASS"
            if result.passed_behavioral
            else ("FAIL" if result.passed_behavioral is False else "n/a")
        )
        fixture = (
            "PASS"
            if result.passed_fixture_retrieval
            else ("FAIL" if result.passed_fixture_retrieval is False else "n/a")
        )
        extra = f" failures={result.failures}" if result.failures else ""
        print(
            f"{result.case.case_id:32} behavioral={behavioral:4} "
            f"fixture_retrieval={fixture:4} harness_ms={result.harness_total_latency_ms}"
            f"{extra}"
        )

    assert report.total >= 20
    behavioral = [r for r in report.results if r.passed_behavioral is not None]
    failed = [r.case.case_id for r in behavioral if not r.passed_behavioral]
    assert failed == [], f"behavioral regressions: {failed}"

    assert "1) Behavioral / regression" in summary
    assert "2) Fixture-based retrieval baseline" in summary
    assert "3) Harness latency measurements" in summary
    assert "NOT Qdrant cosine search" in summary
    assert "NOT production retrieval accuracy" in summary
    assert "NOT production latency. NOT an SLO." in summary
