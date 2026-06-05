function diffEvents(left, right) {
  return {
    id: [left.id, right.id],
    normalizedTimeDelta: right.normalizedTime - left.normalizedTime,
    dominantDomainChanged: left.dominantDomain !== right.dominantDomain,
    contributionDelta: diffMap(left.contributions, right.contributions),
    causalityChanged:
      JSON.stringify(left.causalityKey) !== JSON.stringify(right.causalityKey),
    flags: {
      a: left.flags || [],
      b: right.flags || [],
    },
  };
}

function diffMap(left = {}, right = {}) {
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  const output = {};

  for (const key of keys) {
    output[key] = (right[key] || 0) - (left[key] || 0);
  }

  return output;
}

module.exports = {
  diffEvents,
  diffMap,
};
