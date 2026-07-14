// OPERATOR Browser Bridge — MV3 service worker.
// Connects OUT to OPERATOR's localhost WebSocket and executes browser actions
// it requests: tab management via chrome.tabs, page actions via
// chrome.scripting.executeScript (functions injected on demand; the isolated
// world persists per-page, so element handles from `read` stay valid for
// `click`/`fill` until the page navigates).

const BRIDGE_URL = "ws://127.0.0.1:8377";
let ws = null;
let retryMs = 1000;

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try { ws = new WebSocket(BRIDGE_URL); } catch (e) { return scheduleRetry(); }

  ws.onopen = () => { retryMs = 1000; console.log("Connected to OPERATOR"); };
  ws.onclose = () => scheduleRetry();
  ws.onerror = () => { try { ws.close(); } catch (e) {} };
  ws.onmessage = async (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch (e) { return; }
    let reply;
    try {
      const result = await handle(msg.action, msg.params || {});
      reply = { id: msg.id, ok: true, result };
    } catch (e) {
      reply = { id: msg.id, ok: false, error: String(e && e.message || e) };
    }
    try { ws.send(JSON.stringify(reply)); } catch (e) {}
  };
}

function scheduleRetry() {
  setTimeout(connect, retryMs);
  retryMs = Math.min(retryMs * 2, 15000);
}

// The websocket keeps the service worker alive while connected (Chrome 116+);
// the alarm wakes it up to reconnect if it was ever suspended.
chrome.alarms.create("reconnect", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(connect);
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();

// ==================== Action dispatch ====================

async function handle(action, p) {
  switch (action) {
    case "ping":      return "pong";
    case "tabs":      return listTabs();
    case "open":      return openTab(p.url);
    case "navigate":  return navigate(p.url, p.tab_id);
    case "close_tab": return closeTab(p.tab_id);
    case "read":      return inPage(p.tab_id, readPage, [p.max_chars || 6000]);
    case "click":     return inPage(p.tab_id, clickElement, [p.element, p.selector || null]);
    case "fill":      return inPage(p.tab_id, fillElement, [p.element, p.selector || null, p.text || "", !!p.submit]);
    default: throw new Error("Unknown browser action: " + action);
  }
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) throw new Error("No active tab");
  return tab;
}

async function targetTab(tabId) {
  if (tabId) return chrome.tabs.get(tabId);
  return activeTab();
}

async function listTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs.map(t => ({ id: t.id, active: t.active, title: t.title, url: t.url }));
}

async function openTab(url) {
  if (!url) throw new Error("open requires a url");
  const tab = await chrome.tabs.create({ url });
  return { id: tab.id, url };
}

async function navigate(url, tabId) {
  if (!url) throw new Error("navigate requires a url");
  const tab = await targetTab(tabId);
  await chrome.tabs.update(tab.id, { url, active: true });
  return { id: tab.id, url };
}

async function closeTab(tabId) {
  const tab = await targetTab(tabId);
  await chrome.tabs.remove(tab.id);
  return "closed";
}

async function inPage(tabId, func, args) {
  const tab = await targetTab(tabId);
  if (!/^https?:|^file:/.test(tab.url || "")) {
    throw new Error("Cannot script this page (" + (tab.url || "unknown") + ")");
  }
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id }, func, args,
  });
  if (result && result.__error) throw new Error(result.__error);
  return result;
}

// ==================== Injected page functions ====================
// These run inside the page (isolated world). No closures over worker state.

function readPage(maxChars) {
  const els = [];
  const seen = new Set();
  const selector = "a[href], button, input, select, textarea, [role='button'], [onclick], [contenteditable='true']";
  for (const el of document.querySelectorAll(selector)) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;                 // invisible
    if (seen.has(el)) continue;
    seen.add(el);
    const label = (el.innerText || el.value || el.placeholder ||
                   el.getAttribute("aria-label") || el.name || "").trim().slice(0, 80);
    const entry = { i: els.length, tag: el.tagName.toLowerCase(), text: label };
    if (el.tagName === "INPUT") entry.type = el.type;
    if (el.tagName === "A") entry.href = (el.href || "").slice(0, 200);
    els.push(entry);
    if (els.length >= 120) break;
  }
  window.__opEls = Array.from(seen);
  let text = (document.body && document.body.innerText || "").replace(/\n{3,}/g, "\n\n");
  if (text.length > maxChars) text = text.slice(0, maxChars) + "\n...(page text truncated)";
  return { url: location.href, title: document.title, text, elements: els };
}

function clickElement(index, selector) {
  let el = null;
  if (selector) el = document.querySelector(selector);
  else if (window.__opEls && index != null) el = window.__opEls[index];
  if (!el) return { __error: "Element not found — call browser read first (element handles reset on navigation)" };
  el.scrollIntoView({ block: "center" });
  el.click();
  return "clicked: " + (el.innerText || el.value || el.tagName).trim().slice(0, 60);
}

function fillElement(index, selector, text, submit) {
  let el = null;
  if (selector) el = document.querySelector(selector);
  else if (window.__opEls && index != null) el = window.__opEls[index];
  if (!el) return { __error: "Element not found — call browser read first (element handles reset on navigation)" };
  el.focus();
  if (el.isContentEditable) {
    el.innerText = text;
  } else {
    const setter = Object.getOwnPropertyDescriptor(
      el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, "value");
    if (setter && setter.set) setter.set.call(el, text); else el.value = text;
  }
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  if (submit) {
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
    if (el.form) el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit();
  }
  return "filled: " + text.slice(0, 60);
}
