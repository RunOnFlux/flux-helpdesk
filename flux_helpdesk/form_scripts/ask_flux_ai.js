// Installed into Helpdesk as an HD Form Script ("Flux: Ask Flux AI") on every
// migrate. Adds two buttons to the agent's ticket header: a suggested answer
// from the Flux knowledge bot, and a link to the ticket's Discord message.
function setupForm({ doc, call, $dialog, createToast }) {
  const escape = (text) =>
    String(text || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);

  const actions = [
    {
      label: "Ask Flux AI",
      iconLeft: "zap",
      onClick: async () => {
        createToast({ message: "Asking Flux AI…" });
        try {
          const res = await call("flux_helpdesk.ai.suggest_reply", { ticket: doc.name });
          const answer = escape(res.answer || "No answer this time.");
          const sources = (res.sources || [])
            .filter((s) => /^https?:\/\//.test(s.url))
            .map(
              (s) =>
                '<li><a class="underline" target="_blank" rel="noopener" href="' +
                escape(s.url) + '">' + escape(s.title) + "</a></li>"
            )
            .join("");
          $dialog({
            title: "Flux AI suggestion",
            size: "xl",
            html:
              '<div class="text-p-base text-ink-gray-8" style="white-space:pre-line">' +
              answer + "</div>" +
              (sources
                ? '<p class="mt-4 text-sm font-medium text-ink-gray-6">Sources</p>' +
                  '<ul class="mt-1 list-disc pl-5 text-sm text-ink-gray-7">' + sources + "</ul>"
                : "") +
              '<p class="mt-4 text-sm text-ink-gray-5">Check it before you send it. ' +
              "The bot answers from our public docs and can be wrong.</p>",
            actions: [
              {
                label: "Copy answer",
                variant: "solid",
                onClick(close) {
                  navigator.clipboard.writeText(res.answer || "");
                  createToast({ message: "Copied. Paste it into your reply." });
                  close();
                },
              },
            ],
          });
        } catch (e) {
          createToast({
            message: (e && e.messages && e.messages[0]) || "Flux AI could not answer this one.",
          });
        }
      },
    },
  ];

  if (doc.flux_discord_url) {
    actions.push({
      label: "Discord",
      iconLeft: "message-circle",
      onClick: () => window.open(doc.flux_discord_url, "_blank", "noopener"),
    });
  }

  return { actions };
}
