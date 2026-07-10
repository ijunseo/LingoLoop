# 🔄 LingoLoop

LLM과의 대화에서 얻은 언어 학습 데이터를 구조화하고, 약점 위주로 복습한 뒤,
그 성취도를 다시 LLM에게 주입(Context Injection)해 **나에게 딱 맞는 AI 튜터**를
만드는 로컬 개인용 앱입니다.

- **API 비용 0원 (Zero API Cost)** — 라이브 API가 아니라 복사·붙여넣기 기반의
  스마트 파서를 씁니다. 같은 내용에 두 번 돈 낼 일이 없습니다.
- **닫힌 순환 (Closed Loop)** — 퀴즈 결과가 `learning_profile.md`가 되고, 이걸
  다음 대화에 넣어주면 AI가 내가 자주 틀리는 단어·패턴을 알아서 다시 활용합니다.

> 🇨🇳 **이 인스턴스는 중국어(만다린) 학습용으로 설정되어 있습니다.**
> 단어 = 한자(汉字), 발음 = 병음/IPA, 뜻 = 모국어(예: 한국어), 문법 = 중국어 예문.
> 발음 재생(TTS)은 `zh-CN`으로 동작합니다 — 소리가 나려면 OS에 중국어 음성이
> 설치돼 있어야 합니다 (Windows: 설정 → 시간 및 언어 → 언어에서 중국어 음성 추가).
> 다른 언어로 바꾸려면 [`src/frontend/app.js`](src/frontend/app.js)의 `TTS_LANG`
> 한 줄만 수정하세요.

---

## 🚀 빠른 시작

```bash
# 1. (선택) 더미 데이터를 넣어 바로 화면을 확인
uv run python src/scripts/seed_dummy.py

# 2. 앱 실행 (백엔드 + 프론트엔드가 한 서버에서 함께 제공됨)
uv run uvicorn src.backend.server:app --reload
```

브라우저에서 **http://127.0.0.1:8000** 을 엽니다. 대시보드와 퀴즈가 같은 서버에서
서빙되고, SQLite DB(`data/lingoloop.db`)는 첫 실행 시 자동 생성됩니다.

> 첫 `uv run` 실행 때 FastAPI · uvicorn 등이 로컬 가상환경에 자동 설치됩니다.

---

## 🔄 LingoLoop 파이프라인 (공부하는 법)

LingoLoop은 단순한 단어장이 아니라, AI와의 대화를 내 수준에 맞게 진화시키는
순환 시스템입니다.

### Step 1 — 프로필과 함께 대화 시작
먼저 현재 성취도 리포트를 생성합니다.

```bash
uv run python src/scripts/generate_profile.py
```

생성된 `learning_profile.md` 내용을 복사해 Gemini / ChatGPT / Claude에 아래와 함께
붙여넣습니다.

> "이건 내 현재 중국어 학습 성취도와 취약점 데이터야. 이걸 바탕으로 오늘 내가 자주 틀리는
> 단어나 문법을 자연스럽게 활용해서 대화를 리드해줘."

*(Claude Code를 쓴다면 "내 LingoLoop 프로필 생성해줘" 라고만 해도
`.claude/skills/`의 `generate-profile` 스킬이 대신 실행해 줍니다.)*

### Step 2 — 자유 대화 후 추출
대화가 끝나면, AI에게 아래 프롬프트를 줘서 오늘 배운 내용을 JSON으로 뽑습니다.

```
[System Instruction: LingoLoop Universal Data Extractor]
Extract all key vocabulary and grammar elements from our conversation
today and format them into a single JSON list. Return ONLY the pure JSON block
without any explanations, greetings, or markdown formatting.

# Schema (one object per item):
- type: strictly "vocabulary" or "grammar".
- id: random UUID v4.
- For "vocabulary": word, pronunciation (IPA/pinyin), meaning (the correct answer).
- For "grammar": sentence (with a ___ blank for the target word/phrase).
- options: 4 multiple-choice strings; exactly one is correct.
- correct_option: must exactly match one of options
  (for vocabulary = the meaning; for grammar = the word that fills ___).
- wrong_count: 0
- consecutive_correct: 0
- created_at: ISO 8601 timestamp.
```

### Step 3 — LingoLoop에 주입
출력된 JSON을 대시보드의 **데이터 주입** 텍스트박스에 붙여넣고 **저장하기**를
누릅니다. 마크다운 백틱(```` ```json ````)은 백엔드가 자동으로 제거합니다. ✨

### Step 4 — 연습 & 마스터
**복습 시작**을 눌러 맞춤형 4지선다 퀴즈로 약점을 극복합니다. 문제 출제 시
발음이 자동 재생됩니다(Web Speech API).

그리고 다시 **Step 1**로 — 이제 프로필이 더 정교해져 있습니다. 🔁

---

## 🧠 동작 원리

| 규칙 | 동작 |
|---|---|
| **하드 필터** | `consecutive_correct < 3`(아직 미마스터)인 항목만 퀴즈에 나옵니다. |
| **가중 정렬** | 우선순위 = `wrong_count * 10 + 최신성(0~100)`; 상위 15개를 출제. |
| **1세션 1카운트** | 한 세션에서 같은 문제를 여러 번 틀려도 `wrong_count`는 최초 1회만 +1 (프론트 `Set` 방어). |
| **마스터** | 첫 시도 정답을 3연속 달성하면 해당 항목은 퀴즈에서 제외됩니다. |

---

## 🧪 테스트

```bash
uv run pytest            # 백엔드 API (중국어 데이터로 import·quiz·review 검증)
node --test tests/       # TTS 텍스트 정규화(cleanSentenceForTTS) 검증
```

---

## 📁 폴더 구조

```
LingoLoop/
├── data/lingoloop.db              # SQLite (자동 생성, gitignore)
├── src/
│   ├── backend/server.py          # FastAPI: 파서 + REST API + 정적 서빙
│   ├── frontend/                  # index.html · app.js · tts-util.js · style.css
│   └── scripts/
│       ├── generate_profile.py    # DB → learning_profile.md
│       └── seed_dummy.py          # 데모 데이터
├── tests/                         # pytest(test_server.py) · node:test(tts.test.js)
├── .claude/skills/generate-profile/SKILL.md   # Claude Code 스킬
├── learning_profile.md            # 생성되는 리포트 (gitignore)
├── pyproject.toml
└── README.md
```

## 🔌 API 레퍼런스

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/api/import` | 마크다운 백틱 제거 → `json.loads` → 테이블에 upsert. |
| `GET` | `/api/quiz` | 필터 + 가중 정렬된 15문항 세트. |
| `PUT` | `/api/review` | 채점 결과 저장 (`{id, type, correct}`). |
| `GET` | `/api/stats` | 대시보드 통계 + 마스터율. |
