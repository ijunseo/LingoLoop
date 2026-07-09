"""Generate learning_profile.md from the LingoLoop database.

    uv run python src/scripts/generate_profile.py

Reads data/lingoloop.db and writes a Context-Injection report to the project
root that you paste into your next LLM chat so it teaches to your weaknesses.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows consoles may be cp932/cp949; keep emoji-friendly output from crashing.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "lingoloop.db"
OUT_PATH = ROOT / "learning_profile.md"
MASTERY_THRESHOLD = 3
TOP_WEAK = 10
TOP_MASTERED = 5


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise SystemExit(
            f"Database not found at {DB_PATH}.\n"
            "Import some data first (dashboard) or run seed_dummy.py."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_stats(conn: sqlite3.Connection, table: str) -> tuple[int, int]:
    total = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
    mastered = conn.execute(
        f"SELECT COUNT(*) c FROM {table} WHERE consecutive_correct >= ?",
        (MASTERY_THRESHOLD,),
    ).fetchone()["c"]
    return total, mastered


def weaknesses(conn: sqlite3.Connection) -> list[dict]:
    rows = []
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


def recently_mastered(conn: sqlite3.Connection) -> list[dict]:
    rows = []
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
        "> **To the AI tutor:** This is my current English proficiency snapshot. "
        "Please naturally weave the *Current Weaknesses* below into today's "
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
    with connect() as conn:
        report = build_report(conn)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"✅ Wrote {OUT_PATH}")
    print("   Paste its contents into your next Gemini/ChatGPT/Claude chat.")


if __name__ == "__main__":
    main()
