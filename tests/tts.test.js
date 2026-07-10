/* cleanSentenceForTTS 단위 테스트 (중국어 예문).
 *
 *   node --test tests/tts.test.js
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { cleanSentenceForTTS, cleanPronunciation } = require("../src/frontend/tts-util.js");

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

test("cleanPronunciation: 양쪽 슬래시(IPA 관습)를 제거한다", () => {
  assert.equal(cleanPronunciation("/wɔ/"), "wɔ");
});

test("cleanPronunciation: 슬래시가 없는 표준 병음은 그대로 둔다", () => {
  assert.equal(cleanPronunciation("nǐ hǎo"), "nǐ hǎo");
});

test("cleanPronunciation: 앞뒤 공백과 짝 없는 슬래시도 정리한다", () => {
  assert.equal(cleanPronunciation("  /xièxie "), "xièxie");
});

test("cleanPronunciation: 값이 없으면 빈 문자열을 반환한다", () => {
  assert.equal(cleanPronunciation(undefined), "");
  assert.equal(cleanPronunciation(""), "");
});
