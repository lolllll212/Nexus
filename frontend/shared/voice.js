/* NEXUS shared voice utilities — Indian-English voice pick + speech-safe text.
   Loaded by index.html, holo.html and chat.html; exposes window.NEXUS_VOICE. */
(function (global) {
  "use strict";

  var LANGUAGE = "en-IN";

  function normalizeLang(value) {
    return String(value || "").replace("_", "-").toLowerCase();
  }

  /* Prefer a real Indian-English voice, then other clear English voices. */
  function pickVoice() {
    if (!("speechSynthesis" in global)) return null;
    const vs = global.speechSynthesis.getVoices() || [];
    const score = v => {
      const n = (v.name || "").toLowerCase();
      const lang = normalizeLang(v.lang);
      const natural = /natural|neural|online/.test(n);
      const indianName = /heera|ravi|priya|neerja|prabhat|kajal|india|indian/.test(n);
      if (lang === "en-in" && natural) return 0;
      if (lang === "en-in" && indianName) return 1;
      if (lang === "en-in") return 2;
      if (indianName && /^en/.test(lang)) return 3;
      if (lang === "en-gb" && natural) return 4;
      if (lang === "en-us" && natural) return 5;
      if (/aria|guy|emma|jenny/.test(n)) return 6;
      if (lang === "en-us" && /google/.test(n)) return 7;
      if (/^en/.test(lang)) return 8;
      return 99;
    };
    return vs.slice().sort((a, b) => score(a) - score(b))[0] || null;
  }

  function recognitionLanguage() {
    return LANGUAGE;
  }

  /* Strip markdown/table noise so the voice reads clean sentences. */
  function speakable(text) {
    return String(text || "")
      .replace(/```[\s\S]*?```/g, " code block ")
      .replace(/^\s*FINAL ANSWER:\s*/i, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/https?:\/\/\S+/g, " a link ")
      .replace(/[|#>~_*]/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim()
      .slice(0, 420);
  }

  global.NEXUS_VOICE = {
    LANGUAGE: LANGUAGE,
    pickVoice: pickVoice,
    recognitionLanguage: recognitionLanguage,
    speakable: speakable
  };
})(window);
