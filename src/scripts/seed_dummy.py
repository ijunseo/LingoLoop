"""Seed the LingoLoop database with dummy vocabulary & grammar.

    uv run python src/scripts/seed_dummy.py

Items carry pre-set wrong_count / consecutive_correct / created_at so the
weighted quiz sort, the mastery filter, and the profile report all have
something interesting to show.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Windows consoles may be cp932/cp949; keep unicode output from crashing.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "backend"))

import server  # noqa: E402


def days_ago(n: int) -> str:
    """n일 전 UTC 시각을 ISO 8601 문자열로 반환한다."""
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


# (word, ipa, meaning, distractors, wrong_count, streak, days_ago)
VOCAB = [
    ("serendipity", "/ˌserənˈdɪpəti/", "뜻밖의 행운, 우연한 발견",
     ["극심한 피로", "고의적인 방해", "엄격한 규율"], 5, 0, 1),
    ("ubiquitous", "/juːˈbɪkwɪtəs/", "어디에나 존재하는",
     ["희귀한", "복잡한", "일시적인"], 4, 0, 2),
    ("meticulous", "/məˈtɪkjələs/", "꼼꼼한, 세심한",
     ["부주의한", "관대한", "충동적인"], 3, 1, 3),
    ("resilient", "/rɪˈzɪliənt/", "회복력 있는, 탄력 있는",
     ["연약한", "무관심한", "완고한"], 3, 0, 1),
    ("ambiguous", "/æmˈbɪɡjuəs/", "애매모호한",
     ["명확한", "화려한", "지루한"], 2, 1, 4),
    ("candor", "/ˈkændər/", "솔직함, 정직함",
     ["교활함", "냉담함", "허영심"], 2, 0, 5),
    ("pragmatic", "/præɡˈmætɪk/", "실용적인, 실리적인",
     ["이상적인", "감상적인", "비관적인"], 1, 2, 6),
    ("nuance", "/ˈnuːɑːns/", "미묘한 차이",
     ["명백한 오류", "거대한 규모", "단순한 반복"], 1, 0, 2),
    ("eloquent", "/ˈeləkwənt/", "웅변의, 유창한",
     ["말을 더듬는", "무뚝뚝한", "시끄러운"], 0, 2, 7),
    ("tenacious", "/təˈneɪʃəs/", "끈질긴, 집요한",
     ["쉽게 포기하는", "느긋한", "산만한"], 0, 3, 9),   # mastered
    ("frugal", "/ˈfruːɡl/", "검소한, 절약하는",
     ["낭비하는", "사치스러운", "관대한"], 0, 3, 10),   # mastered
    ("empathy", "/ˈempəθi/", "공감, 감정이입",
     ["무관심", "적대감", "우월감"], 1, 1, 3),
]

# (sentence with ___, answer, distractors, wrong_count, streak, days_ago)
GRAMMAR = [
    ("If I ___ known earlier, I would have helped.", "had",
     ["have", "has", "having"], 6, 0, 1),
    ("She suggested that he ___ the report by Friday.", "submit",
     ["submits", "submitted", "will submit"], 4, 0, 2),
    ("I look forward to ___ from you soon.", "hearing",
     ["hear", "heard", "be heard"], 3, 0, 1),
    ("The project ___ by the team last month.", "was completed",
     ["completed", "has completed", "is completing"], 2, 1, 4),
    ("He is used to ___ up early every morning.", "waking",
     ["wake", "woke", "be woken"], 2, 0, 5),
    ("Not only ___ late, but he also forgot the files.", "was he",
     ["he was", "he is", "did he"], 1, 2, 6),
    ("I wish I ___ more time to finish it.", "had",
     ["have", "will have", "am having"], 1, 0, 3),
    ("By the time we arrived, the movie ___ already started.", "had",
     ["has", "have", "was"], 0, 3, 9),   # mastered
]


def build_items() -> list[dict[str, Any]]:
    """VOCAB/GRAMMAR 정의를 import API가 받는 항목 dict 리스트로 변환한다."""
    items: list[dict[str, Any]] = []
    for word, ipa, meaning, wrongs, wc, streak, ago in VOCAB:
        items.append({
            "type": "vocabulary",
            "id": str(uuid.uuid4()),
            "word": word,
            "pronunciation": ipa,
            "meaning": meaning,
            "options": [meaning, *wrongs],
            "correct_option": meaning,
            "wrong_count": wc,
            "consecutive_correct": streak,
            "created_at": days_ago(ago),
        })
    for sentence, answer, wrongs, wc, streak, ago in GRAMMAR:
        items.append({
            "type": "grammar",
            "id": str(uuid.uuid4()),
            "sentence": sentence,
            "options": [answer, *wrongs],
            "correct_option": answer,
            "wrong_count": wc,
            "consecutive_correct": streak,
            "created_at": days_ago(ago),
        })
    return items


def main() -> None:
    """더미 데이터를 DB에 주입하고 처리 건수를 출력한다."""
    server.init_db()
    items = build_items()
    with server.get_db() as conn:
        counts = server.upsert_items(conn, items)
    print(f"Seeded → vocabulary: {counts['vocabulary']}, "
          f"grammar: {counts['grammar']}, skipped: {counts['skipped']}")
    print(f"Database: {server.DB_PATH}")


if __name__ == "__main__":
    main()
