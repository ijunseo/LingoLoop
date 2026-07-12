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


# 단어: (한자, 표준 병음, 뜻, 헷갈리는 병음 오답 3개, wrong_count, streak, days_ago)
VOCAB = [
    ("你好", "nǐhǎo", "안녕하세요",
     ["níhǎo", "nǐhào", "lǐhǎo"], 5, 0, 1),
    ("谢谢", "xièxie", "고맙다",
     ["xiéxie", "xièxiè", "jièxie"], 4, 0, 2),
    ("水", "shuǐ", "물",
     ["shuí", "shuì", "suǐ"], 3, 1, 3),
    ("钱", "qián", "돈",
     ["qiǎn", "jián", "qiàng"], 3, 0, 1),
    ("猫", "māo", "고양이",
     ["máo", "mǎo", "bāo"], 2, 1, 4),
    ("吃", "chī", "먹다",
     ["chí", "chǐ", "qī"], 2, 0, 5),
    ("大", "dà", "크다",
     ["dá", "dǎ", "tà"], 1, 2, 6),
    ("学生", "xuésheng", "학생",
     ["xuěsheng", "xuéshēng", "xuéshang"], 1, 0, 2),
    ("喜欢", "xǐhuan", "좋아하다",
     ["xíhuan", "xǐhuàn", "qǐhuan"], 0, 2, 7),
    ("漂亮", "piàoliang", "예쁘다",
     ["piáoliang", "piàoliàng", "biàoliang"], 0, 3, 9),   # mastered
]

# 문법: (문장(___·뜻), 빈칸 한자, 빈칸 병음, 빈칸 개별 뜻, 병음 오답 3개,
#        wrong_count, streak, days_ago)
GRAMMAR = [
    ("你 ___ 学生吗？(너 학생이야?)", "是", "shì", "~이다 (be동사)",
     ["shí", "sì", "shǐ"], 6, 0, 1),
    ("我 ___ 钱。(나 돈 없어.)", "没", "méi", "안 ~있다 (부정)",
     ["měi", "mèi", "móu"], 4, 0, 2),
    ("这 ___ 猫很漂亮。(이 고양이 예쁘다.)", "只", "zhī", "마리 (동물 양사)",
     ["zhí", "zī", "jī"], 3, 0, 1),
    ("我 ___ 喜欢你。(나 너 정말 좋아해.)", "很", "hěn", "매우 (정도부사)",
     ["hén", "hèn", "hěng"], 2, 1, 4),
    ("他 ___ 吃饭。(그는 밥 먹는 중이다.)", "在", "zài", "~하는 중 (진행)",
     ["zǎi", "zāi", "cài"], 1, 2, 6),
    ("你 ___？(너는?)", "呢", "ne", "~는? (되묻는 어기조사)",
     ["nè", "nǎ", "le"], 0, 3, 9),   # mastered
]


def build_items() -> list[dict[str, Any]]:
    """VOCAB/GRAMMAR 정의를 import API가 받는 항목 dict 리스트로 변환한다."""
    items: list[dict[str, Any]] = []
    for word, pinyin, meaning, distractors, wc, streak, ago in VOCAB:
        items.append({
            "type": "vocabulary",
            "id": str(uuid.uuid4()),
            "word": word,
            "pronunciation": pinyin,
            "meaning": meaning,
            "options": [pinyin, *distractors],
            "correct_option": pinyin,
            "wrong_count": wc,
            "consecutive_correct": streak,
            "created_at": days_ago(ago),
        })
    for sentence, answer, pinyin, target_meaning, distractors, wc, streak, ago in GRAMMAR:
        items.append({
            "type": "grammar",
            "id": str(uuid.uuid4()),
            "sentence": sentence,
            "pronunciation": pinyin,
            "target_meaning": target_meaning,
            "answer": answer,
            "options": [pinyin, *distractors],
            "correct_option": pinyin,
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
