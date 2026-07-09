"""LingoLoop backend — FastAPI + stdlib sqlite3.

Zero-API-cost personal language-learning loop:
  * POST /api/import  — strip markdown fences, json.loads, upsert into tables
  * GET  /api/quiz    — hard filter (consecutive_correct < 3), weighted sort, 15 items
  * PUT  /api/review  — persist an answer outcome
  * GET  /api/stats   — dashboard totals + mastery rate
Frontend (src/frontend) is served statically at "/".
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --------------------------------------------------------------------------- #
# Paths & configuration
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[2]          # .../LingoLoop
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "lingoloop.db"
FRONTEND_DIR = ROOT / "src" / "frontend"

MASTERY_THRESHOLD = 3   # consecutive_correct >= this  →  mastered (filtered out)
QUIZ_SIZE = 15


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
@contextmanager
def get_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS vocabulary (
                id                  TEXT PRIMARY KEY,
                word                TEXT NOT NULL,
                pronunciation       TEXT DEFAULT '',
                meaning             TEXT NOT NULL,
                options             TEXT NOT NULL,   -- JSON array of 4 strings
                correct_option      TEXT NOT NULL,
                wrong_count         INTEGER NOT NULL DEFAULT 0,
                consecutive_correct INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS grammar (
                id                  TEXT PRIMARY KEY,
                sentence            TEXT NOT NULL,   -- contains a ___ blank
                options             TEXT NOT NULL,   -- JSON array of 4 strings
                correct_option      TEXT NOT NULL,
                wrong_count         INTEGER NOT NULL DEFAULT 0,
                consecutive_correct INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT NOT NULL
            );
            """
        )


# --------------------------------------------------------------------------- #
# Smart parser — strip markdown fences, then json.loads
# --------------------------------------------------------------------------- #
_FENCE_RE = re.compile(r"```[a-zA-Z0-9]*\s*(.*?)\s*```", re.DOTALL)


def strip_and_load(raw: str) -> list[dict[str, Any]]:
    """Remove any markdown code fences / prose, then parse the JSON payload.

    Accepts a bare JSON list, a JSON object, or such wrapped in ```json fences
    with surrounding chatter. Always returns a list of item dicts.
    """
    if not raw or not raw.strip():
        raise ValueError("Empty input.")

    text = raw.strip()

    # 1) If fenced, take the content of the first code fence.
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    # 2) Drop a stray leading "json" language tag if it survived.
    text = re.sub(r"^json\s*", "", text, flags=re.IGNORECASE).strip()

    # 3) Try a direct parse; otherwise carve out the outermost [...] or {...}.
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in (text.find("["), text.find("{")) if i != -1], default=-1)
        end = max(text.rfind("]"), text.rfind("}"))
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object/array found in input.")
        data = json.loads(text[start : end + 1])

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("Parsed JSON must be an object or a list.")
    return data


def _first(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return default


def upsert_items(conn: sqlite3.Connection, items: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {"vocabulary": 0, "grammar": 0, "skipped": 0}
    for item in items:
        if not isinstance(item, dict):
            counts["skipped"] += 1
            continue
        itype = str(item.get("type", "")).strip().lower()
        options = _first(item, "options", default=[])
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except json.JSONDecodeError:
                options = [options]
        correct = _first(item, "correct_option", "answer", "correct")
        created_at = _first(item, "created_at", default="")
        item_id = str(_first(item, "id", default="")).strip()
        wrong = int(_first(item, "wrong_count", default=0) or 0)
        streak = int(_first(item, "consecutive_correct", default=0) or 0)

        if itype == "vocabulary":
            word = _first(item, "word", "term", "vocab")
            if not (item_id and word and correct):
                counts["skipped"] += 1
                continue
            conn.execute(
                """
                INSERT INTO vocabulary
                    (id, word, pronunciation, meaning, options, correct_option,
                     wrong_count, consecutive_correct, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    word=excluded.word,
                    pronunciation=excluded.pronunciation,
                    meaning=excluded.meaning,
                    options=excluded.options,
                    correct_option=excluded.correct_option
                """,
                (
                    item_id,
                    str(word),
                    str(_first(item, "pronunciation", "ipa", default="")),
                    str(_first(item, "meaning", "definition", default=correct)),
                    json.dumps(options, ensure_ascii=False),
                    str(correct),
                    wrong,
                    streak,
                    str(created_at),
                ),
            )
            counts["vocabulary"] += 1

        elif itype == "grammar":
            sentence = _first(item, "sentence", "question", "text")
            if not (item_id and sentence and correct):
                counts["skipped"] += 1
                continue
            conn.execute(
                """
                INSERT INTO grammar
                    (id, sentence, options, correct_option,
                     wrong_count, consecutive_correct, created_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    sentence=excluded.sentence,
                    options=excluded.options,
                    correct_option=excluded.correct_option
                """,
                (
                    item_id,
                    str(sentence),
                    json.dumps(options, ensure_ascii=False),
                    str(correct),
                    wrong,
                    streak,
                    str(created_at),
                ),
            )
            counts["grammar"] += 1
        else:
            counts["skipped"] += 1
    return counts


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
app = FastAPI(title="LingoLoop")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


# ---- API ------------------------------------------------------------------ #
class ReviewIn(BaseModel):
    id: str
    type: str
    correct: bool


@app.post("/api/import")
def api_import(payload: str = Body(..., media_type="text/plain")):
    try:
        items = strip_and_load(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Parse failed: {exc}")
    with get_db() as conn:
        counts = upsert_items(conn, items)
    return {"ok": True, "imported": counts}


def _recency_scores(rows: list[sqlite3.Row]) -> dict[str, int]:
    """Map each row id → recency score 0..100 (newest = 100)."""
    order = sorted(rows, key=lambda r: (r["created_at"] or ""))  # oldest → newest
    n = len(order)
    if n <= 1:
        return {r["id"]: 100 for r in order}
    return {r["id"]: round(100 * i / (n - 1)) for i, r in enumerate(order)}


@app.get("/api/quiz")
def api_quiz():
    with get_db() as conn:
        vocab = conn.execute(
            "SELECT * FROM vocabulary WHERE consecutive_correct < ?", (MASTERY_THRESHOLD,)
        ).fetchall()
        gram = conn.execute(
            "SELECT * FROM grammar WHERE consecutive_correct < ?", (MASTERY_THRESHOLD,)
        ).fetchall()

    recency = _recency_scores(list(vocab) + list(gram))

    def render(row: sqlite3.Row, kind: str) -> dict[str, Any]:
        base = {
            "id": row["id"],
            "type": kind,
            "options": json.loads(row["options"]),
            "correct_option": row["correct_option"],
            "wrong_count": row["wrong_count"],
            "consecutive_correct": row["consecutive_correct"],
            "_score": row["wrong_count"] * 10 + recency[row["id"]],
        }
        if kind == "vocabulary":
            base.update(
                word=row["word"],
                pronunciation=row["pronunciation"],
                meaning=row["meaning"],
            )
        else:
            base.update(sentence=row["sentence"])
        return base

    items = [render(r, "vocabulary") for r in vocab] + [render(r, "grammar") for r in gram]
    items.sort(key=lambda x: x["_score"], reverse=True)
    items = items[:QUIZ_SIZE]
    for it in items:
        it.pop("_score", None)
    return {"count": len(items), "items": items}


@app.put("/api/review")
def api_review(review: ReviewIn):
    table = "vocabulary" if review.type == "vocabulary" else "grammar"
    with get_db() as conn:
        row = conn.execute(f"SELECT id FROM {table} WHERE id = ?", (review.id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Item not found.")
        if review.correct:
            conn.execute(
                f"UPDATE {table} SET consecutive_correct = consecutive_correct + 1 WHERE id = ?",
                (review.id,),
            )
        else:
            conn.execute(
                f"UPDATE {table} SET wrong_count = wrong_count + 1, "
                f"consecutive_correct = 0 WHERE id = ?",
                (review.id,),
            )
    return {"ok": True}


@app.get("/api/stats")
def api_stats():
    with get_db() as conn:
        stats = {}
        total_items = total_mastered = 0
        for table in ("vocabulary", "grammar"):
            total = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
            mastered = conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE consecutive_correct >= ?",
                (MASTERY_THRESHOLD,),
            ).fetchone()["c"]
            due = conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE consecutive_correct < ?",
                (MASTERY_THRESHOLD,),
            ).fetchone()["c"]
            stats[table] = {"total": total, "mastered": mastered, "due": due}
            total_items += total
            total_mastered += mastered
        rate = round(100 * total_mastered / total_items) if total_items else 0
        stats["overall"] = {
            "total": total_items,
            "mastered": total_mastered,
            "mastery_rate": rate,
        }
    return stats


# ---- Static frontend (mounted last so /api/* wins) ------------------------ #
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
