# OPERATOR Browser Bridge (Chrome extension)

Lets OPERATOR work inside the browser you actually use — your profile, your
logins, your tabs. It connects to OPERATOR over `ws://127.0.0.1:8377` only;
nothing ever leaves your machine.

## Install (one time)

1. Open Chrome (or Edge/Brave) → `chrome://extensions`
2. Turn on **Developer mode** (top right)
3. Click **Load unpacked** → select this `extension/` folder
4. Done. It auto-connects whenever OPERATOR is running (and retries forever,
   so start order doesn't matter).

## What OPERATOR can do with it

| Action | What happens | Safety tier |
|---|---|---|
| `tabs` | List open tabs | SAFE (auto) |
| `open` / `navigate` | Open a URL / go to a URL | SAFE (auto) |
| `read` | Page text + numbered list of clickable/fillable elements | SAFE (auto) |
| `click` | Click element N from the last read | CAUTION (asks you) |
| `fill` | Type into element N, optionally submit | CAUTION (asks you) |
| `close_tab` | Close a tab | CAUTION (asks you) |

Everything is DOM-level text — no screenshots, so it's fast and cheap.

## Config

- Change the port with the `OPERATOR_BROWSER_PORT` env var **and** `BRIDGE_URL`
  at the top of `background.js` (they must match).
- Chrome blocks extensions from scripting special pages (`chrome://…`, the
  Web Store); OPERATOR gets a clear error on those instead of results.
