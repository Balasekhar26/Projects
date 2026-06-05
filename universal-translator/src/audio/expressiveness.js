function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function describeExpressiveness({ analysis, transcript, targetLanguage }) {
  const normalizedTranscript = typeof transcript === "string" ? transcript.trim() : "";
  const safeAnalysis =
    analysis && typeof analysis === "object"
      ? {
          rms: Number(analysis.rms) || 0,
          peak: Number(analysis.peak) || 0,
          zeroCrossingRate: Number(analysis.zeroCrossingRate) || 0,
        }
      : {
          rms: 0,
          peak: 0,
          zeroCrossingRate: 0,
        };

  const energy = clamp(safeAnalysis.rms, 0, 1);
  const peak = clamp(safeAnalysis.peak, 0, 1);
  const zeroCrossingRate = clamp(safeAnalysis.zeroCrossingRate, 0, 1);
  const emphasis = /[!?]/.test(normalizedTranscript);

  const toneHints = [];
  if (energy < 0.03) {
    toneHints.push("soft", "calm", "gentle");
  } else if (energy < 0.08) {
    toneHints.push("steady", "conversational");
  } else if (energy < 0.16) {
    toneHints.push("engaged", "natural");
  } else {
    toneHints.push("animated", "energetic");
  }

  if (peak > 0.8 || emphasis) {
    toneHints.push("emphatic");
  }

  if (zeroCrossingRate > 0.14) {
    toneHints.push("bright");
  } else if (zeroCrossingRate < 0.06) {
    toneHints.push("grounded");
  }

  const uniqueHints = [...new Set(toneHints)];
  const languageHint = typeof targetLanguage === "string" && targetLanguage.trim()
    ? `Speak in ${targetLanguage}.`
    : "";

  return [
    languageHint,
    "Preserve the speaker's likely emotional intent and delivery style from the source audio.",
    `Keep the voice ${uniqueHints.join(", ")}.`,
    "Do not sound robotic or overly theatrical.",
  ]
    .filter(Boolean)
    .join(" ");
}

module.exports = {
  describeExpressiveness,
};
