/* LingoLoop — TTS 텍스트 정규화 유틸 (브라우저 / Node 공용) */
"use strict";

/**
 * 문법 예문을 TTS로 읽기 좋은 문자열로 정규화한다.
 *
 * 괄호 안 번역(예: "(너는 학생이다.)")은 제거하고, ___ 빈칸을 `fill`로 채운 뒤
 * 연속 공백을 하나로 줄인다. 즉 대상 언어(중국어) 부분만 남긴다.
 *
 * @param {string} sentence - 번역 괄호와 ___ 빈칸이 섞일 수 있는 원본 예문.
 * @param {string} fill - 빈칸을 대체할 문자열(정답, 또는 짧은 쉼을 뜻하는 "，").
 * @returns {string} 정규화된 문자열.
 */
function cleanSentenceForTTS(sentence, fill) {
  return String(sentence)
    .replace(/[（(][^）)]*[）)]/g, " ") // 괄호 안 번역 제거
    .replace(/_+/g, fill)              // 빈칸 → 정답 또는 쉼
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * 발음 표기를 화면에 보여주기 좋은 형태로 정리한다.
 *
 * LLM이 IPA 관습(예: "/wɔ/")으로 슬래시를 씌워 보내는 경우를 방어적으로
 * 걷어낸다. 표준 병음(예: "nǐ hǎo")은 슬래시가 없으므로 그대로 통과한다.
 *
 * @param {string} raw - 원본 발음 문자열(양끝에 "/"가 붙어있을 수 있음).
 * @returns {string} 슬래시와 불필요한 공백이 제거된 문자열.
 */
function cleanPronunciation(raw) {
  return String(raw || "")
    .trim()
    .replace(/^\/+/, "")   // 앞쪽 슬래시 제거
    .replace(/\/+$/, "")   // 뒤쪽 슬래시 제거
    .trim();
}

// 브라우저에서는 전역 함수, Node(테스트)에서는 module.exports 로 노출.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { cleanSentenceForTTS, cleanPronunciation };
}
