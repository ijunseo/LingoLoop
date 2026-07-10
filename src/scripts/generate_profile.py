"""LingoLoop DB로부터 learning_profile.md를 생성한다.

    uv run python src/scripts/generate_profile.py

data/lingoloop.db를 읽어, 다음 LLM 대화에 붙여넣을 'Context Injection' 리포트를
프로젝트 루트에 만든다. 리포트 본문은 AI 튜터에게 주입할 용도라 영어로 작성한다.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Windows 콘솔은 cp932/cp949일 수 있어, 이모지 출력이 죽지 않도록 UTF-8로 맞춘다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT: Path = Path(__file__).resolve().parents[2]
DB_PATH: Path = ROOT / "data" / "lingoloop.db"
OUT_PATH: Path = ROOT / "learning_profile.md"
MASTERY_THRESHOLD: int = 3
TOP_WEAK: int = 10       # 취약점 상위 N개
TOP_MASTERED: int = 5    # 최근 마스터 상위 N개


def connect() -> sqlite3.Connection:
    """DB에 연결한다. 파일이 없으면 안내 메시지와 함께 종료한다."""
    if not DB_PATH.exists():
        raise SystemExit(
            f"Database not found at {DB_PATH}.\n"
            "Import some data first (dashboard) or run seed_dummy.py."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_stats(conn: sqlite3.Connection, table: str) -> tuple[int, int]:
    """(전체 개수, 마스터 개수) 튜플을 반환한다."""
    total = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
    mastered = conn.execute(
        f"SELECT COUNT(*) c FROM {table} WHERE consecutive_correct >= ?",
        (MASTERY_THRESHOLD,),
    ).fetchone()["c"]
    return total, mastered


def weaknesses(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """오답이 있는 단어/문법을 wrong_count 내림차순으로 상위 TOP_WEAK개 반환한다."""
    rows: list[dict[str, Any]] = []
    for r in conn.execute(
        "SELECT word AS label, wrong_count, consecutive_correct FROM vocabulary "
        "WHERE wrong_count > 0"
    ):
        rows.append({"kind": "vocab", "label": r["label"], "wrong": r["wrong_count"]})
    for r in conn.execute(
        "SELECT sentence AS label, wrong_count, consecutive_correct FROM grammar "
        "WHERE wrong_count > 0"
    ):
        rows.append({"kind": "grammar", "label": r["label"], "wrong": r["wrong_count"]})
    rows.sort(key=lambda x: x["wrong"], reverse=True)
    return rows[:TOP_WEAK]


def recently_mastered(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """마스터된 항목을 최신순으로 상위 TOP_MASTERED개 반환한다."""
    rows: list[dict[str, Any]] = []
    for r in conn.execute(
        "SELECT word AS label, created_at FROM vocabulary "
        "WHERE consecutive_correct >= ? ORDER BY created_at DESC",
        (MASTERY_THRESHOLD,),
    ):
        rows.append({"kind": "vocab", "label": r["label"]})
    for r in conn.execute(
        "SELECT sentence AS label, created_at FROM grammar "
        "WHERE consecutive_correct >= ? ORDER BY created_at DESC",
        (MASTERY_THRESHOLD,),
    ):
        rows.append({"kind": "grammar", "label": r["label"]})
    return rows[:TOP_MASTERED]


def build_report(conn: sqlite3.Connection) -> str:
    """DB 통계를 바탕으로 learning_profile.md의 마크다운 문자열을 만든다."""
    v_total, v_mastered = table_stats(conn, "vocabulary")
    g_total, g_mastered = table_stats(conn, "grammar")
    total = v_total + g_total
    mastered = v_mastered + g_mastered
    rate = round(100 * mastered / total) if total else 0

    weak = weaknesses(conn)
    mastered_list = recently_mastered(conn)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    lines.append("# 🔄 LingoLoop — Learning Profile")
    lines.append("")
    lines.append(f"_Generated: {now}_")
    lines.append("")
    lines.append(
        "> **To the AI tutor:** This is my current Mandarin Chinese proficiency "
        "snapshot. Please naturally weave the *Current Weaknesses* below into today's "
        "conversation so I practice them, and feel free to build on my "
        "*Recently Mastered* items with more advanced usage."
    )
    lines.append("")

    lines.append("## 📊 Overall Stats")
    lines.append("")
    lines.append("| Category | Total | Mastered |")
    lines.append("|---|---|---|")
    lines.append(f"| Vocabulary | {v_total} | {v_mastered} |")
    lines.append(f"| Grammar | {g_total} | {g_mastered} |")
    lines.append(f"| **All** | **{total}** | **{mastered}** |")
    lines.append("")
    lines.append(f"**Mastery rate: {rate}%** (mastered = 3+ correct in a row)")
    lines.append("")

    lines.append("## ⚠️ Current Weaknesses (Top 10)")
    lines.append("")
    if weak:
        lines.append("_Please deliberately reuse these in our conversation:_")
        lines.append("")
        for i, w in enumerate(weak, 1):
            tag = "🔤" if w["kind"] == "vocab" else "📝"
            label = w["label"] if len(w["label"]) <= 80 else w["label"][:77] + "…"
            lines.append(f"{i}. {tag} **{label}** — missed {w['wrong']}×")
    else:
        lines.append("_No mistakes recorded yet. 🎉_")
    lines.append("")

    lines.append("## ✅ Recently Mastered (Top 5)")
    lines.append("")
    if mastered_list:
        lines.append("_Feel free to praise these and push me toward richer usage:_")
        lines.append("")
        for m in mastered_list:
            tag = "🔤" if m["kind"] == "vocab" else "📝"
            lines.append(f"- {tag} {m['label']}")
    else:
        lines.append("_Nothing mastered yet — keep looping!_")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """리포트를 생성해 learning_profile.md로 저장한다."""
    with connect() as conn:
        report = build_report(conn)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"✅ Wrote {OUT_PATH}")
    print("   Paste its contents into your next Gemini/ChatGPT/Claude chat.")


if __name__ == "__main__":
    main()
