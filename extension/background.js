"use strict";

// Classic worker script: importScripts puts SlackchatLib on the worker global.
importScripts("lib/result.js");

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "process") {
    return;
  }

  chrome.storage.local.get(["token", "port"]).then(({ token, port }) => {
    if (!token) {
      sendResponse({ ok: false });
      return;
    }
    SlackchatLib.callDaemon(message.text, { token, port }, fetch).then(sendResponse);
  });

  // Keep the message channel open for the async response above.
  return true;
});
