"""LingoLoop 백엔드 API 테스트 (중국어 데이터 기반).

각 테스트는 임시 SQLite DB를 쓰는 격리된 TestClient로 실행된다.

    uv run pytest
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
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
            pronunciation: str = "", target_meaning: str = "",
            wrong: int = 0, streak: int = 0,
            created_at: str = "2026-07-10T00:00:00Z") -> dict[str, Any]:
    return {
        "type": "grammar",
        "id": id,
        "sentence": sentence,
        "pronunciation": pronunciation,
        "target_meaning": target_meaning,
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
    """중국어 단어/문법이 정상 저장되고 인코딩이 보존된다.

    막 임포트된 항목은 아직 리뷰된 적이 없으므로 상태가 "new"다 — mode=new로 조회한다.
    """
    items = [
        vocab("v-wo", "我", "나"),
        grammar("g-shi", "你 ___ 学生。(너는 학생이다.)", "是", ["是", "有", "在", "的"]),
    ]
    counts = import_payload(client, json.dumps(items, ensure_ascii=False))
    assert counts == {"vocabulary": 1, "grammar": 1, "skipped": 0}

    stats = client.get("/api/stats").json()
    assert stats["overall"]["total"] == 2
    assert stats["overall"]["new"] == 2

    quiz = client.get("/api/quiz?mode=new").json()["items"]
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


def test_mastered_items_only_appear_in_mastered_mode(client: TestClient) -> None:
    """consecutive_correct >= 3 인 항목은 new/due에는 안 나오고 mastered 모드에만 나온다.

    (마스터 판정은 last_reviewed_at 유무와 무관하게 streak만으로 결정된다 —
    프로필 복원 등으로 streak만 채워진 데이터도 정확히 마스터로 분류돼야 한다.)
    """
    items = [
        vocab("v-new", "水", "물", streak=0),
        vocab("v-mastered", "钱", "돈", streak=3),
    ]
    import_payload(client, json.dumps(items, ensure_ascii=False))

    new_ids = {it["id"] for it in client.get("/api/quiz?mode=new").json()["items"]}
    due_ids = {it["id"] for it in client.get("/api/quiz?mode=due").json()["items"]}
    mastered_ids = {it["id"] for it in client.get("/api/quiz?mode=mastered").json()["items"]}

    assert "v-new" in new_ids
    assert "v-mastered" not in new_ids
    assert "v-mastered" not in due_ids
    assert "v-mastered" in mastered_ids


def test_quiz_mode_rejects_unknown_value(client: TestClient) -> None:
    """mode가 new/fresh/due/mastered 중 하나가 아니면 422 (FastAPI Literal 검증)."""
    r = client.get("/api/quiz?mode=bogus")
    assert r.status_code == 422


def test_quiz_fresh_mode_returns_resting_items(client: TestClient) -> None:
    """정답을 맞혀 학습완(fresh)이 된 항목은 mode=fresh로만 나오고 due/new엔 안 나온다.

    (학습완 '재확인'은 프론트엔드가 결과를 기록하지 않으므로, 서버 쪽에서는
    fresh 항목을 조회만 할 수 있게 열어두면 된다.)
    """
    import_payload(client, json.dumps([vocab("v-f", "水", "물")], ensure_ascii=False))
    client.put("/api/review", json={"id": "v-f", "type": "vocabulary", "correct": True})

    fresh_ids = {it["id"] for it in client.get("/api/quiz?mode=fresh").json()["items"]}
    due_ids = {it["id"] for it in client.get("/api/quiz?mode=due").json()["items"]}
    new_ids = {it["id"] for it in client.get("/api/quiz?mode=new").json()["items"]}
    assert "v-f" in fresh_ids
    assert "v-f" not in due_ids
    assert "v-f" not in new_ids


def test_quiz_sorted_by_weight(client: TestClient) -> None:
    """wrong_count가 큰 항목이 앞에 온다 (wrong_count*10 가중). 둘 다 미학습 상태."""
    items = [
        vocab("v-low", "对", "맞다", wrong=0),
        vocab("v-high", "给", "주다", wrong=20),
    ]
    import_payload(client, json.dumps(items, ensure_ascii=False))
    order = [it["id"] for it in client.get("/api/quiz?mode=new").json()["items"]]
    assert order.index("v-high") < order.index("v-low")


def test_quiz_meta_reports_dates_and_counts(client: TestClient) -> None:
    """/api/quiz-meta는 모드별 유입 날짜(YYYY-MM-DD)와 날짜별 개수를 준다."""
    items = [
        vocab("v1", "我", "나", created_at="2026-07-01T00:00:00Z"),
        vocab("v2", "你", "너", created_at="2026-07-01T09:00:00Z"),
        vocab("v3", "他", "그", created_at="2026-07-03T00:00:00Z"),
    ]
    import_payload(client, json.dumps(items, ensure_ascii=False))
    meta = client.get("/api/quiz-meta?mode=new").json()
    assert meta["dates"] == ["2026-07-01", "2026-07-03"]
    assert meta["counts"] == {"2026-07-01": 2, "2026-07-03": 1}
    assert meta["total"] == 3


def test_quiz_date_range_filters(client: TestClient) -> None:
    """start/end로 유입 날짜 구간을 필터링한다(양끝 포함)."""
    items = [
        vocab("v1", "我", "나", created_at="2026-07-01T00:00:00Z"),
        vocab("v3", "他", "그", created_at="2026-07-03T00:00:00Z"),
    ]
    import_payload(client, json.dumps(items, ensure_ascii=False))
    later = {it["id"] for it in client.get("/api/quiz?mode=new&start=2026-07-02").json()["items"]}
    assert later == {"v3"}
    earlier = {it["id"] for it in client.get("/api/quiz?mode=new&end=2026-07-02").json()["items"]}
    assert earlier == {"v1"}


def test_quiz_limit_caps_count(client: TestClient) -> None:
    """limit으로 무작위 샘플링 개수를 지정한다(0<limit 검증은 FastAPI Query)."""
    items = [vocab(f"v{i}", "我", "나") for i in range(20)]
    import_payload(client, json.dumps(items, ensure_ascii=False))
    assert client.get("/api/quiz?mode=new&limit=5").json()["count"] == 5
    assert client.get("/api/quiz?mode=new&limit=100").json()["count"] == 20  # 있는 만큼만
    assert client.get("/api/quiz?mode=new&limit=0").status_code == 422  # ge=1


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


def test_stats_fresh_after_first_correct_review(client: TestClient) -> None:
    """방금 정답을 맞히면 fresh(학습완: 유예기간 중) 상태가 되고, 아직 마스터는 아니다.

    마스터는 0이어도 연습이 실제로 쌓이고 있다는 걸 대시보드가 보여줘야 한다.
    """
    import_payload(client, json.dumps([vocab("v-p", "水", "물")], ensure_ascii=False))
    stats = client.get("/api/stats").json()
    assert stats["overall"]["new"] == 1
    assert stats["overall"]["fresh"] == 0

    client.put("/api/review", json={"id": "v-p", "type": "vocabulary", "correct": True})
    stats = client.get("/api/stats").json()
    assert stats["overall"]["fresh"] == 1
    assert stats["overall"]["new"] == 0
    assert stats["overall"]["mastered"] == 0


def test_compute_status_state_machine() -> None:
    """4단계 상태 분기(new/mastered/due/fresh)를 직접 검증한다.

    - new: 리뷰된 적 없음.
    - mastered: streak >= MASTERY_THRESHOLD(last_reviewed_at 유무와 무관).
    - due: 직전 오답(streak=0)이거나, 정답이었지만 GRACE_DAYS일 유예가 끝남.
    - fresh: 정답을 맞혀 GRACE_DAYS일 유예기간 이내.
    """
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).isoformat()
    long_ago = (now - timedelta(days=server.GRACE_DAYS + 1)).isoformat()

    assert server.compute_status(0, None) == "new"
    assert server.compute_status(server.MASTERY_THRESHOLD, None) == "mastered"
    assert server.compute_status(0, yesterday) == "due"
    assert server.compute_status(1, yesterday) == "fresh"
    assert server.compute_status(2, long_ago) == "due"


def test_import_empty_is_400(client: TestClient) -> None:
    """빈 입력은 400."""
    r = client.post("/api/import", content="   ", headers={"Content-Type": "text/plain"})
    assert r.status_code == 400


def test_grammar_pronunciation_round_trips(client: TestClient) -> None:
    """문법 항목의 pronunciation·target_meaning이 저장/조회에서 보존된다.

    (的/得처럼 발음이 같은 문법조사는 pronunciation을 비워 구식 한자 4지선다로
    폴백시키는 게 의도된 동작이므로, 값이 있는 케이스만 이 테스트로 검증한다.)
    """
    items = [
        grammar(
            "g-shi", "你 ___ 学生。(너는 학생이다.)", "是", ["是", "有", "在", "的"],
            pronunciation="shì", target_meaning="~이다 (be동사)",
        ),
    ]
    import_payload(client, json.dumps(items, ensure_ascii=False))
    item = next(it for it in client.get("/api/quiz?mode=new").json()["items"] if it["id"] == "g-shi")
    assert item["pronunciation"] == "shì"
    assert item["target_meaning"] == "~이다 (be동사)"
    assert item["correct_option"] == "是"  # 빈칸에 채울 한자는 그대로 유지
    assert item["answer"] == "是"  # 구버전 데이터도 마이그레이션된 answer를 제공


def test_llm_authored_pinyin_options_and_grammar_answer_round_trip(
    client: TestClient,
) -> None:
    """새 형식은 LLM 병음 선택지와 문법 한자 정답을 서로 분리해 보존한다."""
    items = [
        {
            "type": "vocabulary",
            "id": "v-wan",
            "word": "晚上",
            "pronunciation": "wǎnshang",
            "meaning": "저녁",
            "options": ["wǎnshang", "wánshang", "wǎnxià", "wènshang"],
            "correct_option": "wǎnshang",
            "created_at": "2026-07-13T00:00:00Z",
        },
        {
            "type": "grammar",
            "id": "g-shi-new",
            "sentence": "你 ___ 学生。(너는 학생이다.)",
            "pronunciation": "shì",
            "target_meaning": "~이다 (be동사)",
            "answer": "是",
            "options": ["shì", "shí", "sì", "shǐ"],
            "correct_option": "shì",
            "created_at": "2026-07-13T00:00:00Z",
        },
    ]
    assert import_payload(client, json.dumps(items, ensure_ascii=False))["skipped"] == 0

    quiz = client.get("/api/quiz?mode=new").json()["items"]
    vo = next(item for item in quiz if item["id"] == "v-wan")
    assert vo["options"] == items[0]["options"]
    assert vo["correct_option"] == vo["pronunciation"] == "wǎnshang"

    gram = next(item for item in quiz if item["id"] == "g-shi-new")
    assert gram["answer"] == "是"
    assert gram["options"] == items[1]["options"]
    assert gram["correct_option"] == gram["pronunciation"] == "shì"


def test_new_schema_rejects_broken_option_contract(client: TestClient) -> None:
    """새 병음 형식은 중복 선택지나 빈 answer를 조용히 저장하지 않는다."""
    grammar_item = {
        "type": "grammar",
        "id": "g-bad-options",
        "sentence": "你 ___ 学生。(너는 학생이다.)",
        "pronunciation": "shì",
        "target_meaning": "~이다",
        "answer": "",
        "options": ["shì", "shì", "sì", "shǐ"],
        "correct_option": "shì",
        "created_at": "2026-07-13T00:00:00Z",
    }
    vocab_item = {
        "type": "vocabulary",
        "id": "v-bad-options",
        "word": "晚上",
        "pronunciation": "wǎnshang",
        "meaning": "저녁",
        "options": ["wǎnshang", "wǎnshang", "wǎnxià", "wènshang"],
        "correct_option": "wǎnshang",
        "created_at": "2026-07-13T00:00:00Z",
    }
    counts = import_payload(
        client, json.dumps([grammar_item, vocab_item], ensure_ascii=False)
    )
    assert counts == {"vocabulary": 0, "grammar": 0, "skipped": 2}


def test_new_homophone_fallback_keeps_hanzi_options(client: TestClient) -> None:
    """진짜 동음 문법 예외는 빈 발음과 한자 선택지를 새 answer 구조로 저장한다."""
    item = {
        "type": "grammar",
        "id": "g-de",
        "sentence": "他慢慢 ___ 走。(그는 천천히 걷는다.)",
        "pronunciation": "",
        "target_meaning": "부사어 표지",
        "answer": "地",
        "options": ["的", "地", "得", "了"],
        "correct_option": "地",
        "created_at": "2026-07-13T00:00:00Z",
    }
    assert import_payload(client, json.dumps([item], ensure_ascii=False))["grammar"] == 1
    saved = client.get("/api/quiz?mode=new").json()["items"][0]
    assert saved["pronunciation"] == ""
    assert saved["answer"] == saved["correct_option"] == "地"
    assert saved["options"] == ["的", "地", "得", "了"]


def test_seed_dummy_imports_cleanly(client: TestClient) -> None:
    """seed_dummy의 더미 데이터가 현재 스키마에 맞게 임포트된다(회귀 방지).

    단어는 병음, 문법은 병음+target_meaning을 갖춘 중국어 데이터여야 하며,
    건너뛰는(skipped) 항목이 없어야 한다.
    """
    sys.path.insert(0, str(ROOT / "src" / "scripts"))
    import seed_dummy  # noqa: E402

    items = seed_dummy.build_items()
    counts = import_payload(client, json.dumps(items, ensure_ascii=False))
    assert counts["skipped"] == 0
    assert counts["vocabulary"] + counts["grammar"] == len(items)

    quiz = client.get("/api/quiz?mode=new").json()["items"]
    gram = [it for it in quiz if it["type"] == "grammar"]
    assert gram and all(it.get("pronunciation") for it in gram)  # 문법에 병음 존재
    assert all(it["answer"] for it in gram)
    assert all(it["correct_option"] == it["pronunciation"] for it in quiz)
    assert all(len(it["options"]) == 4 for it in quiz)


def test_reset_clears_all_data(client: TestClient) -> None:
    """/api/reset은 vocabulary·grammar를 모두 비운다."""
    items = [
        vocab("v-r1", "我", "나"),
        grammar("g-r1", "你 ___ 学生。(너는 학생이다.)", "是", ["是", "有", "在", "的"]),
    ]
    import_payload(client, json.dumps(items, ensure_ascii=False))
    assert client.get("/api/stats").json()["overall"]["total"] == 2

    r = client.post("/api/reset")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert client.get("/api/stats").json()["overall"]["total"] == 0
    assert client.get("/api/quiz").json()["items"] == []
