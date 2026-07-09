# 🔄 LingoLoop

A local, personal **Context-Injection** language-learning app.
It structures the vocab & grammar you pick up while chatting with an LLM,
drills your weak spots with a tailored multiple-choice quiz, and then feeds
your achievement profile *back* to the LLM — so your AI tutor is always
perfectly calibrated to your current level.

- **Zero API Cost** — a smart copy-paste parser, not a live API. You never pay twice.
- **Closed Loop** — quiz results become `learning_profile.md`, which you inject into
  your next chat so the AI reuses the exact words/patterns you keep missing.

---

## 🚀 Quick start

```bash
# 1. (optional) seed dummy data so you can see it working immediately
uv run python src/scripts/seed_dummy.py

# 2. run the app (backend + frontend on one server)
uv run uvicorn src.backend.server:app --reload
```

Open **http://127.0.0.1:8000** — the dashboard and quiz are served from the
same server. The SQLite database is created automatically at
`data/lingoloop.db` on first run.

> First `uv run` will resolve and install FastAPI + uvicorn into a local venv.

---

## 🔄 The LingoLoop Pipeline (How to study)

LingoLoop isn't just a flashcard box. It's a loop that evolves your AI
conversations to match your level.

### Step 1 — Start a chat with your profile
Generate your current report:

```bash
uv run python src/scripts/generate_profile.py
```

Copy the contents of the generated `learning_profile.md` and paste it into
Gemini / ChatGPT / Claude with:

> "이건 내 현재 영어 학습 성취도와 취약점 데이터야. 이걸 바탕으로 오늘 내가 자주 틀리는
> 단어나 문법을 자연스럽게 활용해서 대화를 리드해줘."

*(Using Claude Code? Just say "generate my LingoLoop profile" — the
`generate-profile` skill in `.claude/skills/` runs it for you.)*

### Step 2 — Free talk & extract
When the conversation ends, give the AI this extractor prompt to turn the
session into structured JSON:

```
[System Instruction: LingoLoop Universal Data Extractor]
Extract all key vocabulary and grammar elements from our conversation
today and format them into a single JSON list. Return ONLY the pure JSON block
without any explanations, greetings, or markdown formatting.

# Schema (one object per item):
- type: strictly "vocabulary" or "grammar".
- id: random UUID v4.
- For "vocabulary": word, pronunciation (IPA), meaning (the correct answer).
- For "grammar": sentence (with a ___ blank for the target word/phrase).
- options: 4 multiple-choice strings; exactly one is correct.
- correct_option: must exactly match one of options
  (for vocabulary = the meaning; for grammar = the word that fills ___).
- wrong_count: 0
- consecutive_correct: 0
- created_at: ISO 8601 timestamp.
```

### Step 3 — Feed to LingoLoop
Paste the JSON text into the dashboard's **데이터 주입** textarea and hit
**저장하기**. Markdown fences (```` ```json ````) are stripped automatically by
the backend — Zero API Cost. ✨

### Step 4 — Practice & master
Hit **복습 시작** and beat your weaknesses with the tailored 4-choice quiz.
Native-like pronunciation plays automatically via the Web Speech API.

Then loop back to **Step 1** — your profile is now sharper. 🔁

---

## 🧠 How the logic works

| Rule | Behavior |
|---|---|
| **Hard filter** | Quiz only pulls items with `consecutive_correct < 3` (unmastered). |
| **Weighted sort** | Priority = `wrong_count * 10 + recency(0–100)`; top 15 are served. |
| **1-session-1-count** | Miss the same item repeatedly in one session → `wrong_count` still only +1 (front-end `Set` guard). |
| **Mastery** | 3 first-try-correct answers in a row → item is retired from quizzes. |

---

## 📁 Layout

```
LingoLoop/
├── data/lingoloop.db              # SQLite (auto-created, gitignored)
├── src/
│   ├── backend/server.py          # FastAPI: parser + REST API + static serving
│   ├── frontend/                  # index.html · app.js · style.css (Tailwind CDN)
│   └── scripts/
│       ├── generate_profile.py    # DB → learning_profile.md
│       └── seed_dummy.py          # demo data
├── .claude/skills/generate-profile/SKILL.md   # Claude Code skill
├── learning_profile.md            # generated report (gitignored)
├── pyproject.toml
└── README.md
```

## 🔌 API reference

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/import` | Strip markdown fences → `json.loads` → upsert into tables. |
| `GET` | `/api/quiz` | Filtered + weighted 15-item quiz set. |
| `PUT` | `/api/review` | Persist an answer (`{id, type, correct}`). |
| `GET` | `/api/stats` | Dashboard totals + mastery rate. |
