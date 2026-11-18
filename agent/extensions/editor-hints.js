// Workspace behaviour hints. Added as a prompt section (not as a full system prompt
// replacement) so pi keeps diffing structured sections and the operator anchor stays last.
const WORKSPACE = `- Do what the request asks, exactly as asked. Keep replies brief and concrete.
- Do not add warnings, policy notes, or alternatives nobody requested.
- Tools are available and expected to be used; this workspace is the owner's own machine.
- Finish multi-step work end to end instead of describing how it could be done.
- Write results to disk instead of pasting them into chat.`;

export default function (pi) {
	pi.on("before_agent_start", async (event) => {
		const o = event && event.systemPromptOptions;
		if (!o) return;
		const sections = { ...(o.sections || {}) };
		sections.workspace_hints = WORKSPACE;
		o.sections = sections;
		return { systemPromptOptions: o };
	});
}
