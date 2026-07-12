"""generate_profile.py의 리포트 생성 테스트.

    uv run pytest
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))
sys.path.insert(0, str(ROOT / "src" / "scripts"))

import server  # noqa: E402
import generate_profile  # noqa: E402


def test_build_report_includes_ground_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """생성된 리포트에 세션 규칙(이미지 금지·유사표현·키포인트·왕초보)이 포함된다."""
    db_path = tmp_path / "profile_test.db"
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server, "DB_PATH", db_path)
    server.init_db()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        report = generate_profile.build_report(conn)

    assert "Ground Rules" in report
    assert "왕초보" in report
    assert "Never generate, attach, or reference an image" in report
    assert "similar expressions" in report
    assert "Key Point" in report
