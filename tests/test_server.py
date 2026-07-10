"""LingoLoop 백엔드 API 테스트 (중국어 데이터 기반).

각 테스트는 임시 SQLite DB를 쓰는 격리된 TestClient로 실행된다.

    uv run pytest
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

import server  # noqa: E402


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """임시 DB 경로로 갈아끼운 뒤 lifespan(init_db)까지 태우는 TestClient."""
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server, "DB_PATH", tmp_path / "test.db")
    with TestClient(server.app) as c:  # __enter__ 시 lifespan 실행 → init_db()
        yield c


# --- 샘플 중국어 데이터 --------------------------------------------------- #
def vocab(id: str, word: str, meaning: str, *, wrong: int = 0, streak: int = 0,
          created_at: str = "2026-07-10T00:00:00Z") -> dict[str, Any]:
    return {
        "type": "vocabulary",
        "id": id,
        "word": word,
        "pronunciation": "/test/",
        "meaning": meaning,
        "options": [meaning, "오답1", "오답2", "오답3"],
        "correct_option": meaning,
        "wrong_count": wrong,
        "consecutive_correct": streak,
        "created_at": created_at,
    }


def grammar(id: str, sentence: str, answer: str, options: list[str], *,
            wrong: int = 0, streak: int = 0,
            created_at: str = "2026-07-10T00:00:00Z") -> dict[str, Any]:
    return {
        "type": "grammar",
        "id": id,
        "sentence": sentence,
        "options": options,
        "correct_option": answer,
        "wrong_count": wrong,
        "consecutive_correct": streak,
        "created_at": created_at,
    }


def import_payload(client: TestClient, payload: str) -> dict[str, Any]:
    r = client.post("/api/import", content=payload,
                    headers={"Content-Type": "text/plain"})
    assert r.status_code == 200, r.text
    return r.json()["imported"]


# --- 테스트 --------------------------------------------------------------- #
def test_import_chinese_vocab_and_grammar(client: TestClient) -> None:
    """중국어 단어/문법이 정상 저장되고 인코딩이 보존된다."""
    items = [
        vocab("v-wo", "我", "나"),
        grammar("g-shi", "你 ___ 学生。(너는 학생이다.)", "是", ["是", "有", "在", "的"]),
    ]
    counts = import_payload(client, json.dumps(items, ensure_ascii=False))
    assert counts == {"vocabulary": 1, "grammar": 1, "skipped": 0}

    stats = client.get("/api/stats").json()
    assert stats["overall"]["total"] == 2

    quiz = client.get("/api/quiz").json()["items"]
    words = {it.get("word") for it in quiz if it["type"] == "vocabulary"}
    assert "我" in words  # 한자가 깨지지 않고 왕복
    vo = next(it for it in quiz if it["id"] == "v-wo")
    assert vo["correct_option"] == "나"


def test_import_strips_markdown_fences(client: TestClient) -> None:
    """```json 코드펜스와 앞뒤 잡설이 있어도 파싱된다."""
    body = "여기 있어요:\n```json\n" + json.dumps([vocab("v-ni", "你", "너")],
                                                 ensure_ascii=False) + "\n```\n감사!"
    counts = import_payload(client, body)
    assert counts["vocabulary"] == 1


def test_quiz_hard_filter_excludes_mastered(client: TestClient) -> None:
    """consecutive_correct >= 3 인 항목은 퀴즈에서 제외된다."""
    items = [
        vocab("v-due", "水", "물", streak=0),
        vocab("v-mastered", "钱", "돈", streak=3),
    ]
    import_payload(client, json.dumps(items, ensure_ascii=False))
    ids = {it["id"] for it in client.get("/api/quiz").json()["items"]}
    assert "v-due" in ids
    assert "v-mastered" not in ids


def test_quiz_sorted_by_weight(client: TestClient) -> None:
    """wrong_count가 큰 항목이 앞에 온다 (wrong_count*10 가중)."""
    items = [
        vocab("v-low", "对", "맞다", wrong=0),
        vocab("v-high", "给", "주다", wrong=20),
    ]
    import_payload(client, json.dumps(items, ensure_ascii=False))
    order = [it["id"] for it in client.get("/api/quiz").json()["items"]]
    assert order.index("v-high") < order.index("v-low")


def test_review_lifecycle(client: TestClient) -> None:
    """정답 3연속 → 마스터, 이후 오답 → 리셋 + wrong_count 증가."""
    import_payload(client, json.dumps([vocab("v-x", "来", "오다")], ensure_ascii=False))

    for _ in range(3):
        r = client.put("/api/review", json={"id": "v-x", "type": "vocabulary", "correct": True})
        assert r.status_code == 200
    assert client.get("/api/stats").json()["overall"]["mastered"] == 1

    client.put("/api/review", json={"id": "v-x", "type": "vocabulary", "correct": False})
    assert client.get("/api/stats").json()["overall"]["mastered"] == 0
    item = next(it for it in client.get("/api/quiz").json()["items"] if it["id"] == "v-x")
    assert item["wrong_count"] == 1
    assert item["consecutive_correct"] == 0


def test_review_unknown_id_returns_404(client: TestClient) -> None:
    """존재하지 않는 id 리뷰는 404."""
    r = client.put("/api/review", json={"id": "nope", "type": "vocabulary", "correct": True})
    assert r.status_code == 404


def test_import_empty_is_400(client: TestClient) -> None:
    """빈 입력은 400."""
    r = client.post("/api/import", content="   ", headers={"Content-Type": "text/plain"})
    assert r.status_code == 400
