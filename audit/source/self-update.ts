async function maybeSelfUpdate(action, latest, deps) {
  const fallback = () => action === "notice" ? "notice" : "blocked";
  try {
    if ("FREEPI_NO_AUTO_UPDATE" in deps.env || !deps.autoUpdateEnabled())
      return fallback();
    if (deps.env.npm_config_user_agent || deps.env.npm_lifecycle_event === "npx")
      return fallback();
    const root = deps.spawn("npm", ["root", "-g"], { timeout: NPM_ROOT_TIMEOUT_MS });
    if (root.error || root.status !== 0)
      return fallback();
    const globalRoot = root.stdout.trim();
    const isGlobalInstall = deps.cliRealpath === globalRoot || deps.cliRealpath.startsWith(globalRoot + path.sep);
    if (!isGlobalInstall)
      return fallback();
    const install = deps.spawn("npm", ["install", "-g", "free-pi-cli@latest"], {
      timeout: NPM_INSTALL_TIMEOUT_MS
    });
    if (install.error || install.status !== 0)
      return fallback();
    if (action === "notice") {
      deps.log(`updated to ${latest}; applies next launch`);
      return "updated-continue";
    }
    deps.log(`updated to ${latest} — re-run free-pi-cli`);
    return "updated-exit";
  } catch {
    return fallback();
  }
}
