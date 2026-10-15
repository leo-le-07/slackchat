"use strict";

// Pure helpers shared by the service worker (via importScripts) and the
// content script (via the manifest's content_scripts order). Classic script:
// no import/export, so both worlds can load it.
const DEFAULT_PORT = 8765;
// A wedged daemon (the Anthropic client has a 10-minute default timeout) must
// not leave the popup on "Processing…" with its Fix button dead forever.
const DEFAULT_TIMEOUT_MS = 30000;

function buildSegments(result) {
  // A word diff between Vietnamese and English carries no information.
  if (result.mode === "translation") {
    return [{ kind: "equal", text: result.output }];
  }

  const segments = [];
  for (const change of result.changes) {
    if (change.kind === "equal") {
      segments.push({ kind: "equal", text: change.before });
    } else if (change.kind === "delete") {
      segments.push({ kind: "del", text: change.before });
    } else if (change.kind === "insert") {
      segments.push({ kind: "ins", text: change.after });
    } else if (change.kind === "replace") {
      segments.push({ kind: "del", text: change.before });
      segments.push({ kind: "ins", text: change.after });
    }
  }
  return segments;
}

function classify(result) {
  return result.output.trim() === result.original.trim() ? "nochange" : "ok";
}

async function callDaemon(text, settings, fetchFn) {
  const port = settings.port || DEFAULT_PORT;
  const controller = new AbortController();
  // A ref'd timer, not AbortSignal.timeout: node unrefs that one, so a caller
  // waiting only on it would exit before the timeout fires.
  const timer = setTimeout(
    () => controller.abort(),
    settings.timeoutMs || DEFAULT_TIMEOUT_MS,
  );
  // Only the request itself gets a reason. A rejection here is the daemon not
  // listening (or the fetch never left the browser); an abort means it is up
  // but wedged. Later failures stay generic, so a 401 and a provider error
  // look the same on purpose.
  let response;
  try {
    response = await fetchFn(`http://127.0.0.1:${port}/process`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Slackchat-Token": settings.token,
      },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });
  } catch {
    return { ok: false, reason: controller.signal.aborted ? "timeout" : "offline" };
  } finally {
    clearTimeout(timer);
  }
  try {
    if (!response.ok) {
      return { ok: false };
    }
    const result = await response.json();
    // The daemon reports provider failures as HTTP 200 with a non-null error.
    if (result.error) {
      return { ok: false };
    }
    return { ok: true, result };
  } catch {
    return { ok: false };
  }
}

const SlackchatLib = { buildSegments, classify, callDaemon };
if (typeof module !== "undefined") {
  module.exports = SlackchatLib;
}
