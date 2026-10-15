"use strict";

const tokenInput = document.getElementById("token");
const portInput = document.getElementById("port");
const savedLabel = document.getElementById("saved");

chrome.storage.local.get(["token", "port"]).then(({ token, port }) => {
  if (token) {
    tokenInput.value = token;
  }
  if (port) {
    portInput.value = port;
  }
});

document.getElementById("save").addEventListener("click", async () => {
  const port = portInput.value.trim();
  await chrome.storage.local.set({ token: tokenInput.value.trim() });
  // No port saved means the library's default, 8765.
  if (port) {
    await chrome.storage.local.set({ port: Number(port) });
  } else {
    await chrome.storage.local.remove("port");
  }
  savedLabel.textContent = "Saved";
  setTimeout(() => {
    savedLabel.textContent = "";
  }, 1500);
});
