// Syntax check for every JS file and every Python module. Exit 1 on the first failure list.
import { execFileSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join } from "node:path";

const skip = new Set(["node_modules", ".git", "test-results", "playwright-report", "__pycache__"]);
function walk(dir, ext, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (skip.has(entry.name) || entry.name.startsWith(".")) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walk(path, ext, out);
    else if (entry.name.endsWith(ext)) out.push(path);
  }
  return out;
}

const failures = [];
for (const file of [...walk("frontend", ".js"), ...walk("tests", ".js"), ...walk("scripts", ".mjs")]) {
  try {
    execFileSync(process.execPath, ["--check", file], { stdio: "pipe" });
  } catch (err) {
    failures.push(`${file}\n${err.stderr}`);
  }
}
try {
  execFileSync("python3", ["-m", "py_compile", ...walk("backend", ".py")], { stdio: "pipe" });
} catch (err) {
  failures.push(`backend\n${err.stderr}`);
}
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log("check: ok");
