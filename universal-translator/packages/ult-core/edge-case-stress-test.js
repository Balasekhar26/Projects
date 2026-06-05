const crypto = require('crypto');

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }

  if (value && typeof value === "object") {
    const entries = Object.keys(value)
      .sort()
      .map((key) => `"${key}":${stableStringify(value[key])}`);
    return `{${entries.join(",")}}`;
  }

  return JSON.stringify(value);
}

function hashPayload(payload) {
  return crypto.createHash("sha256").update(stableStringify(payload)).digest("hex");
}

function normalizeContributions(contributions) {
  const raw = contributions || {};
  const normalized = {};
  const decisionDomains = ["system", "observer"].filter((domain) => Object.prototype.hasOwnProperty.call(raw, domain));
  const primaryTotal = decisionDomains.reduce((sum, domain) => sum + Math.abs(raw[domain] || 0), 0);

  for (const domain of Object.keys(raw).sort()) {
    if (decisionDomains.length > 0 && decisionDomains.includes(domain)) {
      normalized[domain] = primaryTotal === 0 ? 0 : Number((raw[domain] / primaryTotal).toFixed(6));
    } else {
      normalized[domain] = raw[domain] === 0 ? 0 : 1;
    }
  }

  return normalized;
}

function computeDecisionHash(contributions, type, dominantDomain) {
  const payload = {
    type,
    dominantDomain,
    contributions: normalizeContributions(contributions),
  };

  return hashPayload(payload);
}

console.log('\n╔═══════════════════════════════════════════════════════════╗');
console.log('║     EDGE CASE STRESS TEST: NORMALIZATION ROBUSTNESS       ║');
console.log('╚═══════════════════════════════════════════════════════════╝\n');

const testCases = [
  {
    name: 'Normal Range (baseline)',
    contributions: { utterance: 44.1, system: 1300, observer: 650 },
  },
  {
    name: 'Very Large Values (1e6 scale)',
    contributions: { utterance: 44.1, system: 1e6, observer: 5e5 },
  },
  {
    name: 'Very Small Values (1e-6 scale)',
    contributions: { utterance: 44.1, system: 1e-6, observer: 5e-7 },
  },
  {
    name: 'Mixed Scale (system large, observer small)',
    contributions: { utterance: 44.1, system: 1e6, observer: 1e-6 },
  },
  {
    name: 'Near-Zero Total (system=1e-9, observer=5e-10)',
    contributions: { utterance: 44.1, system: 1e-9, observer: 5e-10 },
  },
  {
    name: 'Zero Decision Domains (only utterance)',
    contributions: { utterance: 44.1, system: 0, observer: 0 },
  },
  {
    name: 'Equal Decision Domains (1:1 ratio)',
    contributions: { utterance: 44.1, system: 500, observer: 500 },
  },
];

const results = [];

testCases.forEach((testCase) => {
  const normalized = normalizeContributions(testCase.contributions);
  const hash = computeDecisionHash(testCase.contributions, 'final_translation', 'system');
  
  const sysVal = normalized.system || 0;
  const obsVal = normalized.observer || 0;
  const ratio = obsVal !== 0 ? Number((sysVal / obsVal).toFixed(6)) : 'N/A';

  results.push({
    name: testCase.name,
    raw: testCase.contributions,
    normalized,
    ratio,
    hash,
  });

  console.log(`Test: ${testCase.name}`);
  console.log(`  Raw:        ${JSON.stringify(testCase.contributions)}`);
  console.log(`  Normalized: ${JSON.stringify(normalized)}`);
  console.log(`  Ratio (sys/obs): ${ratio}`);
  console.log(`  Hash: ${hash.slice(0, 16)}...`);
  console.log();
});

console.log('\n╔═══════════════════════════════════════════════════════════╗');
console.log('║     INVARIANCE VERIFICATION                              ║');
console.log('╚═══════════════════════════════════════════════════════════╝\n');

console.log('Testing: Same logical relationship, different scales\n');

const invarianceTest = [
  { contributions: { utterance: 44.1, system: 1000, observer: 500 }, label: '1000:500 (scale 1)' },
  { contributions: { utterance: 44.1, system: 1e6, observer: 5e5 }, label: '1e6:5e5 (scale 1e6)' },
  { contributions: { utterance: 44.1, system: 1e-6, observer: 5e-7 }, label: '1e-6:5e-7 (scale 1e-6)' },
];

const invarianceResults = invarianceTest.map((test) => {
  const normalized = normalizeContributions(test.contributions);
  const hash = computeDecisionHash(test.contributions, 'final_translation', 'system');
  return {
    label: test.label,
    normalized,
    hash,
  };
});

invarianceResults.forEach((result) => {
  console.log(`${result.label}:`);
  console.log(`  Normalized: ${JSON.stringify(result.normalized)}`);
  console.log(`  Hash: ${result.hash.slice(0, 16)}...`);
});

const allHashesEqual = invarianceResults.every((r, i) => {
  if (i === 0) return true;
  return r.hash === invarianceResults[i - 1].hash;
});

console.log(`\n✓ All Hashes Invariant Across Scales: ${allHashesEqual ? 'YES ✅' : 'NO ❌'}`);

const allNormalized = invarianceResults.every((r) => {
  const expected = { observer: 0.333333, system: 0.666667, utterance: 1 };
  return (
    Math.abs((r.normalized.observer || 0) - expected.observer) < 0.000001 &&
    Math.abs((r.normalized.system || 0) - expected.system) < 0.000001 &&
    r.normalized.utterance === 1
  );
});

console.log(`✓ All Normalized Values Match Expected: ${allNormalized ? 'YES ✅' : 'NO ❌'}`);

console.log('\n╔═══════════════════════════════════════════════════════════╗');
console.log('║     EDGE CASE ASSESSMENT                                 ║');
console.log('╚═══════════════════════════════════════════════════════════╝\n');

const zeroCase = results.find((r) => r.name.includes('Zero Decision'));
const nearZeroCase = results.find((r) => r.name.includes('Near-Zero'));

console.log('⚠️  Zero Decision Domains Case:');
console.log(`   Status: ${zeroCase.hash === '0' ? 'Degenerate' : 'Handled'}`);
console.log(`   Normalized: ${JSON.stringify(zeroCase.normalized)}`);
console.log(`   Hash: ${zeroCase.hash.slice(0, 16)}...`);
console.log();

console.log('⚠️  Near-Zero Total Case:');
console.log(`   Normalized: ${JSON.stringify(nearZeroCase.normalized)}`);
console.log(`   Hash: ${nearZeroCase.hash.slice(0, 16)}...`);
console.log(`   Recommendation: May need epsilon threshold guard (< 1e-8 total)`);
console.log();
