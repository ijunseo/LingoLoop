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

// 브라우저에서는 전역 함수, Node(테스트)에서는 module.exports 로 노출.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { cleanSentenceForTTS };
}
