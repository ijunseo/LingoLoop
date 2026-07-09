/* LingoLoop frontend — vanilla JS */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// --------------------------------------------------------------------------- //
// Navigation
// --------------------------------------------------------------------------- //
function showView(name) {
  $("#view-dashboard").classList.toggle("hidden", name !== "dashboard");
  $("#view-quiz").classList.toggle("hidden", name !== "quiz");
  $$(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  if (name === "dashboard") loadStats();
}
$$(".tab-btn").forEach((b) => b.addEventListener("click", () => showView(b.dataset.tab)));

// --------------------------------------------------------------------------- //
// Text-to-speech
// --------------------------------------------------------------------------- //
function speak(text) {
  if (!("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
  u.rate = 0.95;
  const voice = window.speechSynthesis
    .getVoices()
    .find((v) => v.lang && v.lang.startsWith("en"));
  if (voice) u.voice = voice;
  window.speechSynthesis.speak(u);
}
// Warm up voices list (some browsers load it async).
if ("speechSynthesis" in window) window.speechSynthesis.getVoices();

// --------------------------------------------------------------------------- //
// Dashboard: stats + import
// --------------------------------------------------------------------------- //
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
    msg.textContent = "❌ " + e.message;
    msg.className = "text-sm text-rose-400";
  }
}
$("#import-btn").addEventListener("click", doImport);

$("#sample-btn").addEventListener("click", () => {
  $("#import-text").value = JSON.stringify(SAMPLE_ITEMS, null, 2);
});

const SAMPLE_ITEMS = [
  {
    type: "vocabulary",
    id: crypto.randomUUID(),
    word: "serendipity",
    pronunciation: "/ˌserənˈdɪpəti/",
    meaning: "뜻밖의 행운, 우연한 발견",
    options: ["뜻밖의 행운, 우연한 발견", "극심한 피로", "고의적인 방해", "엄격한 규율"],
    correct_option: "뜻밖의 행운, 우연한 발견",
    wrong_count: 0,
    consecutive_correct: 0,
    created_at: new Date().toISOString(),
  },
  {
    type: "grammar",
    id: crypto.randomUUID(),
    sentence: "I wish I ___ more time to finish it.",
    options: ["had", "have", "will have", "am having"],
    correct_option: "had",
    wrong_count: 0,
    consecutive_correct: 0,
    created_at: new Date().toISOString(),
  },
];

// --------------------------------------------------------------------------- //
// Quiz engine
// --------------------------------------------------------------------------- //
const quiz = {
  queue: [],
  uniqueTotal: 0,
  solved: 0,
  everWrong: new Set(), // 1-session-1-count guard
  locked: false,
};

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

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

function renderCurrent() {
  quiz.locked = false;
  const item = quiz.queue[0];
  $("#next-btn").classList.add("hidden");

  // progress
  const pct = quiz.uniqueTotal ? (quiz.solved / quiz.uniqueTotal) * 100 : 0;
  $("#quiz-progress-bar").style.width = pct + "%";
  $("#quiz-progress-label").textContent = `${quiz.solved} / ${quiz.uniqueTotal}`;
  $("#quiz-type-badge").textContent = item.type === "vocabulary" ? "단어" : "문법";

  // question body
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
    speak(item.sentence.replace(/_+/g, " blank "));
  }

  // options
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

async function selectOption(btn, opt, item) {
  if (quiz.locked) return;
  quiz.locked = true;
  const isCorrect = opt === item.correct_option;

  // reveal
  $$("#quiz-options .option-btn").forEach((b) => {
    b.disabled = true;
    if (b.textContent === item.correct_option) b.classList.add("correct");
  });
  if (!isCorrect) btn.classList.add("wrong");

  if (isCorrect) {
    if (!quiz.everWrong.has(item.id)) {
      // first-attempt correct → count toward mastery
      sendReview(item, true);
    }
    if (item.type === "grammar") {
      speak(item.sentence.replace(/_+/g, item.correct_option));
    }
    quiz.solved += 1;
    quiz.queue.shift(); // remove solved item
    setTimeout(nextStep, 650);
  } else {
    if (!quiz.everWrong.has(item.id)) {
      // 1-session-1-count: only the FIRST wrong hits the DB
      sendReview(item, false);
      quiz.everWrong.add(item.id);
    }
    // requeue this item to the back
    const [cur] = quiz.queue.splice(0, 1);
    quiz.queue.push(cur);
    $("#next-btn").classList.remove("hidden");
  }
}

function nextStep() {
  if (quiz.queue.length === 0) finishQuiz(false);
  else renderCurrent();
}
$("#next-btn").addEventListener("click", nextStep);

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
  else speak(item.sentence.replace(/_+/g, " blank "));
});

// --------------------------------------------------------------------------- //
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// init
showView("dashboard");
