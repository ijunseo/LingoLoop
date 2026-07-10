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
 * 대시보드/퀴즈 뷰를 전환하고 탭 활성 상태를 갱신한다.
 * @param {"dashboard"|"quiz"} name - 표시할 뷰 이름.
 */
function showView(name) {
  $("#view-dashboard").classList.toggle("hidden", name !== "dashboard");
  $("#view-quiz").classList.toggle("hidden", name !== "quiz");
  $$(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  if (name === "dashboard") loadStats();
}
$$(".tab-btn").forEach((b) => b.addEventListener("click", () => showView(b.dataset.tab)));

// --------------------------------------------------------------------------- //
// 발음 재생 (Text-to-speech)
// --------------------------------------------------------------------------- //
// 학습 언어. 다른 언어로 바꾸려면 이 한 줄만 수정한다("en-US", "ja-JP" 등).
// 해당 언어의 OS 음성이 설치돼 있어야 소리가 난다.
const TTS_LANG = "zh-CN"; // 중국어(만다린) 학습용

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
  const base = TTS_LANG.split("-")[0].toLowerCase();
  const voice = window.speechSynthesis
    .getVoices()
    .find((v) => v.lang && v.lang.toLowerCase().startsWith(base));
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

// 일부 브라우저는 음성 목록을 비동기로 로드하므로 미리 warm-up 한다.
if ("speechSynthesis" in window) window.speechSynthesis.getVoices();

// --------------------------------------------------------------------------- //
// 대시보드: 통계 + 데이터 주입 (Dashboard)
// --------------------------------------------------------------------------- //
/** 통계 API를 호출해 대시보드 숫자들을 갱신한다. @returns {Promise<void>} */
async function loadStats() {
  try {
    const r = await fetch("/api/stats");
    const s = await r.json();
    $("#stat-total").textContent = s.overall.total;
    $("#stat-mastered").textContent = s.overall.mastered;
    $("#stat-due").textContent =
      (s.vocabulary?.due || 0) + (s.grammar?.due || 0);
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
    pronunciation: "/wɔ/",
    meaning: "나",
    options: ["너", "나", "그", "우리"],
    correct_option: "나",
    wrong_count: 0,
    consecutive_correct: 0,
    created_at: new Date().toISOString(),
  },
  {
    type: "grammar",
    id: crypto.randomUUID(),
    sentence: "你 ___ 学生。(너는 학생이다.)",
    options: ["是", "有", "在", "的"],
    correct_option: "是",
    wrong_count: 0,
    consecutive_correct: 0,
    created_at: new Date().toISOString(),
  },
];

// --------------------------------------------------------------------------- //
// 퀴즈 엔진 (Quiz engine)
// --------------------------------------------------------------------------- //
/**
 * 진행 중인 퀴즈 세션 상태.
 * @type {{queue: object[], uniqueTotal: number, solved: number,
 *         everWrong: Set<string>, locked: boolean}}
 */
const quiz = {
  queue: [],
  uniqueTotal: 0,
  solved: 0,
  everWrong: new Set(), // 1세션 1카운트 방어용
  locked: false,
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

/** 퀴즈 데이터를 받아 세션을 초기화하고 첫 문항을 그린다. @returns {Promise<void>} */
async function startQuiz() {
  showView("quiz");
  $("#quiz-done").classList.add("hidden");
  $("#quiz-card").classList.remove("hidden");
  const r = await fetch("/api/quiz");
  const data = await r.json();
  quiz.queue = data.items;
  quiz.uniqueTotal = data.items.length;
  quiz.solved = 0;
  quiz.everWrong = new Set();
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
  $("#next-btn").classList.add("hidden");

  // 진행률
  const pct = quiz.uniqueTotal ? (quiz.solved / quiz.uniqueTotal) * 100 : 0;
  $("#quiz-progress-bar").style.width = pct + "%";
  $("#quiz-progress-label").textContent = `${quiz.solved} / ${quiz.uniqueTotal}`;
  $("#quiz-type-badge").textContent = item.type === "vocabulary" ? "단어" : "문법";

  // 문제 본문
  const q = $("#quiz-question");
  if (item.type === "vocabulary") {
    $("#quiz-prompt").textContent = "알맞은 뜻을 고르세요";
    q.innerHTML = `
      <div class="text-5xl font-extrabold tracking-tight">${escapeHtml(item.word)}</div>
      ${item.pronunciation ? `<div class="mt-2 font-mono text-brand-400">${escapeHtml(item.pronunciation)}</div>` : ""}
    `;
    speak(item.word);
  } else {
    $("#quiz-prompt").textContent = "빈칸에 알맞은 것을 고르세요";
    const html = escapeHtml(item.sentence).replace(/_+/g, '<span class="blank"></span>');
    q.innerHTML = `<div class="text-2xl font-semibold leading-relaxed">${html}</div>`;
    speakSentence(item.sentence, "，"); // 빈칸은 짧은 쉼으로 읽음
  }

  // 보기(정답 포함 4지선다, 순서 섞기)
  const box = $("#quiz-options");
  box.innerHTML = "";
  shuffle(item.options).forEach((opt) => {
    const btn = document.createElement("button");
    btn.className = "option-btn";
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
 * @param {HTMLButtonElement} btn - 클릭된 보기 버튼.
 * @param {string} opt - 선택한 보기 텍스트.
 * @param {object} item - 현재 문항.
 */
async function selectOption(btn, opt, item) {
  if (quiz.locked) return;
  quiz.locked = true;
  const isCorrect = opt === item.correct_option;

  // 정답 공개
  $$("#quiz-options .option-btn").forEach((b) => {
    b.disabled = true;
    if (b.textContent === item.correct_option) b.classList.add("correct");
  });
  if (!isCorrect) btn.classList.add("wrong");

  if (isCorrect) {
    if (!quiz.everWrong.has(item.id)) {
      // 첫 시도 정답 → 마스터 카운트 반영
      sendReview(item, true);
    }
    if (item.type === "grammar") {
      speakSentence(item.sentence, item.correct_option);
    }
    quiz.solved += 1;
    quiz.queue.shift(); // 푼 항목 제거
    setTimeout(nextStep, 650);
  } else {
    if (!quiz.everWrong.has(item.id)) {
      // 1세션 1카운트: 최초 오답 1회만 DB에 반영
      sendReview(item, false);
      quiz.everWrong.add(item.id);
    }
    // 이 항목을 큐 맨 뒤로 재삽입
    const [cur] = quiz.queue.splice(0, 1);
    quiz.queue.push(cur);
    $("#next-btn").classList.remove("hidden");
  }
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
  $("#quiz-done-msg").textContent = empty
    ? "복습할 항목이 없어요. 데이터를 먼저 주입해 주세요!"
    : `${quiz.uniqueTotal}개 항목을 모두 풀었어요. 틀린 항목은 다음 복습에 우선 출제됩니다.`;
}

$("#start-quiz-btn").addEventListener("click", startQuiz);
$("#back-dash-btn").addEventListener("click", () => showView("dashboard"));
$("#tts-btn").addEventListener("click", () => {
  const item = quiz.queue[0];
  if (!item) return;
  if (item.type === "vocabulary") speak(item.word);
  else speakSentence(item.sentence, "，");
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
