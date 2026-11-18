async function relaunchViaNpx(latest, deps) {
  const { env } = deps;
  if ("FREEPI_NO_AUTO_UPDATE" in env || !deps.autoUpdateEnabled())
    return;
  if (env.FREEPI_AUTO_UPDATED)
    return;
  const win = deps.platform === "win32";
  if (!latest || !SEMVER.test(latest))
    return;
  const target = latest;
  const nodeDir = dirname13(deps.execPath);
  const npxCli = win ? join13(nodeDir, "node_modules", "npm", "bin", "npx-cli.js") : join13(dirname13(nodeDir), "lib", "node_modules", "npm", "bin", "npx-cli.js");
  const exists = deps.exists ?? existsSync6;
  const distroNpxCli = "/usr/share/nodejs/npm/bin/npx-cli.js";
  const healthy = (cli) => {
    const root = join13(dirname13(cli), "..");
    return exists(join13(root, "package.json")) && exists(join13(root, "lib", "cli.js"));
  };
  let npxCliPath = npxCli;
  if (!exists(npxCli)) {
    if (!win && deps.execPath === "/usr/bin/node" && exists(distroNpxCli))
      npxCliPath = distroNpxCli;
    else
      return;
  }
  if (!healthy(npxCliPath))
    return;
  const childEnv = sanitizedEnv(env, nodeDir, deps.cwd, deps.homedir, win);
  const readyDir = mkdtempSync2(join13(tmpdir2(), "free-pi-relaunch-"));
  const readyFile = join13(readyDir, "started");
  try {
    deps.log(`Updating free-pi to ${target}…`);
    return await new Promise((resolve) => {
      let child;
      try {
        child = deps.spawn(deps.execPath, [npxCliPath, "--yes", `free-pi-cli@${target}`, ...deps.argv], {
          stdio: "inherit",
          cwd: deps.homedir,
          env: { ...childEnv, FREEPI_AUTO_UPDATED: target, FREEPI_RELAUNCH_READY: readyFile, FREEPI_RELAUNCH_CWD: deps.cwd },
          shell: false
        });
      } catch {
        resolve(undefined);
        return;
      }
      const handlers = win ? [] : [
        ["SIGINT", () => {}],
        ["SIGTERM", () => void child.kill("SIGTERM")],
        ["SIGHUP", () => void child.kill("SIGTERM")]
      ];
      for (const [sig, cb] of handlers)
        deps.proc.on(sig, cb);
      const done = (code) => {
        for (const [sig, cb] of handlers)
          deps.proc.off(sig, cb);
        resolve(code);
      };
      child.on("error", () => done(undefined));
      child.on("exit", (code, signal) => {
        const exitCode = code ?? 128 + (signal ? osConstants.signals[signal] ?? 0 : 0);
        const cancelled = signal === "SIGINT" || signal === "SIGTERM" || signal === "SIGHUP" || exitCode === 130 || exitCode === 143 || exitCode === 129;
        done(exitCode !== 0 && !cancelled && !existsSync6(readyFile) ? undefined : exitCode);
      });
    });
  } finally {
    rmSync2(readyDir, { recursive: true, force: true });
  }
}
