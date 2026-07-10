"""LingoLoop 백엔드 — FastAPI + 표준 라이브러리 sqlite3.

API 유지비용 0원(Zero API Cost)을 지향하는 개인용 언어 학습 루프의 서버.

엔드포인트:
  * POST /api/import  — 마크다운 백틱 제거 후 json.loads, 테이블에 upsert
  * GET  /api/quiz    — 하드 필터(consecutive_correct < 3) + 가중 정렬로 15개 반환
  * PUT  /api/review  — 정답/오답 결과를 DB에 영속화
  * GET  /api/stats   — 대시보드용 전체 통계 + 마스터율
프론트엔드(src/frontend)는 "/" 에 정적(static)으로 서빙된다.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Iterator

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --------------------------------------------------------------------------- #
# 경로 및 설정 (Paths & configuration)
# --------------------------------------------------------------------------- #
ROOT: Path = Path(__file__).resolve().parents[2]          # .../LingoLoop
DATA_DIR: Path = ROOT / "data"
DB_PATH: Path = DATA_DIR / "lingoloop.db"
FRONTEND_DIR: Path = ROOT / "src" / "frontend"

MASTERY_THRESHOLD: int = 3   # consecutive_correct >= 이 값이면 마스터(퀴즈에서 제외)
QUIZ_SIZE: int = 15          # 퀴즈 1회에 반환할 문항 수


# --------------------------------------------------------------------------- #
# 데이터베이스 (Database)
# --------------------------------------------------------------------------- #
@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """SQLite 커넥션을 여는 컨텍스트 매니저.

    정상 종료 시 자동으로 commit 하고, 어떤 경우든 마지막에 커넥션을 닫는다.
    `row_factory`를 sqlite3.Row로 두어 컬럼명을 키로 접근할 수 있게 한다.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """vocabulary / grammar 테이블이 없으면 생성한다. (idempotent)"""
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
                sentence            TEXT NOT NULL,   -- ___ 빈칸을 포함
                options             TEXT NOT NULL,   -- JSON array of 4 strings
                correct_option      TEXT NOT NULL,
                wrong_count         INTEGER NOT NULL DEFAULT 0,
                consecutive_correct INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT NOT NULL
            );
            """
        )


# --------------------------------------------------------------------------- #
# 스마트 파서 — 마크다운 백틱 제거 후 json.loads
# --------------------------------------------------------------------------- #
_FENCE_RE = re.compile(r"```[a-zA-Z0-9]*\s*(.*?)\s*```", re.DOTALL)


def strip_and_load(raw: str) -> list[dict[str, Any]]:
    """LLM 출력에서 마크다운 백틱/잡설을 제거한 뒤 JSON을 파싱한다.

    순수 JSON 리스트, 단일 JSON 객체, 또는 ```json 코드펜스로 감싸이고 앞뒤에
    설명 문장이 붙은 형태까지 허용한다. 항상 item dict의 리스트를 돌려준다.

    Args:
        raw: 사용자가 붙여넣은 원본 텍스트.

    Returns:
        파싱된 항목 dict들의 리스트.

    Raises:
        ValueError: 입력이 비었거나 JSON을 찾지 못한 경우.
    """
    if not raw or not raw.strip():
        raise ValueError("Empty input.")

    text = raw.strip()

    # 1) 코드펜스가 있으면 첫 번째 펜스 안의 내용만 취한다.
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    # 2) 남아있을 수 있는 선두 "json" 언어 태그를 제거한다.
    text = re.sub(r"^json\s*", "", text, flags=re.IGNORECASE).strip()

    # 3) 우선 그대로 파싱을 시도하고, 실패하면 가장 바깥의 [...] 또는 {...}를 잘라낸다.
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
    """item에서 keys를 순서대로 확인해, 값이 있는 첫 키의 값을 반환한다.

    LLM마다 필드명이 조금씩 다를 수 있어(예: word/term) 이를 흡수하기 위한 헬퍼.
    빈 문자열('')과 None은 '값 없음'으로 취급한다.
    """
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return default


def upsert_items(conn: sqlite3.Connection, items: Iterable[dict[str, Any]]) -> dict[str, int]:
    """항목들을 type에 따라 vocabulary/grammar 테이블에 upsert 한다.

    id가 충돌하면 본문 필드만 갱신하고 카운터(wrong_count/consecutive_correct)와
    created_at은 보존한다. 즉 재임포트해도 학습 진행도가 초기화되지 않는다.

    Args:
        conn: 열려 있는 SQLite 커넥션.
        items: 파싱된 항목 dict들.

    Returns:
        {"vocabulary": n, "grammar": m, "skipped": k} 형태의 처리 건수.
    """
    counts: dict[str, int] = {"vocabulary": 0, "grammar": 0, "skipped": 0}
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
# 앱 (App)
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """서버 기동 시 DB 스키마를 준비한다."""
    init_db()
    yield


app = FastAPI(title="LingoLoop", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- API ------------------------------------------------------------------ #
class ReviewIn(BaseModel):
    """PUT /api/review 요청 바디.

    Attributes:
        id: 항목의 UUID.
        type: "vocabulary" 또는 "grammar".
        correct: 이번 결과가 정답이면 True.
    """

    id: str
    type: str
    correct: bool


@app.post("/api/import")
def api_import(payload: str = Body(..., media_type="text/plain")) -> dict[str, Any]:
    """원본 텍스트(text/plain)를 파싱해 DB에 upsert 한다.

    Raises:
        HTTPException(400): 파싱에 실패한 경우.
    """
    try:
        items = strip_and_load(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Parse failed: {exc}")
    with get_db() as conn:
        counts = upsert_items(conn, items)
    return {"ok": True, "imported": counts}


def _recency_scores(rows: list[sqlite3.Row]) -> dict[str, int]:
    """각 행 id를 최신성 점수(0~100, 최신=100)에 매핑한다.

    created_at 기준 오름차순으로 정렬해 순위를 0~100으로 정규화한다.
    """
    order = sorted(rows, key=lambda r: (r["created_at"] or ""))  # 오래된 → 최신
    n = len(order)
    if n <= 1:
        return {r["id"]: 100 for r in order}
    return {r["id"]: round(100 * i / (n - 1)) for i, r in enumerate(order)}


@app.get("/api/quiz")
def api_quiz() -> dict[str, Any]:
    """복습 문항을 반환한다.

    consecutive_correct < MASTERY_THRESHOLD 인 항목만 대상으로 하며(하드 필터),
    `wrong_count * 10 + 최신성(0~100)` 점수 내림차순으로 상위 QUIZ_SIZE개를 준다.
    정답 채점은 프론트에서 하므로 correct_option도 함께 내려준다.
    """
    with get_db() as conn:
        vocab = conn.execute(
            "SELECT * FROM vocabulary WHERE consecutive_correct < ?", (MASTERY_THRESHOLD,)
        ).fetchall()
        gram = conn.execute(
            "SELECT * FROM grammar WHERE consecutive_correct < ?", (MASTERY_THRESHOLD,)
        ).fetchall()

    recency = _recency_scores(list(vocab) + list(gram))

    def render(row: sqlite3.Row, kind: str) -> dict[str, Any]:
        """DB 행을 프론트가 쓰는 dict로 변환한다(내부 정렬용 _score 포함)."""
        base: dict[str, Any] = {
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
def api_review(review: ReviewIn) -> dict[str, Any]:
    """한 문항의 채점 결과를 DB에 반영한다.

    정답이면 consecutive_correct를 +1, 오답이면 wrong_count를 +1 하고
    consecutive_correct를 0으로 리셋한다.

    Raises:
        HTTPException(404): 해당 id의 항목이 없는 경우.
    """
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
def api_stats() -> dict[str, Any]:
    """대시보드용 통계를 반환한다.

    테이블별 total/mastered/due 와 전체(overall) 합계 및 마스터율(%)을 포함한다.
    """
    with get_db() as conn:
        stats: dict[str, Any] = {}
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


# ---- 정적 프론트엔드 (Static frontend, /api/* 가 우선하도록 마지막에 마운트) ---- #
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
