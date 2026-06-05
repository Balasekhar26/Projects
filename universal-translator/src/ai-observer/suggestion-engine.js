class SuggestionEngine {
  constructor() {
    this.suggestionQueue = [];
    this.appliedSuggestions = [];
    this.rejectedSuggestions = [];
  }

  generateSuggestions(anomalies) {
    const suggestions = [];
    const seen = new Set();

    for (const issue of anomalies) {
      if (!issue.suggestedFix) continue;

      const fixKey = `${issue.suggestedFix.parameter}:${issue.suggestedFix.direction}`;
      if (seen.has(fixKey)) continue;
      seen.add(fixKey);

      const suggestion = {
        id: `sug-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
        createdAt: Date.now(),
        issueType: issue.type,
        severity: issue.severity,
        parameter: issue.suggestedFix.parameter,
        direction: issue.suggestedFix.direction,
        reason: issue.suggestedFix.reason,
        rootCause: issue.rootCauseHypothesis,
        confidence: this._computeConfidence(issue),
        status: "pending",
        estimatedImpact: this._estimateImpact(issue),
      };

      suggestions.push(suggestion);
    }

    suggestions.sort((a, b) => (b.confidence * this._severityScore(b.severity)) - (a.confidence * this._severityScore(a.severity)));
    return suggestions.slice(0, 5);
  }

  enqueueSuggestion(suggestion) {
    this.suggestionQueue.push({
      ...suggestion,
      enqueuedAt: Date.now(),
    });
  }

  approveSuggestion(suggestionId, approvalReason = "") {
    const idx = this.suggestionQueue.findIndex((s) => s.id === suggestionId);
    if (idx < 0) return null;

    const suggestion = this.suggestionQueue.splice(idx, 1)[0];
    suggestion.status = "approved";
    suggestion.approvedAt = Date.now();
    suggestion.approvalReason = approvalReason;
    this.appliedSuggestions.push(suggestion);
    return suggestion;
  }

  rejectSuggestion(suggestionId, rejectionReason = "") {
    const idx = this.suggestionQueue.findIndex((s) => s.id === suggestionId);
    if (idx < 0) return null;

    const suggestion = this.suggestionQueue.splice(idx, 1)[0];
    suggestion.status = "rejected";
    suggestion.rejectedAt = Date.now();
    suggestion.rejectionReason = rejectionReason;
    this.rejectedSuggestions.push(suggestion);
    return suggestion;
  }

  getPendingSuggestions() {
    return this.suggestionQueue.filter((s) => s.status === "pending");
  }

  getAppliedSuggestions() {
    return this.appliedSuggestions;
  }

  getRejectedSuggestions() {
    return this.rejectedSuggestions;
  }

  formatSuggestionReport() {
    const pending = this.getPendingSuggestions();
    if (pending.length === 0) {
      return "No pending suggestions. System appears healthy.";
    }

    let report = "=== AI OBSERVER SUGGESTIONS ===\n\n";

    for (let i = 0; i < pending.length; i++) {
      const sug = pending[i];
      report += `[${i + 1}] ${sug.parameter} (${sug.direction})\n`;
      report += `    Issue: ${sug.issueType}\n`;
      report += `    Severity: ${sug.severity}\n`;
      report += `    Confidence: ${(sug.confidence * 100).toFixed(0)}%\n`;
      report += `    Reason: ${sug.reason}\n`;
      report += `    Root Cause: ${sug.rootCause}\n`;
      report += `    Estimated Impact: ${sug.estimatedImpact}\n`;
      report += `    ID: ${sug.id}\n\n`;
    }

    report += `\nTotal Pending: ${pending.length}`;
    report += `\nApplied: ${this.appliedSuggestions.length}`;
    report += `\nRejected: ${this.rejectedSuggestions.length}`;

    return report;
  }

  _computeConfidence(issue) {
    const baseConfidence = {
      "revision-oscillation": 0.85,
      "latency-spike-cluster": 0.7,
      "silence-gaps": 0.65,
      "confidence-drop": 0.4,
      "version-starvation": 0.75,
      "playback-blocked-excessively": 0.8,
      "stability-gate-too-strict": 0.7,
    };

    return (baseConfidence[issue.type] || 0.5) * (issue.severity === "high" ? 1.0 : issue.severity === "medium" ? 0.85 : 0.7);
  }

  _estimateImpact(issue) {
    if (issue.type === "revision-oscillation") {
      return "Reduce audio jitter and speaking hesitation artifacts";
    }
    if (issue.type === "latency-spike-cluster") {
      return "Prevent queue overloading and allow graceful degradation";
    }
    if (issue.type === "silence-gaps") {
      return "Reduce silence between phrases and improve continuity";
    }
    if (issue.type === "version-starvation") {
      return "Prevent indefinite waiting; force closure of older utterances";
    }
    if (issue.type === "playback-blocked-excessively") {
      return "Increase speech fluency by reducing overly conservative gating";
    }
    if (issue.type === "stability-gate-too-strict") {
      return "Allow earlier utterance playback without waiting for perfect stability";
    }
    return "Improve system behavior";
  }

  _severityScore(severity) {
    return severity === "high" ? 3 : severity === "medium" ? 2 : 1;
  }
}

module.exports = {
  SuggestionEngine,
};
