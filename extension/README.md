# slackchat Edge extension

A button next to the Slack message box that sends the text to the local
`slackchat` daemon and shows an inline diff before anything is applied.

Manifest V3, vanilla JS, no build step, no npm dependencies.

- `manifest.json` — MV3 manifest. `storage` permission; host permissions for
  `https://app.slack.com/*` and `http://127.0.0.1/*`.
- `lib/result.js` — the daemon client and the diff-segment builder. Classic
  script, also `require`-able from node. Loaded first, so
  `SlackchatLib` is visible to the scripts after it.
- `background.js` — service worker. Owns every network call; reads the token
  and port from `chrome.storage.local`.
- `content.js` — the button, the popup, and the read/write of the Slack input.
  Never talks to `127.0.0.1` itself.
- `options.html`, `options.js` — the token and port form.
- `test/result.test.js` — `node:test` tests for `lib/result.js`.

## Run it

1. Start the daemon **from the repo root**, because the token file is written
   to `<cwd>/.config/server_token` (`server/token.py`, `config.py`):

   ```bash
   uv run slackchat serve
   ```

   It prints `X-Slackchat-Token: <token>` on startup; the token is the value
   after the colon. Keep it running.

2. In Edge, open `edge://extensions`, turn on **Developer mode**, click
   **Load unpacked**, and pick this `extension/` directory.

3. Open the extension's **Options**, paste the token, and press **Save**.
   Leave the port empty unless you changed `[server] port` in your config
   (default 8765).

4. Open `https://app.slack.com`, reload the tab once after loading the
   extension, then type in the message box and click **Fix**.

Clicking **Fix** shows "Processing…", then either the diff with **Check** and
**Cancel**, "Nothing to fix", or "Something went wrong. Check that
`slackchat serve` is running.". **Check** is the only action that writes to
the box; **Cancel**, an error, and a close all leave it untouched.

## After a restart

1. Start the daemon **from the repo root**:

   ```bash
   cd /Users/leo/Work/tries/2026-08-22-translator && uv run slackchat serve
   ```

2. Nothing else. Edge keeps an unpacked extension loaded across restarts, and
   the token and port live in `chrome.storage.local`, so there is no token to
   paste again. Only a deleted `.config/server_token`, or `serve` started from
   another directory (it writes `<cwd>/.config/server_token`, so that directory
   gets a brand new token), forces a new paste.

Check whether the daemon is up:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/health
```

`200` means it is up, `000` means it is not running.

## After changing the extension

Both steps, in this order:

1. `edge://extensions` → the slackchat card → **⟳ Reload**.
2. **F5 the Slack tab.** Not optional: the content script already running in
   that tab keeps the old code until the page loads again, so an extension
   reload without a tab reload fails with `Extension context invalidated` in
   the popup — that is the symptom, not a bug.

| Changed | Do |
|---|---|
| `manifest.json`, `content.js`, `lib/result.js` | ⟳ Reload, then F5 Slack |
| `background.js` | ⟳ Reload is enough |
| `options.html`, `options.js` | Reopen the Options page |
| the token or port | Save in Options; nothing to reload |
| the repo's directory (moved or renamed) | Load unpacked again and paste the token again |

If ⟳ leaves a red error on the card, click **Errors** on the card to read it.

## When something looks wrong

**No Fix button at all.** In the Slack tab, F12 → Console:

```js
const ed = document.querySelector('[contenteditable="true"]');
let n = ed, out = [];
while (n && n !== document.body) { out.push(n.tagName + (n.dataset && n.dataset.qa ? `[data-qa="${n.dataset.qa}"]` : "") + " ." + (n.className || "")); n = n.parentElement; }
console.log(out.join("\n"));
```

If that prints no `[data-qa="message_input"]` ancestor, Slack changed its
markup: update `INPUT_CONTAINER` in `content.js` from that output.

**The generic error every time.** `edge://extensions` → the slackchat card →
**service worker** → Console:

```js
chrome.runtime.sendMessage({type:"process", text:"I has finish the task"}).then(console.log)
```

- `{ok: true, result: {...}}` — worker, daemon and token are fine; the fault is
  in `content.js`.
- `{ok: false}` — wrong token, daemon down, or the request is blocked before it
  leaves the browser (see the `allowed_origins` line in Known limits).

**Check writes nothing, or a mention, emoji or line break was lost.** That is
risk 1 in the design doc; note what was typed and what came back, then fix
forward in `content.js`.

**Did the request reach the daemon?**

```bash
sqlite3 data/runs.db "select created_at, client, mode, substr(input,1,36) from runs order by created_at desc limit 5;"
```

Extension requests are logged with `client='server'`.

## Tests

```bash
node --test "extension/test/*.test.js"
```

The glob, not `node --test extension/test/`: in Node 22.21 a bare directory
argument is treated as an entry module and fails with "Cannot find module".

The Python side is unchanged; `./scripts/check.sh` still gates it.

## Live acceptance checklist

Checked by hand on 2026-10-15: the extension loads, and the basic flow (a typo
→ diff popup → **Check** / **Cancel**) works on `app.slack.com`. The items
below are the ones still to walk through; the Slack selectors and the
write-back path in `content.js` were first guesses and stay provisional until
they all pass.

1. A message with a typo: diff popup; **Check** fills the box; **Cancel**
   leaves it.
2. A correct sentence: "Nothing to fix", no **Check**.
3. A Vietnamese sentence: English output; **Check** applies it.
4. Stop the daemon: the generic error line, input unchanged.
5. The last request appears in the `runs` table with `client='server'`
   (default DB path is under `data/`).
6. Type `<b>hi</b> & "x" teh` and click: the popup shows those literal
   characters, no markup.
7. Type text, click **Fix**, keep typing before the result arrives, then click
   **Check**: the box must be unchanged and the popup must show the error.
8. Double-click **Fix**: one request only, not two. Click it on an empty box:
   no popup at all.
9. The **Fix** button must not sit on top of Slack's own send button. It is
   placed bottom-right inside the input container; if it overlaps, move it in
   `content.js`.

## Known limits

- **Mentions, emoji, and line breaks are unverified.** Slack's input is a rich
  editor and `content.js` reads `innerText` and writes back with
  `execCommand("insertText")`. A plain-text round trip may flatten `@mentions`,
  emoji, or code spans. The first version targets plain text; fix forward when
  a real message shows what breaks.
- **Selectors are guesses**: `[data-qa="message_input"]` and the
  `[contenteditable="true"]` inside it. When Slack changes its markup, the
  button stops appearing; that is the first thing to re-check.
- **One daemon per browser profile.** The token and port are global settings,
  not per tab.
- **No hotkeys, no auto-trigger.** Every request is one click and one Haiku
  call.
- **Requests give up after 30 seconds** (`DEFAULT_TIMEOUT_MS` in
  `lib/result.js`), so a wedged daemon cannot leave "Processing…" on the screen
  forever. The input is untouched when that happens.
- **If every click gives the generic error while the daemon is running and the
  token is right**, the request may be blocked before it leaves the browser.
  The fallback is to add the extension's origin to `[server] allowed_origins`
  in your config (design doc section 7).
