# slackchat Edge extension

Button next to the Slack message box: sends the text to the local `slackchat`
daemon, shows an inline diff, applies it only when you click **Check**.
Manifest V3, vanilla JS, no build step, no npm dependencies.
Design: `docs/superpowers/specs/2026-10-15-edge-extension-design.md`.

## Run it (once)

1. Daemon, **from the repo root** (the token file is `<cwd>/.config/server_token`):

   ```bash
   uv run slackchat serve
   ```

   It prints `X-Slackchat-Token: <token>`; the token is the value after the colon.

2. Edge → `edge://extensions` → **Developer mode** → **Load unpacked** → pick this
   `extension/` directory.

3. Extension **Options** → paste the token → **Save**. Leave port empty (= 8765).

Then open `https://app.slack.com`, type in the message box, click **Fix**.

## After a reboot

Only step 1 above. Edge keeps an unpacked extension loaded and the token lives
in `chrome.storage.local`, so there is nothing to paste again — unless
`.config/server_token` was deleted, or you started `serve` from another
directory, which writes a brand new token there.

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/health   # 200 = up, 000 = not running
```

## After editing the extension

1. `edge://extensions` → slackchat card → **⟳ Reload**
2. **F5 the Slack tab.** Not optional: the content script already in that tab
   keeps the old code, so the popup shows `Extension context invalidated`.

Only `options.html`/`options.js` changed → just reopen the Options page.
Only `background.js` changed → ⟳ is enough.

## When it breaks

**No Fix button.** First check you F5'd the Slack tab after the last reload.
Still missing → F12 → Console in the Slack tab:

```js
const ed = document.querySelector('[contenteditable="true"]');
console.log(ed && ed.closest("[data-qa]") && ed.closest("[data-qa]").dataset.qa);
```

Prints `message_input` → tell me the console errors. Prints anything else (or
`undefined`) → Slack changed its markup, `INPUT_CONTAINER` in `content.js` needs
the new value.

**Generic error every time.** `edge://extensions` → slackchat card → **service
worker** → Console:

```js
chrome.runtime.sendMessage({type:"process", text:"I has finish the task"}).then(console.log)
```

- `{ok: true, result: {...}}` → worker + daemon + token are fine, the fault is
  in `content.js`.
- `{ok: false}` → wrong token, daemon down, or the request never left the
  browser; last resort is adding the extension's origin to
  `[server] allowed_origins` in `.config/config.toml` and restarting `serve`.

**Check does nothing, or a mention / emoji / line break was lost.** The
write-back path is the known weak spot — note what you typed and what came
back, that is fixable in `content.js`.

**Did the request reach the daemon?**

```bash
sqlite3 data/runs.db "select created_at, client, mode, substr(input,1,36) from runs order by created_at desc limit 5;"
```

Extension runs are logged with `client='server'`.

## Tests

```bash
node --test "extension/test/*.test.js"
```

The glob, not `node --test extension/test/` (a bare directory fails on Node
22.21). `./scripts/check.sh` does not cover JS.

## Not yet verified

- `@mentions`, emoji, and Shift+Enter line breaks surviving a round trip.
- The Slack selectors (`[data-qa="message_input"]`) and the write-back — first guesses.
- The **Fix** button not sitting on top of Slack's own send button.
