/* NEXUS shared voice utilities — natural-voice pick + speech-safe text.
   Loaded by index.html, holo.html and chat.html; exposes window.NEXUS_VOICE. */
(function (global) {
  "use strict";

  /* Preferred clear voices: Windows natural voices first, then Google en-US. */
  function pickVoice() {
    if (!("speechSynthesis" in global)) return null;
    const vs = global.speechSynthesis.getVoices() || [];
    const score = v => {
      const n = (v.name || "").toLowerCase();
      if (/natural|online/.test(n) && /en[-_ ]us|english/.test(n + " " + v.lang)) return 0;
      if (/aria|guy|emma|jenny/.test(n)) return 1;
      if (v.lang === "en-US" && /google/.test(n)) return 2;
      if (v.lang === "en-US") return 3;
      if (/^en/.test(v.lang)) return 4;
      return 9;
    };
    return vs.slice().sort((a, b) => score(a) - score(b))[0] || null;
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

  global.NEXUS_VOICE = { pickVoice: pickVoice, speakable: speakable };
})(window);
