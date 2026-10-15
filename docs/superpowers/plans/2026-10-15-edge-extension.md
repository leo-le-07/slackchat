# Edge Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An Edge extension that adds a button next to the Slack message input; clicking it sends the input text to the local `slackchat` daemon and shows an inline-diff popup with Check and Cancel.

**Architecture:** Manifest V3, plain JS, no build step. A pure, node-testable library (`lib/result.js`) turns the daemon's JSON into diff segments and talks to the daemon. A classic service worker calls the library; a content script on `app.slack.com` owns the button, popup, and the read/write of the input box.

**Tech Stack:** Vanilla JS, `node --test` (Node 22 is installed) for the pure library. No npm dependencies.

**Spec:** `docs/superpowers/specs/2026-10-15-edge-extension-design.md`

## Global Constraints

- Edge, loaded unpacked, Manifest V3, vanilla JS, no build step, no npm dependencies.
- Host permissions: `https://app.slack.com/*` and `http://127.0.0.1/*`. Permission: `storage`.
- Daemon: `POST http://127.0.0.1:<port>/process`, body `{"text": "..."}`, header `X-Slackchat-Token: <token>`. Port defaults to `8765`.
- Error means any of: network failure, non-2xx status, or HTTP 200 with a non-null `error`.
- All network access happens in the service worker. The content script never calls `127.0.0.1`.
- All UI text is English. Popup status text is "Processing…". Error line is generic. No-change text is "Nothing to fix". Buttons are **Check** and **Cancel**. No hotkeys.
- No logic copied from Python: no detect, no diff, no validation in JS. Render `changes` from the JSON.
- Render message text and model output with `textContent`, never `innerHTML`.
- Never write to the input box except on Check. Cancel, errors, and closing leave it untouched.
- Never put `ANTHROPIC_API_KEY` or the token in a committed file.
- Do not change anything under `src/`, `tests/`, or `scripts/check.sh`.

## Review Focus

Failure modes the spec implies that most likely bite Leo, most likely first:

1. HTTP 200 with a non-null `error` (the daemon's real failure shape) must show the generic error, not an empty "successful" diff. Pinned in Task 1.
2. Leo edits the input while the request is in flight, then clicks Check. Check must not overwrite the newer text. Pinned in Task 3.
3. Leo double-clicks the button, or clicks it on an empty box. No second request while one is in flight; no request for blank text. Pinned in Task 3.
4. Daemon stopped, or token missing or wrong: generic error, input unchanged. Pinned in Task 1 (401, rejected fetch) and Task 4 (live).
5. Message text containing `<`, `&`, or quotes. Rendered as text, never as markup. Pinned in Task 4 (live).

---

### Task 1: Pure library `lib/result.js`

**Files:**
- Create: `extension/lib/result.js`
- Test: `extension/test/result.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces, on a global `SlackchatLib` (and `module.exports` when `module` exists, so node can `require` it):
  - `buildSegments(result): Array<{kind: "equal" | "del" | "ins", text: string}>`
  - `classify(result): "nochange" | "ok"`. Assumes the result is not an error.
  - `callDaemon(text: string, settings: {token: string, port?: number}, fetchFn: typeof fetch): Promise<{ok: true, result: object} | {ok: false}>`

Segment rules: `equal` gives one `equal` segment from `before`; `delete` gives `del`; `insert` gives `ins`; `replace` gives a `del` from `before` then an `ins` from `after`. When `result.mode === "translation"`, return exactly one `equal` segment holding `result.output` (a word diff between Vietnamese and English means nothing). `nochange` means `result.output.trim() === result.original.trim()`.

`callDaemon` returns `{ok: false}` for a rejected fetch, a non-2xx status, a JSON body that fails to parse, or a body whose `error` is non-null. It never throws and never exposes error details. Port defaults to 8765.

- [ ] **Step 1: Write the failing tests** in `extension/test/result.test.js` using `node:test` and `node:assert/strict`:
  - `buildSegments maps equal/replace/insert/delete`: for changes `[equal "Hi there", replace "progres"→"progress", equal "on", insert ""→"now", delete "old"→""]` expect segments `equal "Hi there"`, `del "progres"`, `ins "progress"`, `equal "on"`, `ins "now"`, `del "old"`.
  - `buildSegments gives translation a single equal segment of output`: mode `"translation"`, any `changes`, expect `[{kind:"equal", text: output}]`.
  - `classify returns nochange when output matches original ignoring outer whitespace`, and `classify returns ok when they differ`.
  - `callDaemon posts text with the token header`: fake fetch records its args; expect URL `http://127.0.0.1:8765/process`, method `POST`, header `X-Slackchat-Token` equals the token, body `{"text":"..."}`; returns `{ok: true, result}`.
  - `callDaemon honours a custom port`: URL uses `http://127.0.0.1:9000/process`.
  - `callDaemon returns ok:false` for each of: fetch rejects; status 401; status 400; status 200 with `{error: "boom", output: ""}`; status 200 with a body that is not JSON.

- [ ] **Step 2: Run to verify failure**

Run: `node --test extension/test/`
Expected: FAIL, cannot find module `../lib/result.js`.

- [ ] **Step 3: Implement** the three functions in `extension/lib/result.js`. Wrap as a classic script: define `const SlackchatLib = {...}` and end with `if (typeof module !== "undefined") module.exports = SlackchatLib;`. Do not use ES `import`/`export`, because the content script and service worker load it as a classic script.

- [ ] **Step 4: Run to verify pass**

Run: `node --test extension/test/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add extension/lib/result.js extension/test/result.test.js
git commit -m "feat(extension): add the daemon client and diff segment builder"
```

---

### Task 2: Manifest, service worker, options page

**Files:**
- Create: `extension/manifest.json`, `extension/background.js`, `extension/options.html`, `extension/options.js`
- Delete: `extension/.gitkeep`

**Interfaces:**
- Consumes: `SlackchatLib.callDaemon` from Task 1.
- Produces:
  - Storage: `chrome.storage.local` keys `token` (string) and `port` (number, optional; default 8765).
  - Runtime message from the content script: `{type: "process", text: string}`. Response: `{ok: true, result: object}` or `{ok: false}`. If no token is saved, respond `{ok: false}` without calling the daemon.
  - Content-script load order in the manifest: `lib/result.js`, then `content.js` (Task 3).

- [ ] **Step 1: Write `manifest.json`.** MV3; `name` "slackchat"; `permissions: ["storage"]`; `host_permissions: ["https://app.slack.com/*", "http://127.0.0.1/*"]`; `background: {service_worker: "background.js"}` (classic, not a module); `options_ui: {page: "options.html", open_in_tab: true}`; `content_scripts: [{matches: ["https://app.slack.com/*"], js: ["lib/result.js", "content.js"]}]`.

- [ ] **Step 2: Write `background.js`.** First line `importScripts("lib/result.js")`. One `chrome.runtime.onMessage` listener for `type: "process"`: read `token` and `port` from `chrome.storage.local`, call `SlackchatLib.callDaemon(text, {token, port}, fetch)`, `sendResponse` with the result. Return `true` from the listener so the response can be async.

- [ ] **Step 3: Write the options page.** `options.html` has a token input (type password), a port input (number, placeholder 8765), a Save button, and a one-line hint "Run `slackchat serve` and paste the token it prints." `options.js` loads saved values on open and saves on click. UI text in English.

- [ ] **Step 4: Verify it loads.** In Edge, open `edge://extensions`, enable Developer mode, click "Load unpacked", pick `extension/`. Expected: loads with no errors on the card. Open its Options, save a token, reopen, and confirm the value persisted.

- [ ] **Step 5: Verify the worker end to end.** Run `uv run slackchat serve`, save the printed token in Options. On the extension card click "service worker" to open its devtools console and run:
`chrome.runtime.sendMessage({type:"process", text:"I has finish the task"}).then(console.log)`
Expected: `{ok: true, result: {output: ..., mode: "correction", ...}}`. With a wrong token, expected `{ok: false}`.

- [ ] **Step 6: Commit**

```bash
git rm extension/.gitkeep
git add extension/manifest.json extension/background.js extension/options.html extension/options.js
git commit -m "feat(extension): add the manifest, service worker and options page"
```

---

### Task 3: Content script: button, popup, apply

**Files:**
- Create: `extension/content.js`

**Interfaces:**
- Consumes: `SlackchatLib.buildSegments` and `SlackchatLib.classify` (Task 1, already loaded before `content.js`); runtime message `{type: "process", text}` (Task 2).
- Produces: nothing other tasks use.

Slack's markup is undocumented. These are first guesses, per the spec's fix-forward rule. Change them when Task 4 shows they are wrong:
- Input container: `[data-qa="message_input"]`; editable: the `[contenteditable="true"]` inside it.
- Read text with `innerText`. Write with `editable.focus()`, `document.execCommand("selectAll")`, then `document.execCommand("insertText", false, output)`.
- Attach one button per container (mark attached containers), and use a `MutationObserver` on `document.body` to attach to containers Slack renders later (channel switches, threads).

- [ ] **Step 1: Button.** Inject a small button inside each input container, bottom-right. It must not steal focus from the editable (use `mousedown` `preventDefault`).

- [ ] **Step 2: Popup shell.** One popup per container, a Shadow DOM host positioned above the input so Slack's CSS cannot touch it. Four states, switched by one function: `processing` ("Processing…"), `result` (mode label "Correction" or "Translation", diff paragraph, Check and Cancel), `nochange` ("Nothing to fix" and a Close button, no Check), `error` (the generic line "Something went wrong. Check that `slackchat serve` is running." and a Close button). Build every text node with `textContent`. Diff styling: `del` red background with strikethrough, `ins` green background, `equal` plain. In `translation` mode show the single `equal` segment as plain text.

- [ ] **Step 3: Click handler.** On button click:
  1. Read text. If `text.trim()` is empty, do nothing and send no request.
  2. If the popup is already in `processing`, do nothing.
  3. Show `processing`, send `{type: "process", text}`.
  4. On `{ok: false}` show `error`. On `{ok: true, result}`, show `nochange` if `SlackchatLib.classify(result) === "nochange"`, else `result`.
  5. Keep the `text` that was sent alongside the popup state.

- [ ] **Step 4: Check and Cancel.** Cancel closes the popup and writes nothing. Check re-reads the input text first. If it differs from the text that was sent, switch to `error` and write nothing (Leo kept typing). Otherwise write `result.output` into the editable and close the popup.

- [ ] **Step 5: Smoke check.** Reload the extension, reload the Slack tab. Expected: the button appears next to the input, and clicking it with text produces the Processing popup.

- [ ] **Step 6: Commit**

```bash
git add extension/content.js
git commit -m "feat(extension): add the Slack button, diff popup and apply"
```

---

### Task 4: Acceptance run, fixes, README

**Files:**
- Create: `extension/README.md`
- Modify: `extension/content.js` (selectors and write-back, as the run requires)

**Interfaces:**
- Consumes: the working extension from Tasks 1 to 3.
- Produces: the run instructions, and the answer to whether the first-guess selectors hold.

- [ ] **Step 1: Run the spec's acceptance list** (spec section 12) on `https://app.slack.com`, with `slackchat serve` running:
  1. A message with a typo: diff popup; Check fills the box; Cancel leaves it.
  2. A correct sentence: "Nothing to fix", no Check.
  3. A Vietnamese sentence: English output; Check applies it.
  4. Stop the daemon: generic error, input unchanged.
  5. Run `sqlite3` on the `runs` table (path from `slackchat.config`/`SLACKCHAT_DB`; default is under `data/`): the latest rows have `client='server'`.

- [ ] **Step 2: Run the Review Focus checks live.**
  - Type `<b>hi</b> & "x" teh` and click: the popup shows the literal characters, no bold, no injected markup.
  - Type text, click the button, and immediately type more before the result arrives, then click Check: the box is unchanged and the popup shows the error line.
  - Double-click the button: one request only (watch the service-worker console or the `runs` table). Click it on an empty box: no popup.
  - Type a multi-line message (Shift+Enter) containing an `@mention` and an emoji, click, Check. Write down exactly what survives. This is the spec's highest risk. Do not research first; fix what breaks.

- [ ] **Step 3: Fix what broke** in `extension/content.js`, minimal changes, and re-run the failing check. If a fix needs a daemon change, stop and tell Leo; it is outside this spec.

- [ ] **Step 4: Write `extension/README.md`.** Cover: start the daemon (`uv run slackchat serve`, run it from the repo root because the token file lives in `<cwd>/.config/`), load unpacked in Edge, paste the token in Options, how to run the library tests (`node --test extension/test/`), and a "Known limits" list from what Step 2 found about mentions, emoji, and line breaks.

- [ ] **Step 5: Final verification**

Run: `node --test extension/test/ && ./scripts/check.sh`
Expected: node tests PASS, and `check.sh` exits 0 (the Python side must still be green).

- [ ] **Step 6: Commit**

```bash
git add extension/README.md extension/content.js
git commit -m "docs(extension): add run instructions and record the Slack limits"
```
