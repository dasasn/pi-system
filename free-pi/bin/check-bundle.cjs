// Syntax check for the patched ESM bundle.
// `node --check <file>` is unreliable here: for a large ESM file it reports a bogus
// "Unexpected token '}'" depending on how the file was written (mtime/mode/cache state).
// Parsing the source explicitly with the V8 parser through vm.SourceTextModule is stable.
const fs = require("node:fs");
const vm = require("node:vm");
const file = process.argv[2];
if (!file) {
  console.error("usage: check-bundle.cjs <bundle.js>");
  process.exit(2);
}
const src = fs.readFileSync(file, "utf8");
try {
  // eslint-disable-next-line no-new
  new vm.SourceTextModule(src, { identifier: file });
  process.exit(0);
} catch (err) {
  console.error(`${file}: ${err && err.message}`);
  process.exit(1);
}
