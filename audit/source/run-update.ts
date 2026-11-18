async function runUpdate(ctx, deps = {}) {
  const env = deps.env ?? process.env;
  if (isEphemeralNpx(env)) {
    ctx.ui.notify("You're running via npx, which always fetches the latest — you're already up to date.", "info");
    return;
  }
  ctx.ui.notify("Updating free-pi-cli… (npm install -g free-pi-cli@latest)", "info");
  try {
    const { ok } = await (deps.installLatest ?? defaultInstallLatest)();
    ctx.ui.notify(ok ? "Updated — restart free-pi-cli to use the new version." : "Update failed. Try manually: npm install -g free-pi-cli@latest", ok ? "info" : "error");
  } catch {
    ctx.ui.notify("Update failed. Try manually: npm install -g free-pi-cli@latest", "error");
  }
}

