#!/usr/bin/env node

/**
 * E2E Test Runner
 * Executes all end-to-end system tests
 */

const tests = require("./e2e.test.js");
const performanceTests = require("./performance-benchmark.test.js");

async function runTests() {
  console.log("╔═══════════════════════════════════════════════════════════╗");
  console.log("║         ULT System E2E Test Suite                         ║");
  console.log("╚═══════════════════════════════════════════════════════════╝\n");

  const allTests = { ...tests, ...performanceTests };
  const testNames = Object.keys(allTests);
  const results = [];
  
  console.log(`Running ${testNames.length} tests...\n`);

  for (let i = 0; i < testNames.length; i++) {
    const testName = testNames[i];
    const testFn = tests[testName];
    
    process.stdout.write(`[${i + 1}/${testNames.length}] ${testName}... `);
    
    try {
      const startTime = Date.now();
      const result = await allTests[testName]();
      const duration = Date.now() - startTime;
      
      results.push({
        name: testName,
        ...result,
        duration
      });

      if (result.passed) {
        console.log(`✓ PASS (${duration}ms)`);
      } else {
        console.log(`✗ FAIL (${duration}ms)`);
        if (result.error) {
          console.log(`   Error: ${result.error}`);
        }
      }
    } catch (error) {
      console.log(`✗ ERROR (${error.message})`);
      results.push({
        name: testName,
        passed: false,
        error: error.message,
        duration: 0
      });
    }
  }

  // Summary
  console.log("\n╔═══════════════════════════════════════════════════════════╗");
  console.log("║                      Test Summary                         ║");
  console.log("╚═══════════════════════════════════════════════════════════╝\n");

  const passed = results.filter((r) => r.passed).length;
  const failed = results.filter((r) => !r.passed).length;
  const totalDuration = results.reduce((sum, r) => sum + r.duration, 0);

  console.log(`Total:  ${results.length} tests`);
  console.log(`Passed: ${passed} (${((passed / results.length) * 100).toFixed(1)}%)`);
  console.log(`Failed: ${failed} (${((failed / results.length) * 100).toFixed(1)}%)`);
  console.log(`Duration: ${totalDuration}ms\n`);

  // Detailed results
  if (failed > 0) {
    console.log("Failed Tests:");
    results.filter((r) => !r.passed).forEach((result) => {
      console.log(`  ✗ ${result.name}`);
      if (result.error) {
        console.log(`    ${result.error}`);
      }
    });
    console.log();
  }

  // Device info
  console.log("Detected Configuration:");
  const deviceTest = results.find((r) => r.name === "device-topology");
  if (deviceTest && deviceTest.passed) {
    console.log(`  Input Devices: ${deviceTest.devices.input}`);
    console.log(`  Output Devices: ${deviceTest.devices.output}`);
  }

  console.log();

  // Exit code
  const exitCode = failed > 0 ? 1 : 0;
  console.log(exitCode === 0 ? "✓ All tests passed!" : "✗ Some tests failed");
  process.exit(exitCode);
}

runTests().catch((error) => {
  console.error("Test runner error:", error);
  process.exit(1);
});
