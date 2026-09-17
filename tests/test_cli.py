"""CLI wiring: month expansion, exit codes, and the ingest refusal."""

from __future__ import annotations

import pytest

from pipeline import cli


def test_expands_a_single_month():
    assert cli._expand_months(["2025-03"]) == [(2025, 3)]


def test_expands_a_range_across_a_year_boundary():
    assert cli._expand_months(["2024-11..2025-02"]) == [
        (2024, 11),
        (2024, 12),
        (2025, 1),
        (2025, 2),
    ]


def test_deduplicates_and_sorts():
    assert cli._expand_months(["2025-02", "2025-01", "2025-02"]) == [(2025, 1), (2025, 2)]


def test_rejects_a_backwards_range():
    with pytest.raises(SystemExit, match="backwards"):
        cli._expand_months(["2025-06..2025-01"])


def test_ingest_refuses_without_verification(data_root, capsys):
    assert cli.main(["ingest", "--months", "2025-01"]) == 2
    assert "Refusing to ingest an unverified source" in capsys.readouterr().err


def test_build_reports_no_data_clearly(data_root, capsys):
    assert cli.main(["build"]) == 2
    assert "Run `pipeline ingest" in capsys.readouterr().err


def test_query_without_a_database(data_root, capsys):
    assert cli.main(["query", "SELECT 1"]) == 2
    assert "Run `pipeline build` first" in capsys.readouterr().err


def test_status_runs_on_an_empty_tree(data_root, capsys):
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "NOT VERIFIED" in out
    assert "clean:     0 months" in out


def test_build_and_query_over_the_fixture(normalized, capsys):
    assert cli.main(["build"]) == 0
    capsys.readouterr()
    assert cli.main(["query", "SELECT count(*) AS n FROM operations", "--format", "json"]) == 0
    assert '"n": 22' in capsys.readouterr().out
