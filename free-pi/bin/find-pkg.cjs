// Locate a free-pi install (node-only). Usage: node find-pkg.cjs
// Prints the highest-version package dir that contains dist/.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const PREFIX = process.env.PREFIX || "/data/data/com.termux/files/usr";
const home = os.homedir();

const dirs = [
  ...(() => {
    try {
      const np = require("node:child_process")
        .execFileSync("npm", ["config", "get", "prefix"], { encoding: "utf8" })
        .trim();
      return [np + "/lib/node_modules/free-pi-cli"];
    } catch {
      return [];
    }
  })(),
  PREFIX + "/lib/node_modules/free-pi-cli",
  home + "/.npm-global/lib/node_modules/free-pi-cli",
  ...(() => {
    const out = [];
    try {
      const root = home + "/.npm/_npx";
      for (const e of fs.readdirSync(root)) {
        const d = path.join(root, e, "node_modules/free-pi-cli");
        if (fs.existsSync(path.join(d, "dist"))) out.push(d);
      }
    } catch {}
    return out;
  })(),
].filter((d) => fs.existsSync(path.join(d, "dist")));

function ver(d) {
  try {
    return JSON.parse(fs.readFileSync(path.join(d, "package.json"), "utf8")).version || "0";
  } catch {
    return "0";
  }
}

if (!dirs.length) process.exit(1);
dirs.sort((a, b) => (ver(a) < ver(b) ? 1 : -1));
process.stdout.write(dirs[0] + "\n");