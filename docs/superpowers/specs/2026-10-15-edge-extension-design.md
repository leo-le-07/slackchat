# Edge extension for slackchat: design

Date: 2026-10-15. Status: draft, waiting for Leo's approval.

## 1. Intent

Leo chats in Slack web (`https://app.slack.com/client/...`) every day. Today,
to fix an English sentence or translate Vietnamese, he copies the text into
the `slackchat` CLI, then copies the result back into Slack. The extension
removes that round trip: the text in the Slack input box goes to the local
`slackchat` daemon, and the result comes back as a small popup with a diff,
inside Slack. It is Grammarly-like in feel, but runs only when Leo asks.

This is "Phase 2" of `2026-08-22-slackchat-design.md`. It is a second client
of the same core service. It adds no logic of its own.

## 2. Goals

- A small button next to the Slack message input. Clicking it sends the
  current input text to the daemon.
- A popup above the input box that shows the result with an inline diff,
  and two buttons: **Check** (apply) and **Cancel** (dismiss).
- Runs on Microsoft Edge, loaded unpacked. No Edge Add-ons store.
- Works for both modes. The daemon auto-detects the mode from the text:
  Vietnamese with diacritics gives translation, anything else gives
  correction. The extension never picks a mode.
- A first working version fast. Breakage in Slack's editor is expected and
  fixed afterwards, not designed away up front.

## 3. Non-goals

- No marketplace publishing, no packaging, no auto-update.
- No hotkeys (not even Tab/Esc inside the popup). Mouse only.
- No auto-trigger while typing, no debounce.
- No settings beyond what is needed to reach the daemon (section 6).
- No other sites, no other browsers.
- No changes to the daemon, `core/`, prompts, or the DB schema.
- No showing of `flags` in the UI.
- No i18n. All UI text is English.
- No investigation of Slack's editor internals before the first version.

## 4. Anti-goals (a failure even if it "works")

- **Any logic copied from the Python side.** No language detection, no
  diffing, no validation, no retry in JS. The popup renders `changes` from
  the JSON as-is.
- **Losing the user's text.** Cancel, an error, or a closed popup must leave
  the input box exactly as it was. Check is the only action that writes.
- **Over-editing.** If `output` equals the original, the popup says there is
  nothing to fix and offers no Check button. The extension must not paper
  over a no-op.
- **Secrets in the wrong place.** The Anthropic API key must never reach the
  browser. Only the daemon token does.
- **Rendering Slack text as HTML.** Message text and model output are
  untrusted strings. Render them with `textContent`, never `innerHTML`.

## 5. User flow

1. Leo types in the Slack input box.
2. Leo clicks the extension's button next to the box.
3. A popup appears above the input with the text "Processing…".
4. On success, the popup shows:
   - a small label for the mode ("Correction" or "Translation");
   - the inline diff (design choice A below);
   - **Check** and **Cancel** buttons.
5. **Check** replaces the input text with `output` and closes the popup.
   **Cancel** closes the popup and changes nothing.
6. If `output` equals the original text: the popup shows "Nothing to fix"
   and a single close action, no Check.
7. On any error: the popup shows one generic line (for example
   "Something went wrong. Check that `slackchat serve` is running.") and a
   close action. No details in the UI.

### Diff design (chosen by Leo: option A)

One paragraph. Deleted words have a red background and strikethrough,
inserted words a green background, unchanged words plain. Built from
`Result.changes`: each item has `kind` (`equal`, `insert`, `delete`,
`replace`), `before`, and `after`. `replace` is shown as a red `before`
followed by a green `after`. For translation mode the original is Vietnamese
and the output English, so a word diff is meaningless: show only `output`
as plain text (my call, see section 9).

Mockup: `.superpowers/brainstorm/39058-1792051484/content/popup-layout.html`
(option A).

## 6. Daemon contract (verified against the code, 2026-10-15)

| Fact | Source |
|---|---|
| `POST http://127.0.0.1:8765/process`, body `{"text": "..."}` | `server/app.py` |
| Header `X-Slackchat-Token: <token>` is required, else 401 | `server/token.py` |
| Port defaults to 8765, set by `[server] port` | `config.py`, `config.example.toml` |
| Token is in `<cwd of slackchat serve>/.config/server_token` (`config_dir()` is `cwd/.config` unless `SLACKCHAT_CONFIG` is set), and is also printed by `slackchat serve`. `AGENTS.md` says `~/.config/slackchat/`; the code disagrees | `config.py`, `server/token.py` |
| Empty or whitespace-only text returns 400 | `server/app.py` |
| A provider failure returns **HTTP 200** with `output: ""` and a non-null `error` | `core/pipeline.py` |
| Response is `dataclasses.asdict(Result)`: `output`, `mode`, `changes`, `flags`, `error`, and more | `core/types.py` |
| CORS is off unless `[server] allowed_origins` is set; default is empty | `server/app.py` |
| Every run, including failed ones, is logged to the `runs` table with `flags` and `error` | `service.py`, `store/sqlite.py` |

So "log error details on the server or in the DB" needs no new code: it
already happens for every run that reaches the daemon. Only "daemon not
running" cannot be logged, because the request never arrives.

The extension must treat an error as any of: network failure, non-2xx
status, or a 200 with non-null `error`.

## 7. Architecture

Directory: `extension/` (it already exists, with a `.gitkeep`). Plain
files, no bundler, no framework, no npm dependencies.

- `manifest.json`: Manifest V3. Host permissions for `https://app.slack.com/*`
  and `http://127.0.0.1/*`. Permission `storage`.
- **Content script** on `app.slack.com`: injects the button, shows the popup,
  reads the input text, writes the text back on Check.
- **Service worker**: receives `{text}` from the content script, calls the
  daemon with the token header, returns the JSON or an error. All network
  access is here, so the Slack page never talks to `127.0.0.1` itself.
- **Options page**: one field for the daemon token. A port field defaulting
  to 8765 (my call). Saved in `chrome.storage.local`.

Why the service worker makes the call (my call, not verified on Edge): an
extension service worker with host permissions can call
`http://127.0.0.1` without the daemon's CORS allowlist. If Edge disagrees,
the fallback is to add the extension's origin to `[server] allowed_origins`,
as the 2026-08-22 spec originally planned.

The daemon is started by hand with `slackchat serve`. The extension does not
start or manage it.

## 8. Constraints from the repo

- `AGENTS.md`: tests never hit the network. Any JS test must fake the
  service worker's fetch.
- `scripts/check.sh` is the Python gate. This work does not have to change it.
  Do not break it: nothing under `extension/` may be imported by Python.
- Never put `ANTHROPIC_API_KEY` or the token in a committed file.
- `.superpowers/` must stay git-ignored (the `.gitignore` already has a
  pending change for it).

## 9. Decisions

Decided by Leo:
- Edge, unpacked, no marketplace.
- Trigger is a small button next to the input; no hotkeys; no auto-trigger.
- Popup with inline diff, option A; buttons Check and Cancel.
- "Processing" status in English, on the popup.
- Flags are not shown. Errors are one generic line. Details stay in server
  log or DB.
- Do not investigate Slack's editor first; ship a first version and fix what
  breaks.

My calls (Leo can overturn any of them):
- Manifest V3, vanilla JS, no build step.
- Service worker makes the daemon call.
- Token and port set on an options page, stored in `chrome.storage.local`.
- Translation mode shows `output` only, no word diff, because a diff between
  Vietnamese and English carries no information.
- Popup text for "no change": "Nothing to fix".
- UI isolated from Slack's CSS (for example with a Shadow DOM). The builder
  may choose how.

## 10. Left to the builder

- How to find the Slack input box and the right spot for the button. Slack's
  markup is not documented and may change.
- How to read the text and how to write it back (Check) so Slack's own state
  stays in sync. Expect this to need iteration.
- Popup placement, styling, and button icon.
- Whether a small JS test is worth adding for the diff-to-DOM function.
- File layout inside `extension/`.

## 11. Known risks

1. **Writing text back into Slack's editor** (highest). Slack's input is a
   rich editor, not a plain `<textarea>`. Mentions (`@Kenny Trinh`), emoji,
   code spans, and line breaks may not survive a plain-text round trip.
   Unknown today, deliberately not researched first. The first version
   targets plain text. Fix-forward when something breaks.
2. **Slack markup changes.** Selectors will break over time.
3. **Daemon not running or wrong token.** Shows the generic error. A person
   hitting this will not know which one it is. Acceptable for now.
4. **Cost and latency per click.** Each click is one Haiku call. Acceptable:
   it is user-initiated.

## 12. Done when (manual check, no automation required)

1. With `slackchat serve` running and the token saved, clicking the button on
   a message with a typo shows a diff popup. Check puts the corrected text in
   the box. Cancel leaves it untouched.
2. A correct sentence shows "Nothing to fix" and no Check button.
3. A Vietnamese sentence shows an English output. Check applies it.
4. With the daemon stopped, the popup shows the generic error and the input
   text is unchanged.
5. The last request appears in the `runs` table with `client='server'`.
