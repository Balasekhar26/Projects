const { normalizeContributions } = require('./src/ai-observer/debug-record.js');

// Test cases
console.log('Test 1: Balanced case');
console.log(normalizeContributions({ system: 2, observer: 1, utterance: 5 }));

console.log('\nTest 2: Degenerate case (system dominates)');
console.log(normalizeContributions({ system: 1e6, observer: 1e-6, utterance: 5 }));

console.log('\nTest 3: Degenerate case (observer dominates)');
console.log(normalizeContributions({ system: 1e-6, observer: 1e6, utterance: 5 }));

console.log('\nTest 4: Absolute void');
console.log(normalizeContributions({ system: 1e-10, observer: 1e-10, utterance: 5 }));

console.log('\nTest 5: Only one decision domain');
console.log(normalizeContributions({ system: 5, utterance: 5 }));

console.log('\nTest 6: Edge case near threshold');
console.log(normalizeContributions({ system: 1e-5, observer: 1e-7, utterance: 5 }));