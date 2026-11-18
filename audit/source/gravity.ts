function startGravityPixel(jwt, storageDir, env = process.env, load = () => import("./index-xkn61g24.js")) {
  return;
  if (env.FREEPI_NO_GRAVITY_PIXEL === "1")
    return;
  const userId = userIdFromJwt(jwt);
  if (!userId)
    return;
  const userHash = createHash("sha256").update(userId).digest("hex");
  let sdk;
  let pixel;
  (async () => {
    try {
      sdk = await load();
      const p = sdk.gravityPixel({ pixelId: GRAVITY_PIXEL_ID, appName: "free-pi", storageDir });
      pixel = p;
      const stopWatching = dropPixelSignalHandlers();
      try {
        await p.start();
      } finally {
        stopWatching();
      }
    } catch {
      pixel = undefined;
    }
  })();
  const fallbackSessionId = randomUUID();
  return () => {
    try {
      if (!sdk)
        return;
      const sessionId = pixel?.getSessionId();
      const ctx = sdk.gravityContext({
        sessionId: sessionId || fallbackSessionId,
        user: sessionId && pixel ? { userId: userHash, gruid: pixel.getVisitorId(), grclid: pixel.getClickId(), graid: pixel.getGraid() } : { userId: userHash }
      });
      const encoded = Buffer.from(JSON.stringify(ctx)).toString("base64url");
      return encoded.length <= GRAVITY_CONTEXT_MAX_BYTES ? encoded : undefined;
    } catch {
      return;
    }
  };
}
