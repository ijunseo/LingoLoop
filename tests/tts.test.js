/* cleanSentenceForTTS 단위 테스트 (중국어 예문).
 *
 *   node --test tests/tts.test.js
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { cleanSentenceForTTS } = require("../src/frontend/tts-util.js");

test("괄호 안 번역을 제거하고 빈칸을 쉼(，)으로 채운다", () => {
  assert.equal(
    cleanSentenceForTTS("你 ___ 学生。(너는 학생이다.)", "，"),
    "你 ， 学生。",
  );
});

test("빈칸을 정답으로 채운다", () => {
  assert.equal(
    cleanSentenceForTTS("你 ___ 学生。(너는 학생이다.)", "是"),
    "你 是 学生。",
  );
});

test("문두 빈칸과 전각 괄호（）도 처리한다", () => {
  assert.equal(
    cleanSentenceForTTS("___ 我钱！（나한테 돈 줘!）", "给"),
    "给 我钱！",
  );
});

test("괄호가 없고 빈칸만 있어도 동작한다", () => {
  assert.equal(cleanSentenceForTTS("我 ___ 唱！", "来"), "我 来 唱！");
});

test("연속 밑줄(_____)도 하나로 취급한다", () => {
  assert.equal(cleanSentenceForTTS("懂 _____ ！", "了"), "懂 了 ！");
});
