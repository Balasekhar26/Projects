#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const packagePath = path.join(root, "package.json");
const builderPath = path.join(root, "electron-builder.yml");
const envExamplePath = path.join(root, ".env.example");
const docs = [
  "README.md",
  "QUICKSTART.md",
  "SETUP.md",
  "USER_MANUAL.md",
];

let failed = false;

section("ULT Release Check");
const pkg = readJson(packagePath);

check(Boolean(pkg.name), "package name present");
check(Boolean(pkg.version), "package version present");
check(pkg.private === true, "package remains private until release ownership is intentional");
checkScript(pkg, "test");
checkScript(pkg, "typecheck");
checkScript(pkg, "package:windows");
checkFile(builderPath, "electron-builder config");
checkEnvExample();
for (const doc of docs) checkFile(path.join(root, doc), doc);

if (failed) {
  console.log("\nResult: release check needs attention");
  process.exit(1);
}

console.log("\nResult: release check passed");

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    fail(path.relative(root, filePath), error.message);
    return {};
  }
}

function checkScript(pkgJson, scriptName) {
  check(Boolean(pkgJson.scripts?.[scriptName]), `npm script '${scriptName}' present`);
}

function checkFile(filePath, label) {
  check(fs.existsSync(filePath), `${label} present`);
}

function checkEnvExample() {
  const env = fs.existsSync(envExamplePath) ? fs.readFileSync(envExamplePath, "utf8") : "";
  const required = [
    "DEEPL_API_KEY",
    "OPENAI_API_KEY",
    "NVIDIA_NIM_API_KEY",
    "ULT_TRANSLATION_PROVIDER",
    "ONLINE_POLICY",
  ];

  for (const key of required) {
    check(env.includes(key), `.env.example documents ${key}`);
  }
}

function section(label) {
  console.log(`\n${label}`);
}

function check(condition, label) {
  if (condition) {
    console.log(`[ok] ${label}`);
  } else {
    fail(label, "missing or invalid");
  }
}

function fail(label, detail) {
  failed = true;
  console.log(`[fail] ${label}: ${detail}`);
}
