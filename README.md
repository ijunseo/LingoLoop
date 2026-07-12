# 🔄 LingoLoop

LLM과의 대화에서 얻은 언어 학습 데이터를 구조화하고, 약점 위주로 복습한 뒤,
그 성취도를 다시 LLM에게 주입(Context Injection)해 **나에게 딱 맞는 AI 튜터**를
만드는 로컬 개인용 앱입니다.

- **API 비용 0원 (Zero API Cost)** — 라이브 API가 아니라 복사·붙여넣기 기반의
  스마트 파서를 씁니다. 같은 내용에 두 번 돈 낼 일이 없습니다.
- **닫힌 순환 (Closed Loop)** — 퀴즈 결과가 `learning_profile.md`가 되고, 이걸
  다음 대화에 넣어주면 AI가 내가 자주 틀리는 단어·패턴을 알아서 다시 활용합니다.

> 🇨🇳 **이 인스턴스는 중국어(만다린) 학습용으로 설정되어 있습니다.**
> 단어 = 한자(汉字), 발음 = **표준 병음(성조 기호 포함, 사전식 표기)**, 뜻 = 모국어(예: 한국어),
> 문법 = 중국어 예문.
> 발음 재생(TTS)은 `zh-CN`으로 동작합니다 — 소리가 나려면 OS에 중국어 음성이
> 설치돼 있어야 합니다 (Windows: 설정 → 시간 및 언어 → 언어에서 중국어 음성 추가).
> 다른 언어로 바꾸려면 [`src/frontend/app.js`](src/frontend/app.js)의 `TTS_LANG`
> 한 줄만 수정하세요.
>
> **단어·문법 모두 100% 발음 매칭 방식입니다.** 한자(단어는 단어 자체, 문법은
> 문장 속 강조된 글자)를 그대로 보여주고, 뜻도 같이 공개한 뒤, 발음(병음) 4지선다로
> 답을 고르게 합니다 — 한자 자체나 뜻을 유추하는 건 이미 되는 학습자(다년간 한자
> 문화권 학습·거주 경험 등)에게는, 진짜 병목이 "이 글자를 실제로 어떻게 읽는가"이기
> 때문입니다. 그래서 뜻 맞히기가 아니라 **오직 읽기(발음)** 만 시험합니다.
> (예외: 的/地/得처럼 발음이 완전히 같은 문법조사는 병음으로 구별이 불가능해서
> 자동으로 기존 한자 4지선다 방식으로 대체됩니다.)

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

리포트에는 통계·취약점 외에도 **세션 규칙(Ground Rules)** 이 자동으로 포함됩니다:
왕초보 눈높이로 진행할 것, **이미지를 절대 생성하지 말 것**(텍스트 형태 요청이
이미지 생성 도구를 건드리는 걸 방지), 질문한 단어·표현엔 비슷한 표현도 같이
제시할 것, 새로 배운 내용마다 "💡 Key Point" 한 줄을 짚어줄 것.

*(Claude Code를 쓴다면 "내 LingoLoop 프로필 생성해줘" 라고만 해도
`.claude/skills/`의 `generate-profile` 스킬이 대신 실행해 줍니다.)*

### Step 2 — 자유 대화 후 추출
대화가 끝나면, AI에게 아래 프롬프트를 줘서 오늘 배운 내용을 JSON으로 뽑습니다.
핵심은 세 가지입니다:
1. `pronunciation`은 **사전에 나오는 표준 병음(성조 기호 포함)** 이어야 합니다 —
   IPA나 슬래시(`/.../`)로 오면 퀴즈 화면에서 어색하게 표시됩니다.
2. **문법도 문장 통째로 추출**하고, 문장 전체 뜻과 빈칸 글자 하나의 개별 뜻을
   둘 다 공개합니다. 뜻은 이미 다 알려주니 학습자는 오직 **그 글자를 어떻게
   읽는지(발음)** 에만 집중하면 됩니다.
3. `options`는 다른 DB 항목에서 무작위로 뽑지 않고, AI가 정답과 성조·초성·운모가
   비슷한 **문항 전용 병음 오답 3개**를 함께 만듭니다.

```
[System Instruction: LingoLoop Universal Data Extractor]
Your response MUST be one valid JSON array and nothing else. Do not output
markdown fences, prose, greetings, comments, or trailing text. If no eligible
lesson item exists, return [].

# 1. Source boundary — non-negotiable
Extract ONLY Mandarin vocabulary and grammar that the learner actually learned,
discussed, corrected, or practised in the lesson conversation BEFORE this
instruction. Mere appearance is not evidence of learning.

NEVER extract content from this instruction, schema placeholders, examples,
README text, code blocks, app instructions, a prior Learning Profile, incidental
example sentences, deleted items, or an earlier form later judged incorrect.
When an item was corrected, keep only the final corrected form. Deduplicate
repeated items. Do not invent lesson content to reach a target count.

# 2. Learning objective
The learner can infer Hanzi shape and meaning through long Kanji experience.
Reveal Hanzi and Korean meaning; test Mandarin pronunciation. Every ordinary
item therefore needs one correct pinyin and three deliberately confusable pinyin
distractors generated for THAT item. Never fill distractors by sampling unrelated
words from the conversation.

# 3. Pinyin rules — all must pass
- Use lowercase standard dictionary Hanyu Pinyin with tone diacritics.
- Never use IPA, tone numbers, slashes, uppercase, or tone-less spelling for a
  syllable that is not neutral tone.
- Write syllables belonging to one lexical word together. Put a space only
  between separate words in a multi-word expression.
- Preserve dictionary neutral tones without a tone mark.

# 4. Pronunciation option contract — all must pass
For every item whose pronunciation is non-empty:
- options MUST contain exactly 4 non-empty, pairwise-distinct strings.
- options MUST contain pronunciation exactly once.
- correct_option MUST equal pronunciation byte-for-byte.
- The other 3 options MUST have the same syllable count whenever possible and
  differ subtly in tone, initial, final, or one syllable only.
- At least 2 of the 3 distractors MUST preserve the target's syllable count.
- At least 1 distractor MUST differ only by tone on one or more syllables.
- A distractor may be a non-word, but every syllable MUST be phonotactically
  valid standard Hanyu Pinyin. Never create an impossible initial-final pairing.
- Do not use a distractor that is an accepted pronunciation of the target Hanzi
  in the given meaning/context. Do not use spelling-format variants of the answer.
- Reject and regenerate unrelated, obviously removable, much longer/shorter,
  duplicate, or identical distractors before producing the JSON.

# 5. Vocabulary object
Use exactly these fields:
{
  "type": "vocabulary",
  "id": "<UUID_V4>",
  "word": "<TARGET_HANZI>",
  "pronunciation": "<CORRECT_PINYIN>",
  "meaning": "<KOREAN_MEANING>",
  "options": ["<PINYIN_1>", "<PINYIN_2>", "<PINYIN_3>", "<PINYIN_4>"],
  "correct_option": "<CORRECT_PINYIN>",
  "wrong_count": 0,
  "consecutive_correct": 0,
  "created_at": "<CURRENT_ISO_8601_UTC_TIMESTAMP>"
}

# 6. Grammar object
Extract the complete sentence, not an isolated pattern. Replace exactly one
target word/expression with exactly one ___, then append the full Korean sentence
meaning in parentheses. `answer` is always the actual Hanzi/expression that fills
the blank. `correct_option` is the pinyin the learner selects.

Use exactly these fields:
{
  "type": "grammar",
  "id": "<UUID_V4>",
  "sentence": "<FULL_CHINESE_SENTENCE_WITH_EXACTLY_ONE_BLANK>。(<FULL_KOREAN_MEANING>)",
  "pronunciation": "<TARGET_PINYIN>",
  "target_meaning": "<KOREAN_MEANING_OR_FUNCTION_OF_ONLY_THE_BLANK>",
  "answer": "<TARGET_HANZI_OR_EXPRESSION>",
  "options": ["<PINYIN_1>", "<PINYIN_2>", "<PINYIN_3>", "<PINYIN_4>"],
  "correct_option": "<TARGET_PINYIN>",
  "wrong_count": 0,
  "consecutive_correct": 0,
  "created_at": "<CURRENT_ISO_8601_UTC_TIMESTAMP>"
}

# 7. True-homophone grammar fallback only
Use this exception ONLY when all meaningful Hanzi candidates are genuine
homophones, so sound cannot distinguish the grammar choice. Do not use it merely
because the target is a particle. For this exception only:
- pronunciation MUST be "".
- options MUST be exactly 4 distinct Hanzi candidates including answer.
- correct_option MUST equal answer exactly.
- Keep every other grammar field and rule unchanged.

# 8. Silent final audit
Before responding, silently check every object against sections 1–7. Remove any
object whose lesson provenance is uncertain. Regenerate any invalid option set.
Then output only the final JSON array. Placeholder tokens above describe
structure only and are never lesson data.
```

### Step 3 — LingoLoop에 주입
출력된 JSON을 대시보드의 **데이터 주입** 텍스트박스에 붙여넣고 **저장하기**를
누릅니다. 마크다운 백틱(```` ```json ````)은 백엔드가 자동으로 제거합니다. ✨

새 문법 형식은 빈칸의 실제 한자를 `answer`에, 선택할 병음 정답을
`correct_option`에 따로 저장합니다. 기존 DB의 뜻/한자 선택지 데이터는 시작 시
자동 마이그레이션되어 학습 기록이 유지되며, 새 형식으로 다시 주입하기 전까지는
기존 발음 풀 방식이 호환용으로 적용됩니다.

### Step 4 — 연습 & 마스터
대시보드에는 학습 상태별로 **네 개의 버튼**이 있습니다 — 아래 "학습 상태" 표 참고.
**복습**이 매일 쓰는 기본 버튼입니다. 버튼을 누르면 **설정 패널**이 떠서 ①
데이터가 들어온 날짜 구간(양끝 핸들 슬라이더), ② 그 구간 안 항목 수(실시간),
③ 몇 개를 풀지(숫자 입력)를 고를 수 있습니다. 고른 범위에서 **무작위로**
출제되므로, 항목이 15개보다 많아도 매번 다른 조합을 연습할 수 있습니다.

단어·문법 모두 한자(문법은 문장 속 강조된 글자)와 뜻을 그대로 보여주고
**발음(병음)만 4지선다로** 묻습니다 — 정답을 미리 들려주지 않으니 🔊 버튼으로
힌트를 듣거나, 답을 고른 뒤 자동 재생되는 정답 발음으로 확인하세요.
**"다음" 버튼을 눌러야 다음 문제로 넘어갑니다** — 정답/오답 상관없이 발음을
충분히 들을 시간이 있습니다.

> 的/地/得 같은 동음이의 문법조사는 병음으로 구별할 수 없어서, 이런 항목만
> 예외적으로 기존 한자 4지선다 방식으로 출제됩니다.

그리고 다시 **Step 1**로 — 이제 프로필이 더 정교해져 있습니다. 🔁

---

## 🧠 학습 상태 (4단계 간격 반복)

LingoLoop은 가벼운 간격 반복(SRS) 모델로 항목을 4가지 상태로 관리합니다.
항목마다 매번 다시 시험 보는 게 아니라, **정답을 맞히면 며칠 쉬었다가** 다시
나타나서 "진짜 기억하는지"를 확인합니다.

| 상태 | 뜻 | 퀴즈에 나오는 조건 |
|---|---|---|
| 🆕 **미학습(new)** | 한 번도 안 풀어본 항목 | **새 단어 학습** 버튼 |
| 💤 **학습완(fresh)** | 방금 정답을 맞혀 유예기간(3일) 동안 쉬는 중 | **학습완 재확인** 버튼(선택) — 아래 참고 |
| 🔁 **학습필요(due)** | 방금 오답이었거나, 유예기간이 끝나 다시 확인할 때 | **복습** 버튼 |
| 🏆 **완전학습완(mastered)** | 별도 세션 3번 연속으로 첫 시도 정답 | **마스터 연습** 버튼(선택) |

> **학습완 재확인**은 잠자는 항목을 그냥 다시 확인하는 용도라, 정답/오답을
> **DB에 기록하지 않습니다** — 유예 타이머(3일)나 연속 정답 수를 건드리지 않아
> 잠자는 상태가 그대로 유지됩니다.

상태 전이: `미학습 --정답--> 학습완 --(3일 경과)--> 학습필요 --정답--> 학습완(반복, 3번째면 완전학습완) / --오답--> 학습필요(유예 없이 즉시)`

**완전학습완도 틀리면 되돌아갑니다** — 마스터 연습에서 오답을 내면 학습필요로
다시 떨어집니다(진짜 안 까먹었는지 계속 확인).

| 그 외 규칙 | 동작 |
|---|---|
| **가중 정렬** | 같은 모드 안에서 우선순위 = `wrong_count * 10 + 최신성(0~100)`; 상위 15개를 출제. |
| **1세션 1카운트** | 한 세션에서 같은 문제를 여러 번 틀려도 `wrong_count`는 최초 1회만 +1 (프론트 `Set` 방어). |

대시보드 좌하단 구석의 **🗑 DB 리셋** 버튼은 데이터 포맷을 이것저것 바꿔가며
테스트할 때 쓰는 개발용 기능입니다 — 클릭하면 확인 후 단어·문법을 전부
삭제합니다(되돌릴 수 없음).

---

## 🌏 다른 언어로 바꾸기 (예: 광둥어/광저우)

이 앱은 발음 표기법을 특정 언어에 하드코딩하지 않습니다. **광둥어(광저우 지역
중국어)** 로 바꾸는 것도 가능합니다:

1. [`src/frontend/app.js`](src/frontend/app.js)에서 `TTS_LANG`을 `"zh-CN"` →
   **`"zh-HK"`** 로, `STUDY_LANG_LABEL`을 `"광둥어"` 로 바꿉니다.
   (Edge에는 광둥어 음성 HiuGaai·HiuMaan·WanLung이 내장돼 있습니다.)
2. 데이터는 병음 대신 **Jyutping(월병)** 발음으로 임포트합니다 — Step 2 추출
   프롬프트에서 "STANDARD DICTIONARY PINYIN" 부분을 `Jyutping (e.g. "nei5 hou2",
   "ngo5", "m4 goi1")` 로 바꾸면 됩니다.
3. 기존 만다린 데이터는 발음 체계가 완전히 다르므로, 좌하단 **🗑 DB 리셋** 후
   광둥어 데이터로 새로 임포트하세요.

> 만다린과 광둥어는 한자는 대체로 공유하지만 발음이 완전히 달라서, 한 DB에
> 섞지 말고 언어별로 따로 쓰는 걸 권장합니다.

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
| `GET` | `/api/quiz` | `mode`(new/fresh/due/mastered) + `start`/`end`(날짜 구간) + `limit`(무작위 샘플 수) 로 문항 반환. |
| `GET` | `/api/quiz-meta` | `mode`별 유입 날짜 목록과 날짜별 개수(기간 슬라이더용). |
| `PUT` | `/api/review` | 채점 결과 저장 (`{id, type, correct}`); `last_reviewed_at` 갱신. |
| `GET` | `/api/stats` | 4가지 학습 상태별 개수 + 마스터율. |
| `POST` | `/api/reset` | 단어·문법 전체 삭제(개발용, 되돌릴 수 없음). |
