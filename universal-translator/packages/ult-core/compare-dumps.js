const fs = require('fs');

const dump1 = JSON.parse(fs.readFileSync('real-session-evidence/dumps/9569d391-590d-4a9d-97e2-4485979f46ca_full_1776343113922.json'));
const dump2 = JSON.parse(fs.readFileSync('real-session-evidence/dumps/34ea0a0e-884f-4e8f-b532-a3812ab27e9f_full_1776343159493.json'));

console.log('=== RUN 1 (9569d391...) ===');
dump1.events.slice(0, 3).forEach(e => {
  console.log(`Event ${e.sequence}: ${e.type} at ${e.normalizedTime}ms (raw: ${e.rawTime})`);
});

console.log('\n=== RUN 2 (34ea0a0e...) ===');
dump2.events.slice(0, 3).forEach(e => {
  console.log(`Event ${e.sequence}: ${e.type} at ${e.normalizedTime}ms (raw: ${e.rawTime})`);
});

console.log('\n=== TIME DIFFS ===');
for (let i = 0; i < Math.min(dump1.events.length, dump2.events.length); i++) {
  const e1 = dump1.events[i];
  const e2 = dump2.events[i];
  const timeDiff = e1.normalizedTime - e2.normalizedTime;
  console.log(`Event ${i}: ${timeDiff}ms diff`);
}