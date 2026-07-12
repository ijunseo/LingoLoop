/* LingoLoop frontend — vanilla JS
 *
 * 대시보드(통계/데이터 주입)와 4지선다 복습 퀴즈를 담당한다.
 * 백엔드 API(/api/*)와 통신하며, 발음은 Web Speech API로 재생한다.
 * TTS 텍스트 정규화는 tts-util.js의 cleanSentenceForTTS를 사용한다.
 */
"use strict";

/** @param {string} sel @returns {Element|null} 첫 번째 매칭 요소. */
const $ = (sel) => document.querySelector(sel);
/** @param {string} sel @returns {NodeListOf<Element>} 매칭되는 모든 요소. */
const $$ = (sel) => document.querySelectorAll(sel);

// --------------------------------------------------------------------------- //
// 화면 전환 (Navigation)
// --------------------------------------------------------------------------- //
/**
 * 대시보드/설정/퀴즈 뷰를 전환하고 탭 활성 상태를 갱신한다.
 * @param {"dashboard"|"config"|"quiz"} name - 표시할 뷰 이름.
 */
function showView(name) {
  $("#view-dashboard").classList.toggle("hidden", name !== "dashboard");
  $("#view-config").classList.toggle("hidden", name !== "config");
  $("#view-quiz").classList.toggle("hidden", name !== "quiz");
  $$(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  if (name === "dashboard") loadStats();
}
// 헤더 "복습" 탭은 due(복습) 모드의 설정 패널을 연다.
// (예전엔 showView("quiz")만 호출해 퀴즈가 시작되지 않은 빈 화면이 떴다 — 버그.)
$$(".tab-btn").forEach((b) =>
  b.addEventListener("click", () => {
    if (b.dataset.tab === "quiz") openConfig("due");
    else showView("dashboard");
  }),
);

// --------------------------------------------------------------------------- //
// 발음 재생 (Text-to-speech)
// --------------------------------------------------------------------------- //
// 학습 언어 설정. 광둥어(광저우)로 바꾸려면 TTS_LANG를 "zh-HK"로 바꾸고,
// 데이터는 병음 대신 Jyutping(월병) 발음으로 임포트한다(README "언어 바꾸기" 참고).
// 해당 언어의 OS 음성이 설치돼 있어야 소리가 난다.
const TTS_LANG = "zh-CN";          // 만다린. 광둥어(광저우)는 "zh-HK"
const STUDY_LANG_LABEL = "중국어";  // 안내 배너에 쓰는 언어 이름

/** @type {SpeechSynthesisVoice[]} 캐시된 음성 목록. */
let VOICES = [];

/** 브라우저에서 음성 목록을 다시 읽어 캐시한다(비동기 로드 대응). */
function refreshVoices() {
  if ("speechSynthesis" in window) VOICES = window.speechSynthesis.getVoices() || [];
}

/** 광둥어(월어) 로케일인지 판별한다: zh-HK / zh-MO / yue-*. */
function isCantonese(lang) {
  const l = (lang || "").toLowerCase();
  return l === "zh-hk" || l === "zh-mo" || l.startsWith("yue");
}

/**
 * TTS_LANG에 맞는 음성을 고른다.
 * 1) 정확히 일치하는 로케일(zh-CN 등)을 최우선.
 * 2) 같은 언어(zh) 폴백. 단 만다린을 원할 땐 광둥어(zh-HK) 음성은 건너뛴다 —
 *    zh-CN 음성이 없는 환경에서 zh-HK가 잡혀 만다린 글자를 광둥어로 읽어버리는
 *    걸 막기 위함(정말 zh 음성이 광둥어뿐이면 마지막에 그거라도 쓴다).
 * @returns {SpeechSynthesisVoice|undefined}
 */
function pickVoice() {
  const want = TTS_LANG.toLowerCase();
  const base = want.split("-")[0];
  const exact = VOICES.find((v) => v.lang && v.lang.toLowerCase() === want);
  if (exact) return exact;
  const sameLang = VOICES.filter((v) => v.lang && v.lang.toLowerCase().startsWith(base));
  if (!isCantonese(want)) {
    const mandarin = sameLang.find((v) => !isCantonese(v.lang));
    if (mandarin) return mandarin;
  }
  return sameLang[0];
}

/**
 * 주어진 텍스트를 TTS_LANG 언어로 읽는다.
 * @param {string} text - 읽을 텍스트.
 */
function speak(text) {
  if (!("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = TTS_LANG;
  u.rate = 0.9;
  const voice = pickVoice();
  if (voice) u.voice = voice;
  window.speechSynthesis.speak(u);
}

/**
 * 문법 예문에서 번역 괄호를 빼고 빈칸을 채운 뒤 읽는다.
 * @param {string} sentence - 원본 예문.
 * @param {string} fill - 빈칸 대체 문자열(정답 또는 짧은 쉼 "，").
 */
function speakSentence(sentence, fill) {
  speak(cleanSentenceForTTS(sentence, fill));
}

let ttsWarned = false;
/**
 * 사용 가능한 (중국어) 음성이 없으면 안내 배너를 한 번 띄운다.
 * VS Code 내장 미리보기 등에서는 음성 엔진이 없어 소리가 나지 않는다.
 */
function checkTTSHealth() {
  if (ttsWarned) return;
  refreshVoices();
  const ok = "speechSynthesis" in window && VOICES.length > 0 && pickVoice();
  if (ok) return;
  ttsWarned = true;
  const bar = document.createElement("div");
  bar.className = "tts-warning";
  bar.innerHTML =
    `⚠️ 이 환경에서 ${STUDY_LANG_LABEL} 음성을 찾지 못했어요. VS Code 미리보기가 아니라 ` +
    "<b>Chrome / Edge</b>에서 <b>http://127.0.0.1:8000</b> 을 여세요. " +
    `(Edge는 ${STUDY_LANG_LABEL} 음성 내장) `;
  const close = document.createElement("button");
  close.textContent = "✕";
  close.setAttribute("aria-label", "닫기");
  close.addEventListener("click", () => bar.remove());
  bar.appendChild(close);
  document.body.appendChild(bar);
}

// 음성 목록은 비동기로 로드되므로 즉시 + voiceschanged + 지연 후 재확인한다.
if ("speechSynthesis" in window) {
  refreshVoices();
  window.speechSynthesis.onvoiceschanged = refreshVoices;
  setTimeout(() => { refreshVoices(); checkTTSHealth(); }, 2000);
}

// --------------------------------------------------------------------------- //
// 대시보드: 통계 + 데이터 주입 (Dashboard)
// --------------------------------------------------------------------------- //
/**
 * 통계 API를 호출해 대시보드 숫자들을 갱신한다.
 * 4가지 학습 상태(new/fresh/due/mastered)를 그대로 타일에 반영한다.
 * @returns {Promise<void>}
 */
async function loadStats() {
  try {
    const r = await fetch("/api/stats");
    const s = await r.json();
    $("#stat-new").textContent = s.overall.new;
    $("#stat-fresh").textContent = s.overall.fresh;
    $("#stat-due").textContent = s.overall.due;
    $("#stat-mastered").textContent = s.overall.mastered;
    $("#stat-total").textContent = s.overall.total;
    $("#stat-rate").textContent = s.overall.mastery_rate + "%";
  } catch (e) {
    console.error(e);
  }
}

/**
 * 텍스트박스 내용을 /api/import로 보내 저장하고 결과 메시지를 표시한다.
 * @returns {Promise<void>}
 */
async function doImport() {
  const text = $("#import-text").value.trim();
  const msg = $("#import-msg");
  if (!text) {
    msg.textContent = "붙여넣은 내용이 없어요.";
    msg.className = "text-sm text-amber-400";
    return;
  }
  msg.textContent = "저장 중…";
  msg.className = "text-sm text-slate-400";
  try {
    const r = await fetch("/api/import", {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: text,
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "실패");
    const c = data.imported;
    msg.textContent = `✅ 단어 ${c.vocabulary} · 문법 ${c.grammar} 저장 (건너뜀 ${c.skipped})`;
    msg.className = "text-sm text-emerald-400";
    $("#import-text").value = "";
    loadStats();
  } catch (e) {
    // fetch가 TypeError를 던지면 대개 백엔드에 연결할 수 없는 상황이다.
    const offline = e instanceof TypeError;
    msg.textContent = offline
      ? "❌ 서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인하세요 (uv run uvicorn src.backend.server:app)."
      : "❌ " + e.message;
    msg.className = "text-sm text-rose-400";
  }
}
$("#import-btn").addEventListener("click", doImport);

$("#sample-btn").addEventListener("click", () => {
  $("#import-text").value = JSON.stringify(SAMPLE_ITEMS, null, 2);
});

/** '샘플 넣기' 버튼이 채워 넣는 예시 항목(중국어). */
const SAMPLE_ITEMS = [
  {
    type: "vocabulary",
    id: crypto.randomUUID(),
    word: "我",
    pronunciation: "wǒ", // 표준 병음(사전식), 슬래시·IPA 금지
    meaning: "나",
    options: ["wǒ", "wó", "wěi", "wù"],
    correct_option: "wǒ",
    wrong_count: 0,
    consecutive_correct: 0,
    created_at: new Date().toISOString(),
  },
  {
    type: "grammar",
    id: crypto.randomUUID(),
    sentence: "你 ___ 学生。(너는 학생이다.)",
    pronunciation: "shì",
    target_meaning: "~이다 (be동사)",
    answer: "是",
    options: ["shì", "shí", "sì", "shǐ"],
    correct_option: "shì",
    wrong_count: 0,
    consecutive_correct: 0,
    created_at: new Date().toISOString(),
  },
];

/**
 * DB의 vocabulary·grammar를 전부 지운다(개발용, 되돌릴 수 없음).
 * 데이터 포맷을 이것저것 바꿔가며 테스트할 때 쓰는 임시 기능이라 구석에 뒀다.
 */
$("#reset-db-btn").addEventListener("click", async () => {
  const btn = $("#reset-db-btn");
  if (!confirm("단어·문법 데이터를 전부 삭제할까요? 되돌릴 수 없어요.")) return;
  try {
    const r = await fetch("/api/reset", { method: "POST" });
    if (!r.ok) throw new Error("reset failed");
    quiz.queue = [];
    quiz.currentItem = null;
    btn.textContent = "✅ 초기화됨";
    setTimeout(() => { btn.textContent = "🗑 DB 리셋"; }, 1500);
    showView("dashboard"); // 진행 중이던 퀴즈에서 빠져나오고 stats도 갱신한다
  } catch (e) {
    console.error(e);
    btn.textContent = "❌ 실패";
    setTimeout(() => { btn.textContent = "🗑 DB 리셋"; }, 1500);
  }
});

// --------------------------------------------------------------------------- //
// 퀴즈 설정 패널 (기간 슬라이더 + 문항 수)
// --------------------------------------------------------------------------- //
const rangeStart = $("#range-start");
const rangeEnd = $("#range-end");
let configMode = "due";
let configDates = [];   // 정렬된 날짜 문자열(슬라이더 눈금)
let configCounts = {};  // 날짜 → 항목 수

function fmtDate(d) {
  return d || "(날짜없음)";
}

/**
 * 모드 버튼을 누르면 바로 시작하지 않고 기간·개수 설정 패널을 연다.
 * 해당 모드에 항목이 없거나 메타 로딩이 실패하면 곧장 startQuiz로 넘긴다.
 * @param {"new"|"due"|"fresh"|"mastered"} mode
 * @returns {Promise<void>}
 */
async function openConfig(mode) {
  configMode = mode;
  let meta;
  try {
    const r = await fetch(`/api/quiz-meta?mode=${encodeURIComponent(mode)}`);
    meta = await r.json();
  } catch (e) {
    console.error(e);
    startQuiz(mode, {}); // 메타 실패 → 기본 방식으로 바로 시작
    return;
  }
  if (!meta.total) {
    startQuiz(mode, {}); // 항목 없음 → 빈 화면 안내
    return;
  }

  configDates = meta.dates;
  configCounts = meta.counts;
  $("#config-title").textContent = MODE_LABEL[mode] || mode;

  const maxIdx = Math.max(0, configDates.length - 1);
  const single = configDates.length <= 1;
  rangeStart.min = rangeEnd.min = "0";
  rangeStart.max = rangeEnd.max = String(maxIdx);
  rangeStart.value = "0";
  rangeEnd.value = String(maxIdx);
  rangeStart.disabled = rangeEnd.disabled = single; // 날짜가 하루뿐이면 슬라이더 고정
  updateRange();
  $("#config-limit").value = String(Math.min(meta.total, 15)); // 기본 15개
  showView("config");
}

/** 슬라이더 상태에 맞춰 라벨·채움바·구간 개수·개수입력 최대값을 갱신한다. */
function updateRange() {
  const s = +rangeStart.value;
  const e = +rangeEnd.value;
  const denom = Math.max(1, configDates.length - 1);
  $("#config-start-label").textContent = fmtDate(configDates[s]);
  $("#config-end-label").textContent = fmtDate(configDates[e]);

  // 채움 바(선택 구간 시각화)
  const left = configDates.length <= 1 ? 0 : (s / denom) * 100;
  const width = configDates.length <= 1 ? 100 : ((e - s) / denom) * 100;
  $("#dual-range-fill").style.left = left + "%";
  $("#dual-range-fill").style.width = width + "%";

  // 구간 내 항목 수
  let count = 0;
  for (let i = s; i <= e; i++) count += configCounts[configDates[i]] || 0;
  $("#config-in-range").textContent = count;

  // 문항 수 입력 상한 클램프
  const limitEl = $("#config-limit");
  limitEl.max = String(count);
  if (+limitEl.value > count) limitEl.value = String(count);
  if (+limitEl.value < 1) limitEl.value = String(Math.min(1, count));
}

rangeStart.addEventListener("input", () => {
  if (+rangeStart.value > +rangeEnd.value) rangeStart.value = rangeEnd.value; // 교차 방지
  updateRange();
});
rangeEnd.addEventListener("input", () => {
  if (+rangeEnd.value < +rangeStart.value) rangeEnd.value = rangeStart.value;
  updateRange();
});
$("#config-limit").addEventListener("input", () => {
  const el = $("#config-limit");
  const max = +el.max || 0;
  if (+el.value > max) el.value = String(max);
});
$("#config-start-btn").addEventListener("click", () => {
  const s = +rangeStart.value;
  const e = +rangeEnd.value;
  let limit = parseInt($("#config-limit").value, 10);
  if (!Number.isFinite(limit) || limit < 1) limit = 1;
  startQuiz(configMode, { start: configDates[s], end: configDates[e], limit });
});
$("#config-cancel-btn").addEventListener("click", () => showView("dashboard"));

// --------------------------------------------------------------------------- //
// 퀴즈 엔진 (Quiz engine)
// --------------------------------------------------------------------------- //
/** 학습 모드별 한글 라벨(대시보드 버튼·퀴즈 배지·완료 메시지에서 공용으로 사용). */
const MODE_LABEL = {
  new: "새 단어 학습",
  due: "복습",
  fresh: "학습완 재확인", // 쉬는 중인 항목을 기록 없이 다시 확인
  mastered: "마스터 연습",
};

/**
 * 진행 중인 퀴즈 세션 상태.
 * @type {{mode: string, queue: object[], uniqueTotal: number, solved: number,
 *         everWrong: Set<string>, locked: boolean,
 *         pronPool: string[], grammarPronPool: string[],
 *         currentCorrect: string, currentItem: object|null, firstTryCorrect: number}}
 */
const quiz = {
  mode: "due",            // "new" | "due" | "mastered"
  queue: [],
  uniqueTotal: 0,
  solved: 0,
  everWrong: new Set(), // 1세션 1카운트 방어용
  locked: false,
  pronPool: [],          // 단어 발음 오답 후보 풀
  grammarPronPool: [],   // 문법 발음 오답 후보 풀(단어 풀과 분리)
  currentCorrect: "",    // 현재 문항의 정답 텍스트
  currentItem: null,     // 현재 화면에 표시 중인 문항(큐 변형과 무관하게 고정)
  firstTryCorrect: 0,    // 이번 세션에서 첫 시도에 맞힌 개수(마스터 진행에 반영됨)
};

/**
 * 배열을 복사해 섞은 새 배열을 반환한다(Fisher–Yates).
 * @param {any[]} arr
 * @returns {any[]}
 */
function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/**
 * 발음 4지선다 보기를 만든다. 정답 + pool에서 뽑은 오답(최대 3개).
 * 단어는 quiz.pronPool, 문법은 quiz.grammarPronPool에서 오답을 뽑는다
 * (서로 섞이지 않도록 종류별로 별도 풀을 쓴다).
 * @param {string} correct - 정답 발음 텍스트.
 * @param {string[]} pool - 오답 후보 발음 풀.
 * @returns {string[]} 섞인 발음 보기(최대 4개).
 */
function pronOptions(correct, pool, fallbackPool = []) {
  // 같은 종류(단어/문법) 풀에서 오답을 우선 뽑되, 항목이 적어 3개가 안 되면
  // 다른 종류 풀에서 빌려와 최대한 4지선다를 채운다(1지선다 방지).
  const same = shuffle(pool.filter((p) => p && p !== correct));
  let distractors = same.slice(0, 3);
  if (distractors.length < 3) {
    const extra = shuffle(
      fallbackPool.filter((p) => p && p !== correct && !distractors.includes(p)),
    );
    distractors = distractors.concat(extra).slice(0, 3);
  }
  return shuffle([correct, ...distractors]);
}

/**
 * LLM이 해당 항목에 직접 만든 병음 선택지가 새 스키마에 맞는지 확인한다.
 * 정확히 4개·중복 없음·correct_option=pronunciation일 때만 사용한다.
 * 그렇지 않은 과거 DB 항목은 pronOptions() 호환 폴백으로 넘긴다.
 * @param {object} item - 퀴즈 항목.
 * @returns {string[]|null} 검증된 뒤 섞인 병음 보기 또는 null.
 */
function authoredPronOptions(item) {
  const correct = cleanPronunciation(item.pronunciation);
  const options = Array.isArray(item.options)
    ? item.options.map(cleanPronunciation).filter(Boolean)
    : [];
  const unique = new Set(options);
  if (
    options.length !== 4 ||
    unique.size !== 4 ||
    cleanPronunciation(item.correct_option) !== correct ||
    !unique.has(correct)
  ) {
    return null;
  }
  return shuffle(options);
}

/**
 * 서버에서 받은 문항을 화면 표시용으로 정규화한다.
 * 발음 필드는 슬래시(IPA 표기 관습)를 제거해 사전식으로 다듬는다.
 * @param {object} item - /api/quiz가 내려준 원본 문항.
 * @returns {object} 정규화된 문항.
 */
function normalizeItem(item) {
  if (item.pronunciation) {
    return { ...item, pronunciation: cleanPronunciation(item.pronunciation) };
  }
  return item;
}

/**
 * 퀴즈 데이터를 받아 세션을 초기화하고 첫 문항을 그린다.
 * @param {"new"|"due"|"fresh"|"mastered"} mode - 어떤 학습 상태의 항목을 출제할지.
 * @param {{start?: string, end?: string, limit?: number}} [opts] - 기간·문항 수.
 * @returns {Promise<void>}
 */
async function startQuiz(mode, opts = {}) {
  quiz.mode = mode;
  showView("quiz");
  $("#quiz-mode-badge").textContent =
    mode === "fresh" ? "학습완 재확인 · 기록 안 함" : MODE_LABEL[mode] || mode;
  $("#quiz-done").classList.add("hidden");
  $("#quiz-card").classList.remove("hidden");
  let data;
  try {
    const params = new URLSearchParams({ mode });
    if (opts.start) params.set("start", opts.start);
    if (opts.end) params.set("end", opts.end);
    if (opts.limit) params.set("limit", String(opts.limit));
    const r = await fetch(`/api/quiz?${params.toString()}`);
    data = await r.json();
    if (!r.ok || !Array.isArray(data.items)) throw new Error(data.detail || "bad response");
  } catch (e) {
    // 서버가 꺼져 있거나 응답이 이상하면 크래시 대신 안내 화면을 보여준다.
    console.error(e);
    $("#quiz-card").classList.add("hidden");
    $("#quiz-done").classList.remove("hidden");
    $("#quiz-done-title").textContent = "불러오기 실패";
    $("#quiz-done-msg").textContent =
      "서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인하세요 (uv run uvicorn src.backend.server:app).";
    return;
  }
  quiz.queue = data.items.map(normalizeItem);
  quiz.uniqueTotal = quiz.queue.length;
  quiz.solved = 0;
  quiz.everWrong = new Set();
  quiz.firstTryCorrect = 0;
  // 발음 오답 후보 풀(중복 제거, 정규화된 값). 단어/문법은 서로 섞이지 않게 분리.
  quiz.pronPool = [
    ...new Set(
      quiz.queue
        .filter((i) => i.type === "vocabulary" && i.pronunciation)
        .map((i) => i.pronunciation),
    ),
  ];
  quiz.grammarPronPool = [
    ...new Set(
      quiz.queue
        .filter((i) => i.type === "grammar" && i.pronunciation)
        .map((i) => i.pronunciation),
    ),
  ];
  checkTTSHealth();
  if (!quiz.queue.length) {
    finishQuiz(true);
    return;
  }
  renderCurrent();
}

/** 큐의 맨 앞 문항을 화면에 렌더링하고 발음을 재생한다. */
function renderCurrent() {
  quiz.locked = false;
  const item = quiz.queue[0];
  quiz.currentItem = item; // 큐가 이후 변형돼도 "지금 화면" 참조는 고정
  $("#next-btn").classList.add("hidden");

  // 진행률
  const pct = quiz.uniqueTotal ? (quiz.solved / quiz.uniqueTotal) * 100 : 0;
  $("#quiz-progress-bar").style.width = pct + "%";
  $("#quiz-progress-label").textContent = `${quiz.solved} / ${quiz.uniqueTotal}`;
  $("#quiz-type-badge").textContent = item.type === "vocabulary" ? "단어" : "문법";

  // 문제 본문 + 보기 구성. quiz.currentCorrect에 정답 텍스트를 담는다.
  const q = $("#quiz-question");
  let options;
  let isPron = false; // true면 보기가 병음(발음) 텍스트 → 가독성용 스타일 적용
  if (item.type === "vocabulary" && item.pronunciation) {
    // 발음 매칭: 한자(+뜻)를 보여주고 올바른 발음을 고르게 한다.
    // 한자는 유추 가능하다는 전제하에, 목표인 '발음'에 집중시킨다.
    // 정답을 흘리지 않도록 출제 시 자동 재생하지 않는다(🔊로 힌트 청취 가능).
    $("#quiz-prompt").textContent = "발음을 고르세요 (🔊로 들어볼 수 있어요)";
    q.innerHTML = `
      <div class="text-5xl font-extrabold tracking-tight">${escapeHtml(item.word)}</div>
      <div class="mt-3 text-lg text-slate-400">${escapeHtml(item.meaning || "")}</div>
    `;
    quiz.currentCorrect = item.pronunciation;
    options = authoredPronOptions(item)
      || pronOptions(item.pronunciation, quiz.pronPool, quiz.grammarPronPool);
    isPron = true;
  } else if (item.type === "vocabulary") {
    // 발음 데이터가 없으면 기존 방식(뜻 고르기)으로 폴백.
    $("#quiz-prompt").textContent = "알맞은 뜻을 고르세요";
    q.innerHTML = `<div class="text-5xl font-extrabold tracking-tight">${escapeHtml(item.word)}</div>`;
    quiz.currentCorrect = item.correct_option;
    options = shuffle(item.options);
    speak(item.word);
  } else if (item.pronunciation) {
    // 발음 매칭: 빈칸을 "가리지 않고" 정답 한자를 그대로 보여준다(강조 표시).
    // 한자 모양으로 답을 찍는 걸 막기 위해, 4지선다는 한자가 아니라 그 글자의
    // 발음(병음)이다. 문장 전체 뜻은 원문의 괄호 번역을 그대로 보여주고,
    // 강조된 글자만의 개별 뜻/문법 기능도 따로 보여준다.
    $("#quiz-prompt").textContent = "강조된 글자의 발음을 고르세요 (🔊로 들어볼 수 있어요)";
    const answer = item.answer || item.correct_option; // 구버전 DB 호환
    const filled = escapeHtml(item.sentence).replace(
      /_+/g,
      `<span class="target-word">${escapeHtml(answer)}</span>`,
    );
    q.innerHTML = `
      <div class="text-2xl font-semibold leading-relaxed">${filled}</div>
      ${item.target_meaning
        ? `<div class="mt-3 text-base text-slate-400">${escapeHtml(answer)} → ${escapeHtml(item.target_meaning)}</div>`
        : ""}
    `;
    quiz.currentCorrect = item.pronunciation;
    options = authoredPronOptions(item)
      || pronOptions(item.pronunciation, quiz.grammarPronPool, quiz.pronPool);
    isPron = true;
  } else {
    // 발음 데이터가 없으면 기존 방식(빈칸에 맞는 한자 고르기)으로 폴백.
    $("#quiz-prompt").textContent = "빈칸에 알맞은 것을 고르세요";
    const html = escapeHtml(item.sentence).replace(/_+/g, '<span class="blank"></span>');
    q.innerHTML = `<div class="text-2xl font-semibold leading-relaxed">${html}</div>`;
    quiz.currentCorrect = item.correct_option;
    options = shuffle(item.options);
    speakSentence(item.sentence, "，"); // 빈칸은 짧은 쉼으로 읽음
  }

  // 보기 렌더링(정답 포함 4지선다)
  const box = $("#quiz-options");
  box.innerHTML = "";
  options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.className = isPron ? "option-btn pron" : "option-btn";
    btn.textContent = opt;
    btn.addEventListener("click", () => selectOption(btn, opt, item));
    box.appendChild(btn);
  });
}

/**
 * 보기 선택을 채점하고 정답/오답 처리를 한다.
 *
 * 정답: 이번 세션에서 처음 틀린 적 없으면 consecutive_correct +1(마스터 진행).
 * 오답: 세션 내 최초 1회만 wrong_count +1을 서버에 보내고(1세션 1카운트),
 *       해당 항목을 큐 뒤로 보내 다시 풀게 한다.
 *
 * 정답/오답 관계없이 정답 발음을 들려주고, 자동으로 넘어가지 않는다 —
 * 사용자가 발음을 다 듣고 "다음" 버튼을 눌러야 다음 문항으로 진행된다.
 *
 * @param {HTMLButtonElement} btn - 클릭된 보기 버튼.
 * @param {string} opt - 선택한 보기 텍스트.
 * @param {object} item - 현재 문항.
 */
async function selectOption(btn, opt, item) {
  if (quiz.locked) return;
  quiz.locked = true;
  const correct = quiz.currentCorrect;
  const isCorrect = opt === correct;
  // everWrong 키는 type+id로 잡는다: 단어와 문법이 같은 id를 쓸 수 있어(LLM이
  // UUID를 재사용하는 경우) id만 쓰면 서로의 1세션-1카운트 판정을 오염시킨다.
  const key = item.type + ":" + item.id;

  // 정답 공개
  $$("#quiz-options .option-btn").forEach((b) => {
    b.disabled = true;
    if (b.textContent === correct) b.classList.add("correct");
  });
  if (!isCorrect) btn.classList.add("wrong");

  // 정답/오답 관계없이 정답 발음을 들려준다(맞혀도 틀려도 발음은 들어야 한다).
  if (item.type === "vocabulary") speak(item.word);
  else speakSentence(item.sentence, item.answer || item.correct_option);

  // "학습완 재확인"(fresh)은 잠자는 항목을 그냥 다시 확인하는 용도라 DB에 기록하지
  // 않는다 — last_reviewed_at/streak을 안 건드려 잠자는 상태를 그대로 둔다.
  const record = quiz.mode !== "fresh";

  if (isCorrect) {
    if (!quiz.everWrong.has(key)) {
      // 첫 시도 정답 → (기록 모드면) 마스터 카운트 반영
      if (record) sendReview(item, true);
      quiz.firstTryCorrect += 1;
    }
    quiz.solved += 1;
    quiz.queue.shift(); // 푼 항목 제거
  } else {
    if (!quiz.everWrong.has(key)) {
      // 1세션 1카운트: 최초 오답 1회만 DB에 반영(기록 모드 한정)
      if (record) sendReview(item, false);
      quiz.everWrong.add(key);
    }
    // 이 항목을 큐 맨 뒤로 재삽입(재확인 모드에서도 맞힐 때까지 다시 풀게 한다)
    const [cur] = quiz.queue.splice(0, 1);
    quiz.queue.push(cur);
  }
  // 정답/오답 모두 "다음" 버튼을 눌러야 넘어간다(자동 진행 없음).
  $("#next-btn").classList.remove("hidden");
}

/** 큐가 비었으면 종료 화면, 아니면 다음 문항으로 진행한다. */
function nextStep() {
  if (quiz.queue.length === 0) finishQuiz(false);
  else renderCurrent();
}
$("#next-btn").addEventListener("click", nextStep);

/**
 * 채점 결과를 /api/review로 영속화한다(실패해도 학습 흐름은 막지 않음).
 * @param {object} item - 문항.
 * @param {boolean} correct - 정답 여부.
 * @returns {Promise<void>}
 */
async function sendReview(item, correct) {
  try {
    await fetch("/api/review", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: item.id, type: item.type, correct }),
    });
  } catch (e) {
    console.error("review failed", e);
  }
}

/**
 * 복습 종료 화면을 표시한다.
 * @param {boolean} empty - 풀 항목이 아예 없었는지 여부.
 */
function finishQuiz(empty) {
  $("#quiz-card").classList.add("hidden");
  $("#next-btn").classList.add("hidden");
  const done = $("#quiz-done");
  done.classList.remove("hidden");
  $("#quiz-progress-bar").style.width = "100%";
  const label = MODE_LABEL[quiz.mode] || quiz.mode;
  $("#quiz-done-title").textContent = `${label} 완료!`;
  if (empty) {
    const emptyMsg = {
      new: "새로 배울 항목이 없어요. 데이터를 먼저 주입해 주세요!",
      due: "지금 복습할 항목이 없어요. 학습완 항목은 며칠 뒤 다시 나타나요.",
      fresh: "지금 쉬는 중(학습완)인 항목이 없어요.",
      mastered: "아직 완전학습완 항목이 없어요. 복습으로 3번 연속 맞혀보세요!",
    };
    $("#quiz-done-msg").textContent = emptyMsg[quiz.mode] || "풀 항목이 없어요.";
    return;
  }
  const missed = quiz.everWrong.size;
  // 모드에 따라 안내 문구를 달리한다. fresh는 기록하지 않는 재확인 세션이다.
  const tail = quiz.mode === "fresh"
    ? ". 재확인 세션이라 학습 상태에는 전혀 반영되지 않았어요."
    : quiz.mode === "mastered"
    ? ". 틀린 항목은 학습필요로 되돌아가 다시 확인하게 돼요."
    : ". 정답을 맞히면 3일간 쉬었다가 다시 나오고, 3번 연속 통과하면 완전학습완이에요.";
  $("#quiz-done-msg").textContent =
    `${quiz.uniqueTotal}개 항목 완료 — 첫 시도 정답 ${quiz.firstTryCorrect}개` +
    (missed ? `, 실수 후 통과 ${missed}개` : "") + tail;
}

$$(".mode-btn").forEach((b) => b.addEventListener("click", () => openConfig(b.dataset.mode)));
$("#back-dash-btn").addEventListener("click", () => showView("dashboard"));
$("#tts-btn").addEventListener("click", () => {
  // quiz.queue[0]이 아니라 quiz.currentItem을 써야 한다: 정답을 맞히면
  // selectOption()이 즉시 큐를 앞으로 밀어버려서(shift), "다음" 버튼을 누르기
  // 전까지는 queue[0]이 이미 다음 문제를 가리킨다 — 그 상태에서 🔊를 누르면
  // 지금 화면에 있는 문제가 아니라 다음 문제 발음이 나오는 버그가 있었다.
  const item = quiz.currentItem;
  if (!item) return;
  if (item.type === "vocabulary") {
    speak(item.word);
  } else if (item.pronunciation) {
    // 발음 매칭 형식: 화면에 이미 정답 한자가 보이므로 자유롭게 들려준다.
    speakSentence(item.sentence, item.answer || item.correct_option);
  } else if (quiz.locked) {
    // 구식 빈칸-한자 폴백, 채점 후: 정답을 채워서 들려준다.
    speakSentence(item.sentence, item.answer || item.correct_option);
  } else {
    // 구식 빈칸-한자 폴백, 채점 전: 빈칸은 짧은 쉼으로(정답 노출 방지).
    speakSentence(item.sentence, "，");
  }
});

// --------------------------------------------------------------------------- //
/**
 * 사용자 입력을 HTML에 넣기 전에 특수문자를 이스케이프한다.
 * @param {string} s
 * @returns {string}
 */
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// 초기 화면
showView("dashboard");
