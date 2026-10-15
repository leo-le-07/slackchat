"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { buildSegments, classify, callDaemon } = require("../lib/result.js");

const change = (kind, before, after) => ({ kind, before, after });

test("buildSegments maps equal/replace/insert/delete", () => {
  const result = {
    mode: "correction",
    changes: [
      change("equal", "Hi there", "Hi there"),
      change("replace", "progres", "progress"),
      change("equal", " on", " on"),
      change("insert", "", " now"),
      change("delete", " old", ""),
    ],
  };

  assert.deepEqual(buildSegments(result), [
    { kind: "equal", text: "Hi there" },
    { kind: "del", text: "progres" },
    { kind: "ins", text: "progress" },
    { kind: "equal", text: " on" },
    { kind: "ins", text: " now" },
    { kind: "del", text: " old" },
  ]);
});

test("buildSegments gives translation a single equal segment of output", () => {
  const result = {
    mode: "translation",
    output: "Hi, is there any progress?",
    changes: [change("replace", "có tiến triển", "any progress")],
  };

  assert.deepEqual(buildSegments(result), [
    { kind: "equal", text: "Hi, is there any progress?" },
  ]);
});

test("classify returns nochange when output matches original ignoring outer whitespace", () => {
  assert.equal(
    classify({ output: "  Done. ", original: "Done." }),
    "nochange",
  );
});

test("classify returns ok when they differ", () => {
  assert.equal(classify({ output: "Done now.", original: "Done." }), "ok");
});

function recordingFetch(response) {
  const calls = [];
  const fetchFn = async (url, options) => {
    calls.push({ url, options });
    return response;
  };
  return { fetchFn, calls };
}

const jsonResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

test("callDaemon posts text with the token header", async () => {
  const result = { output: "I have finished the task.", error: null };
  const { fetchFn, calls } = recordingFetch(jsonResponse(200, result));

  const response = await callDaemon("I has finish the task", { token: "secret" }, fetchFn);

  assert.deepEqual(response, { ok: true, result });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://127.0.0.1:8765/process");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers["X-Slackchat-Token"], "secret");
  assert.equal(calls[0].options.body, JSON.stringify({ text: "I has finish the task" }));
});

test("callDaemon honours a custom port", async () => {
  const { fetchFn, calls } = recordingFetch(jsonResponse(200, { error: null }));

  await callDaemon("hi", { token: "t", port: 9000 }, fetchFn);

  assert.equal(calls[0].url, "http://127.0.0.1:9000/process");
});

test("callDaemon returns ok:false when fetch rejects", async () => {
  const fetchFn = async () => {
    throw new TypeError("Failed to fetch");
  };

  assert.deepEqual(await callDaemon("hi", { token: "t" }, fetchFn), { ok: false });
});

test("callDaemon returns ok:false on status 401", async () => {
  const { fetchFn } = recordingFetch(jsonResponse(401, { detail: "missing or invalid token" }));

  assert.deepEqual(await callDaemon("hi", { token: "wrong" }, fetchFn), { ok: false });
});

test("callDaemon returns ok:false on status 400", async () => {
  const { fetchFn } = recordingFetch(jsonResponse(400, { detail: "empty input" }));

  assert.deepEqual(await callDaemon("   ", { token: "t" }, fetchFn), { ok: false });
});

test("callDaemon returns ok:false on 200 with a non-null error", async () => {
  const { fetchFn } = recordingFetch(jsonResponse(200, { output: "", error: "boom" }));

  assert.deepEqual(await callDaemon("hi", { token: "t" }, fetchFn), { ok: false });
});

test("callDaemon returns ok:false on a body that is not JSON", async () => {
  const { fetchFn } = recordingFetch({
    ok: true,
    status: 200,
    json: async () => {
      throw new SyntaxError("Unexpected token <");
    },
  });

  assert.deepEqual(await callDaemon("hi", { token: "t" }, fetchFn), { ok: false });
});

test("callDaemon gives up when the daemon never answers", async () => {
  const fetchFn = (_url, options) =>
    new Promise((_resolve, reject) => {
      // No signal means no timeout: hang, exactly like a wedged daemon.
      if (!options.signal) {
        return;
      }
      options.signal.addEventListener("abort", () => reject(new Error("aborted")));
    });

  assert.deepEqual(await callDaemon("hi", { token: "t", timeoutMs: 20 }, fetchFn), {
    ok: false,
  });
});
