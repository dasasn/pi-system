function readAutoUpdate(configPath) {
  try {
    const parsed = JSON.parse(readFileSync2(configPath, "utf8"));
    const autoUpdate = parsed?.autoUpdate;
    return autoUpdate !== false;
  } catch {
    return true;
  }
}
