"""LingoLoop 백엔드 — FastAPI + 표준 라이브러리 sqlite3.

API 유지비용 0원(Zero API Cost)을 지향하는 개인용 언어 학습 루프의 서버.
학습 상태는 4단계 간격 반복(SRS-lite) 모델을 따른다 — compute_status() 참고.

엔드포인트:
  * POST /api/import  — 마크다운 백틱 제거 후 json.loads, 테이블에 upsert
  * GET  /api/quiz    — mode(new/due/mastered)별 필터 + 가중 정렬로 15개 반환
  * PUT  /api/review  — 정답/오답 결과를 DB에 영속화 (last_reviewed_at 갱신)
  * GET  /api/stats   — 대시보드용 상태별(new/fresh/due/mastered) 통계
프론트엔드(src/frontend)는 "/" 에 정적(static)으로 서빙된다.
"""
from __future__ import annotations

import json
import random
import re
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Iterator, Literal

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

MASTERY_THRESHOLD: int = 3   # consecutive_correct >= 이 값이면 완전학습완
GRACE_DAYS: int = 3          # 정답을 맞힌 뒤 재시험 없이 쉬는 "학습완" 유예 기간(일)
QUIZ_SIZE: int = 15          # 퀴즈 1회에 반환할 문항 수

Status = Literal["new", "fresh", "due", "mastered"]


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
                last_reviewed_at    TEXT DEFAULT NULL, -- NULL=미학습(new)
                created_at          TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS grammar (
                id                  TEXT PRIMARY KEY,
                sentence            TEXT NOT NULL,   -- ___ 빈칸을 포함, 뒤에 (전체 뜻) 표기 관습
                pronunciation       TEXT DEFAULT '', -- 빈칸(=correct_option) 한자의 표준 병음
                target_meaning      TEXT DEFAULT '', -- 빈칸 글자 하나의 개별 뜻/문법 기능
                options             TEXT NOT NULL,   -- JSON array of 4 strings (구식 한자 4지선다 폴백용)
                correct_option      TEXT NOT NULL,   -- 빈칸에 들어가는 한자
                wrong_count         INTEGER NOT NULL DEFAULT 0,
                consecutive_correct INTEGER NOT NULL DEFAULT 0,
                last_reviewed_at    TEXT DEFAULT NULL, -- NULL=미학습(new)
                created_at          TEXT NOT NULL
            );
            """
        )
        # 기존 DB(구버전 스키마)에는 없을 수 있는 컬럼을 안전하게 추가한다.
        _ensure_column(conn, "vocabulary", "last_reviewed_at", "TEXT DEFAULT NULL")
        _ensure_column(conn, "grammar", "last_reviewed_at", "TEXT DEFAULT NULL")
        _ensure_column(conn, "grammar", "pronunciation", "TEXT DEFAULT ''")
        _ensure_column(conn, "grammar", "target_meaning", "TEXT DEFAULT ''")
        _backfill_last_reviewed_at(conn)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """table에 column이 없으면 ALTER TABLE로 추가한다(idempotent 마이그레이션)."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _backfill_last_reviewed_at(conn: sqlite3.Connection) -> None:
    """last_reviewed_at 컬럼이 생기기 전부터 리뷰 이력이 있던 행을 보정한다.

    wrong_count나 consecutive_correct가 0보다 크면 최소 한 번은 리뷰된 것이므로,
    last_reviewed_at이 비어 있으면 지금 시각으로 채워 "미학습"으로 오인되지 않게
    한다. 이미 채워진 행이나 정말 손댄 적 없는 행에는 영향이 없다(idempotent).
    """
    now = datetime.now(timezone.utc).isoformat()
    for table in ("vocabulary", "grammar"):
        conn.execute(
            f"UPDATE {table} SET last_reviewed_at = ? "
            f"WHERE last_reviewed_at IS NULL AND (wrong_count > 0 OR consecutive_correct > 0)",
            (now,),
        )


def _parse_iso(ts: str) -> datetime:
    """ISO 8601 문자열을 datetime으로 파싱한다(타임존 없으면 UTC로 간주)."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_status(consecutive_correct: int, last_reviewed_at: str | None) -> Status:
    """항목의 학습 상태(4단계 간격 반복)를 계산한다.

    - new(미학습): 한 번도 리뷰된 적 없음.
    - mastered(완전학습완): 별도 세션에서 연속 정답이 MASTERY_THRESHOLD에 도달.
    - due(학습필요): 리뷰된 적은 있지만 아직 마스터 전이고, 직전이 오답(streak=0)
      이거나 GRACE_DAYS일 유예가 끝나 다시 시험 볼 때가 됨.
    - fresh(학습완): 방금 정답을 맞혀 GRACE_DAYS일 동안 재시험 없이 쉬는 상태.

    마스터 판정을 null 체크보다 먼저 하는 이유: 프로필 복원 등으로
    consecutive_correct만 채워지고 last_reviewed_at은 비어있는 데이터가 들어와도
    "미학습"으로 잘못 표시되지 않게 하기 위해서다.
    """
    if consecutive_correct >= MASTERY_THRESHOLD:
        return "mastered"
    if not last_reviewed_at:
        return "new"
    if consecutive_correct <= 0:
        return "due"
    days_since = (datetime.now(timezone.utc) - _parse_iso(last_reviewed_at)).days
    return "fresh" if days_since < GRACE_DAYS else "due"


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
                    (id, sentence, pronunciation, target_meaning, options, correct_option,
                     wrong_count, consecutive_correct, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    sentence=excluded.sentence,
                    pronunciation=excluded.pronunciation,
                    target_meaning=excluded.target_meaning,
                    options=excluded.options,
                    correct_option=excluded.correct_option
                """,
                (
                    item_id,
                    str(sentence),
                    str(_first(item, "pronunciation", "ipa", default="")),
                    str(_first(item, "target_meaning", "target_gloss", default="")),
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

    created_at '값'의 순위로 계산하므로, 같은 시각을 가진 항목은 같은 점수를
    받는다(입력 순서로 편향되지 않음). 시각이 모두 같으면 전부 100이 된다.
    """
    times = sorted({(r["created_at"] or "") for r in rows})  # 고유 시각 오름차순
    m = len(times)
    if m <= 1:
        return {r["id"]: 100 for r in rows}
    rank = {t: i for i, t in enumerate(times)}
    return {r["id"]: round(100 * rank[r["created_at"] or ""] / (m - 1)) for r in rows}


@app.get("/api/quiz")
def api_quiz(mode: Status = "due") -> dict[str, Any]:
    """복습 문항을 반환한다.

    mode로 어떤 학습 상태의 항목을 출제할지 고른다(compute_status 참고):
      - "due"(기본): 학습필요 — 직전 오답이거나 학습완 유예기간이 끝난 항목.
      - "new": 미학습 — 한 번도 리뷰된 적 없는 항목.
      - "fresh": 학습완 — 쉬는 중인 항목을 '재확인'용으로 출제. 프론트엔드는
        이 모드의 결과를 /api/review로 기록하지 않아 잠자는 상태를 안 건드린다.
      - "mastered": 완전학습완 — 이미 마스터된 항목을 선택적으로 다시 연습.
    `wrong_count * 10 + 최신성(0~100)` 점수 내림차순으로 상위 QUIZ_SIZE개를 준다.
    정답 채점은 프론트에서 하므로 correct_option도 함께 내려준다.
    """
    with get_db() as conn:
        all_vocab = conn.execute("SELECT * FROM vocabulary").fetchall()
        all_gram = conn.execute("SELECT * FROM grammar").fetchall()

    def in_mode(row: sqlite3.Row) -> bool:
        return compute_status(row["consecutive_correct"], row["last_reviewed_at"]) == mode

    vocab = [r for r in all_vocab if in_mode(r)]
    gram = [r for r in all_gram if in_mode(r)]

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
            base.update(
                sentence=row["sentence"],
                pronunciation=row["pronunciation"],
                target_meaning=row["target_meaning"],
            )
        return base

    items = [render(r, "vocabulary") for r in vocab] + [render(r, "grammar") for r in gram]
    # 점수가 같은 항목들이 매번 같은 순서로 나오지 않도록 먼저 섞은 뒤,
    # 안정 정렬로 점수 내림차순 정렬한다(동점은 무작위 → 단어/문법이 골고루).
    random.shuffle(items)
    items.sort(key=lambda x: x["_score"], reverse=True)
    items = items[:QUIZ_SIZE]
    for it in items:
        it.pop("_score", None)
    return {"count": len(items), "items": items}


@app.put("/api/review")
def api_review(review: ReviewIn) -> dict[str, Any]:
    """한 문항의 채점 결과를 DB에 반영한다.

    정답이면 consecutive_correct를 +1, 오답이면 wrong_count를 +1 하고
    consecutive_correct를 0으로 리셋한다. 어느 쪽이든 last_reviewed_at을
    지금 시각으로 찍어 학습 상태(new/fresh/due/mastered) 계산의 기준으로 삼는다.

    Raises:
        HTTPException(404): 해당 id의 항목이 없는 경우.
    """
    table = "vocabulary" if review.type == "vocabulary" else "grammar"
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(f"SELECT id FROM {table} WHERE id = ?", (review.id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Item not found.")
        if review.correct:
            conn.execute(
                f"UPDATE {table} SET consecutive_correct = consecutive_correct + 1, "
                f"last_reviewed_at = ? WHERE id = ?",
                (now, review.id),
            )
        else:
            conn.execute(
                f"UPDATE {table} SET wrong_count = wrong_count + 1, "
                f"consecutive_correct = 0, last_reviewed_at = ? WHERE id = ?",
                (now, review.id),
            )
    return {"ok": True}


@app.get("/api/stats")
def api_stats() -> dict[str, Any]:
    """대시보드용 통계를 반환한다.

    테이블별·전체(overall)로 4가지 학습 상태(new/fresh/due/mastered)의 개수와
    total, mastery_rate(%)를 포함한다. compute_status()로 상태를 계산한다.
    """
    with get_db() as conn:
        stats: dict[str, Any] = {}
        overall = {"new": 0, "fresh": 0, "due": 0, "mastered": 0}
        total_items = 0
        for table in ("vocabulary", "grammar"):
            rows = conn.execute(
                f"SELECT consecutive_correct, last_reviewed_at FROM {table}"
            ).fetchall()
            counts = {"new": 0, "fresh": 0, "due": 0, "mastered": 0}
            for r in rows:
                counts[compute_status(r["consecutive_correct"], r["last_reviewed_at"])] += 1
            stats[table] = {"total": len(rows), **counts}
            total_items += len(rows)
            for k in overall:
                overall[k] += counts[k]
        rate = round(100 * overall["mastered"] / total_items) if total_items else 0
        stats["overall"] = {"total": total_items, **overall, "mastery_rate": rate}
    return stats


@app.post("/api/reset")
def api_reset() -> dict[str, Any]:
    """vocabulary·grammar 테이블을 완전히 비운다(개발용, 되돌릴 수 없음).

    데이터 포맷을 확정하기 전 반복 테스트용 기능이다. 확인 절차는 프론트엔드의
    confirm() 대화상자가 담당하며, 서버는 요청이 오면 즉시 실행한다.
    """
    with get_db() as conn:
        conn.execute("DELETE FROM vocabulary")
        conn.execute("DELETE FROM grammar")
    return {"ok": True}


# ---- 정적 프론트엔드 (Static frontend, /api/* 가 우선하도록 마지막에 마운트) ---- #
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
