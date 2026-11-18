async function checkClientVersion(baseUrl, cliVersion, fetchImpl = fetch, jwt) {
  try {
    const res = await fetchImpl(new URL("/client-version", baseUrl), {
      signal: AbortSignal.timeout(3000),
      headers: jwt ? { authorization: `Bearer ${jwt}`, [COST_EXP_HEADER]: "1" } : undefined
    });
    if (!res.ok)
      return { action: "ok" };
    const parsed = ClientVersionResponseSchema.safeParse(await res.json());
    if (!parsed.success)
      return { action: "ok" };
    const { min, latest, model, models, notice, fusion, experiments, cost_experiment } = parsed.data;
    const extra = {};
    if (model !== undefined)
      extra.model = model;
    if (models !== undefined)
      extra.models = models;
    if (notice !== undefined)
      extra.notice = notice;
    if (fusion !== undefined)
      extra.fusion = fusion;
    if (cost_experiment !== undefined)
      extra.costArm = cost_experiment.arm;
    if (experiments !== undefined)
      extra.experiments = experiments;
    return { action: "ok", ...extra };
  } catch {
    return { action: "ok" };
  }
}
