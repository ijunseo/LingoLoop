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


# 단어: (한자, 표준 병음, 뜻, 오답 뜻들, wrong_count, streak, days_ago)
VOCAB = [
    ("你好", "nǐhǎo", "안녕하세요",
     ["고맙다", "미안하다", "잘 자"], 5, 0, 1),
    ("谢谢", "xièxie", "고맙다",
     ["미안하다", "괜찮다", "안녕"], 4, 0, 2),
    ("水", "shuǐ", "물",
     ["불", "흙", "바람"], 3, 1, 3),
    ("钱", "qián", "돈",
     ["책", "집", "차"], 3, 0, 1),
    ("猫", "māo", "고양이",
     ["개", "새", "물고기"], 2, 1, 4),
    ("吃", "chī", "먹다",
     ["마시다", "자다", "보다"], 2, 0, 5),
    ("大", "dà", "크다",
     ["작다", "높다", "길다"], 1, 2, 6),
    ("学生", "xuésheng", "학생",
     ["선생님", "의사", "친구"], 1, 0, 2),
    ("喜欢", "xǐhuan", "좋아하다",
     ["싫어하다", "원하다", "필요하다"], 0, 2, 7),
    ("漂亮", "piàoliang", "예쁘다",
     ["못생기다", "빠르다", "느리다"], 0, 3, 9),   # mastered
]

# 문법: (문장(___·뜻), 빈칸 한자, 빈칸 병음, 빈칸 개별 뜻, 한자 오답들,
#        wrong_count, streak, days_ago)
GRAMMAR = [
    ("你 ___ 学生吗？(너 학생이야?)", "是", "shì", "~이다 (be동사)",
     ["有", "在", "的"], 6, 0, 1),
    ("我 ___ 钱。(나 돈 없어.)", "没", "méi", "안 ~있다 (부정)",
     ["不", "别", "无"], 4, 0, 2),
    ("这 ___ 猫很漂亮。(이 고양이 예쁘다.)", "只", "zhī", "마리 (동물 양사)",
     ["个", "条", "本"], 3, 0, 1),
    ("我 ___ 喜欢你。(나 너 정말 좋아해.)", "很", "hěn", "매우 (정도부사)",
     ["太", "真", "最"], 2, 1, 4),
    ("他 ___ 吃饭。(그는 밥 먹는 중이다.)", "在", "zài", "~하는 중 (진행)",
     ["了", "过", "着"], 1, 2, 6),
    ("你 ___？(너는?)", "呢", "ne", "~는? (되묻는 어기조사)",
     ["吗", "吧", "了"], 0, 3, 9),   # mastered
]


def build_items() -> list[dict[str, Any]]:
    """VOCAB/GRAMMAR 정의를 import API가 받는 항목 dict 리스트로 변환한다."""
    items: list[dict[str, Any]] = []
    for word, pinyin, meaning, wrongs, wc, streak, ago in VOCAB:
        items.append({
            "type": "vocabulary",
            "id": str(uuid.uuid4()),
            "word": word,
            "pronunciation": pinyin,
            "meaning": meaning,
            "options": [meaning, *wrongs],
            "correct_option": meaning,
            "wrong_count": wc,
            "consecutive_correct": streak,
            "created_at": days_ago(ago),
        })
    for sentence, answer, pinyin, target_meaning, wrongs, wc, streak, ago in GRAMMAR:
        items.append({
            "type": "grammar",
            "id": str(uuid.uuid4()),
            "sentence": sentence,
            "pronunciation": pinyin,
            "target_meaning": target_meaning,
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
