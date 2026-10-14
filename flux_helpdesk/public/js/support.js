// /support: ask the Flux knowledge bot first, then open a ticket with the
// question and the answer attached. Plain JS, no build step.
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const state = { question: "", product: "", answer: "", sources: [] };

  async function api(method, body) {
    const headers = { "Content-Type": "application/json", Accept: "application/json" };
    if (csrf) headers["X-Frappe-CSRF-Token"] = csrf;
    const res = await fetch("/api/method/" + method, {
      method: "POST",
      headers,
      credentials: "same-origin",
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(serverMessage(data) || "Something went wrong. Please try again.");
    return data.message;
  }

  function serverMessage(data) {
    try {
      const messages = JSON.parse(data._server_messages || "[]");
      if (messages.length) return JSON.parse(messages[0]).message;
    } catch (e) {
      /* fall through */
    }
    return data.exception ? String(data.exception).split(":").slice(-1)[0].trim() : "";
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  // The bot answers in light Markdown. Render paragraphs and lists as text
  // nodes only; nothing from the answer is ever parsed as HTML.
  function renderAnswer(container, text) {
    container.textContent = "";
    const blocks = String(text).trim().split(/\n{2,}/);
    for (const block of blocks) {
      const lines = block.split("\n");
      const isList = lines.every((l) => /^\s*([-*•]|\d+[.)])\s+/.test(l));
      if (isList) {
        const ordered = /^\s*\d/.test(lines[0]);
        const list = document.createElement(ordered ? "ol" : "ul");
        for (const line of lines) {
          const li = document.createElement("li");
          li.textContent = line.replace(/^\s*([-*•]|\d+[.)])\s+/, "").replace(/\*\*/g, "");
          list.appendChild(li);
        }
        container.appendChild(list);
      } else {
        const p = document.createElement("p");
        p.textContent = block.replace(/\*\*/g, "");
        container.appendChild(p);
      }
    }
  }

  function renderSources(list, sources) {
    list.textContent = "";
    for (const source of sources) {
      if (!/^https?:\/\//.test(source.url)) continue;
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = source.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = source.title;
      li.appendChild(a);
      list.appendChild(li);
    }
    list.hidden = !list.children.length;
  }

  // Product chips behave like a single-choice toggle group.
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const pressed = chip.getAttribute("aria-pressed") === "true";
      document.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
      chip.setAttribute("aria-pressed", pressed ? "false" : "true");
      state.product = pressed ? "" : chip.dataset.product;
    });
  });

  const askForm = $("ask-form");
  if (askForm) {
    const input = $("ask-input");
    const params = new URLSearchParams(location.search);
    if (params.get("q")) input.value = params.get("q").slice(0, 1000);

    askForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const question = input.value.trim();
      if (question.length < 3) {
        input.focus();
        return;
      }
      state.question = question;
      const submit = $("ask-submit");
      const section = $("answer");
      section.hidden = false;
      $("answer-meta").textContent = "thinking…";
      $("answer-body").textContent = "";
      $("answer-sources").hidden = true;
      $("answer-actions").hidden = true;
      $("ticket-form").hidden = true;
      submit.disabled = true;
      section.scrollIntoView({ behavior: "smooth", block: "start" });

      try {
        const result = await api("flux_helpdesk.ai.ask", { question, product: state.product || null });
        state.answer = result.answer || "";
        state.sources = result.sources || [];
        renderAnswer($("answer-body"), state.answer || "I couldn't find an answer to that in our docs.");
        renderSources($("answer-sources"), state.sources);
        $("answer-meta").textContent = state.sources.length
          ? "answered from " + state.sources.length + " help article" + (state.sources.length > 1 ? "s" : "")
          : "";
      } catch (error) {
        $("answer-meta").textContent = "";
        renderAnswer($("answer-body"), error.message);
      } finally {
        submit.disabled = false;
        $("answer-actions").hidden = false;
      }
    });
  }

  const yes = $("answer-yes");
  if (yes) {
    yes.addEventListener("click", () => {
      $("answer-actions").hidden = true;
      $("answer-meta").textContent = "glad that helped";
    });
  }

  const no = $("answer-no");
  if (no) {
    no.addEventListener("click", () => {
      const form = $("ticket-form");
      form.hidden = false;
      const subject = $("ticket-subject");
      if (subject) {
        subject.value = state.question.slice(0, 140);
        $("ticket-details").value = state.question;
        $("ticket-details").focus();
      }
      const login = $("ticket-login");
      if (login) {
        login.href = "/login?redirect-to=" + encodeURIComponent("/support?q=" + state.question);
      }
      form.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  const ticketForm = $("ticket-form");
  if (ticketForm && $("ticket-subject")) {
    ticketForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const subject = $("ticket-subject").value.trim();
      const details = $("ticket-details").value.trim();
      const error = $("ticket-error");
      error.textContent = "";
      if (!subject || !details) {
        error.textContent = "Please add a subject and a few words about what happened.";
        return;
      }

      let description = "<p>" + escapeHtml(details).replace(/\n/g, "<br>") + "</p>";
      if ($("ticket-include-ai").checked && state.answer) {
        description +=
          "<hr><p><strong>Flux AI suggested:</strong></p><p>" +
          escapeHtml(state.answer).replace(/\n/g, "<br>") +
          "</p>";
      }

      const submit = $("ticket-submit");
      submit.disabled = true;
      try {
        const doc = { subject, description };
        if (state.product) doc.flux_product = state.product;
        const ticket = await api("helpdesk.helpdesk.doctype.hd_ticket.api.new", { doc, attachments: [] });
        location.href = "/helpdesk/my-tickets/" + encodeURIComponent(ticket.name);
      } catch (e) {
        error.textContent = e.message;
        submit.disabled = false;
      }
    });
  }
})();
