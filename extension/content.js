"use strict";

// Slack's markup is undocumented; these are first guesses from the spec's
// fix-forward rule. task-4 of the plan records what breaks in the live run.
const INPUT_CONTAINER = '[data-qa="message_input"]';
const EDITABLE = '[contenteditable="true"]';
const ERROR_TEXT = "Something went wrong. Check that `slackchat serve` is running.";

const STYLE = `
  :host { all: initial; }
  .popup {
    font: 14px/1.5 -apple-system, "Segoe UI", sans-serif;
    color: #1d1c1d;
    background: #f8fbff;
    border: 1px solid #1264a3;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    padding: 10px 12px;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .label {
    font-size: 11px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #616061;
    margin-bottom: 4px;
  }
  del { background: #ffd7d5; color: #a40e26; text-decoration: line-through; }
  ins { background: #c9f0d4; color: #0a5c2e; text-decoration: none; }
  .actions { margin-top: 8px; display: flex; gap: 8px; }
  button {
    font: inherit;
    font-size: 12px;
    padding: 2px 10px;
    border-radius: 4px;
    border: 1px solid transparent;
    cursor: pointer;
  }
  .check { background: #007a5a; color: #fff; }
  .plain { background: #fff; border-color: #868686; color: #1d1c1d; }
`;

const sessions = [];

function editableIn(container) {
  return container.querySelector(EDITABLE);
}

function writeText(editable, text) {
  editable.focus();
  document.execCommand("selectAll");
  document.execCommand("insertText", false, text);
}

function attach(container) {
  if (container.dataset.slackchatAttached) {
    return;
  }
  container.dataset.slackchatAttached = "1";

  if (getComputedStyle(container).position === "static") {
    container.style.position = "relative";
  }

  const button = document.createElement("button");
  // The small mark: blue tile, white S. Same as icons/icon16.png. No ring or
  // tick here, they turn to mush at 20px.
  button.textContent = "S";
  button.title = "slackchat: check this message";
  button.setAttribute("aria-label", "slackchat: check this message");
  button.setAttribute(
    "style",
    "position:absolute; right:8px; bottom:8px; z-index:10; width:20px; height:20px; padding:0;" +
      "font:bold 12px -apple-system,'Segoe UI',sans-serif; line-height:1;" +
      "border:none; border-radius:5px; background:#1b7fe3; color:#fff; cursor:pointer;",
  );
  // Do not steal focus from the editable.
  button.addEventListener("mousedown", (event) => event.preventDefault());
  container.append(button);

  const session = {
    container,
    sentText: null,
    result: null,
    pending: false,
    host: null,
    nodes: null,
  };
  sessions.push(session);
  button.addEventListener("click", () => start(session));
}

function ensurePopup(session) {
  if (session.nodes) {
    return session.nodes;
  }

  const host = document.createElement("div");
  host.setAttribute(
    "style",
    "position:fixed; z-index:2147483000; width:24rem; max-width:90vw;",
  );
  const shadow = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = STYLE;
  const popup = document.createElement("div");
  popup.className = "popup";
  const label = document.createElement("div");
  label.className = "label";
  const body = document.createElement("div");
  const actions = document.createElement("div");
  actions.className = "actions";

  const check = document.createElement("button");
  check.className = "check";
  check.textContent = "Check";
  const cancel = document.createElement("button");
  cancel.className = "plain";
  cancel.textContent = "Cancel";
  const close = document.createElement("button");
  close.className = "plain";
  close.textContent = "Close";

  popup.append(label, body, actions);
  shadow.append(style, popup);

  check.addEventListener("click", () => {
    const editable = editableIn(session.container);
    // Leo kept typing: applying now would throw his newer text away.
    if (!editable || editable.innerText !== session.sentText) {
      render(session, "error");
      return;
    }
    writeText(editable, session.result.output);
    dismiss(session);
  });
  cancel.addEventListener("click", () => dismiss(session));
  close.addEventListener("click", () => dismiss(session));

  session.host = host;
  session.nodes = { popup, label, body, actions, check, cancel, close };
  return session.nodes;
}

function place(session) {
  const rect = session.container.getBoundingClientRect();
  const host = session.host;
  const width = host.offsetWidth || 384;
  host.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`;
  host.style.bottom = `${Math.max(8, window.innerHeight - rect.top + 8)}px`;
}

// The four popup states, in one place.
function render(session, state) {
  const nodes = ensurePopup(session);
  if (session.host.parentNode !== document.body) {
    document.body.append(session.host);
  }
  place(session);

  nodes.label.textContent = "slackchat";
  nodes.body.textContent = "";
  nodes.actions.replaceChildren();

  if (state === "processing") {
    nodes.body.textContent = "Processing…";
  } else if (state === "result") {
    nodes.label.textContent = session.result.mode === "translation" ? "Translation" : "Correction";
    for (const segment of SlackchatLib.buildSegments(session.result)) {
      if (segment.kind === "equal") {
        nodes.body.append(segment.text);
      } else {
        const element = document.createElement(segment.kind === "del" ? "del" : "ins");
        element.textContent = segment.text;
        nodes.body.append(element);
      }
    }
    nodes.actions.append(nodes.check, nodes.cancel);
  } else if (state === "nochange") {
    nodes.body.textContent = "Nothing to fix";
    nodes.actions.append(nodes.close);
  } else {
    nodes.body.textContent = ERROR_TEXT;
    nodes.actions.append(nodes.close);
  }
}

function dismiss(session) {
  session.sentText = null;
  session.result = null;
  if (session.host && session.host.parentNode) {
    session.host.remove();
  }
}

async function start(session) {
  const editable = editableIn(session.container);
  if (!editable || session.pending) {
    return;
  }
  const text = editable.innerText;
  if (!text.trim()) {
    return;
  }

  session.pending = true;
  session.sentText = text;
  render(session, "processing");

  let response = { ok: false };
  try {
    response = await chrome.runtime.sendMessage({ type: "process", text });
  } catch {
    response = { ok: false };
  }
  session.pending = false;

  if (!response || !response.ok) {
    render(session, "error");
    return;
  }
  session.result = response.result;
  render(session, SlackchatLib.classify(response.result) === "nochange" ? "nochange" : "result");
}

function attachAll() {
  for (const session of sessions) {
    if (!session.container.isConnected) {
      dismiss(session);
    }
  }
  for (const container of document.querySelectorAll(INPUT_CONTAINER)) {
    attach(container);
  }
}

attachAll();
new MutationObserver(attachAll).observe(document.body, { childList: true, subtree: true });
