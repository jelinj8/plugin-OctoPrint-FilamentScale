# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Goal

An OctoPrint plugin that shows the spool weights reported by the FilamentScale device (sibling project `../FilamentScale`, ESP8266 firmware).

Placement: a slim left sidebar panel (`TemplatePlugin` template type `sidebar`). The navbar was rejected because it is already full. Keep the panel compact: one row per calibrated sensor showing the label, the change since the saved snapshot (if any) and the grams.

## Development

There are no automated tests. To check changes, run the plugin in a throwaway OctoPrint instance:

```
python -m venv venv && venv\Scripts\pip install octoprint && venv\Scripts\pip install -e .
venv\Scripts\octoprint serve --basedir <temp dir> --port 5055
```

Look for `octoprint.plugins.filamentscale` lines in the console log. The plugin's API (`/api/plugin/filamentscale`) answers 403 without a login. To call it from a script, GET `/` first to get the `csrf_token_P<port>` cookie, then send it as the `X-CSRF-Token` header on `POST /api/login` and on commands.

Never test tare/setlabel/setvalue against a scale that is in use: they overwrite its spool readings and names. Point the test instance at a small mock HTTP server that mimics the firmware endpoints instead.

To see the UI, Playwright with the installed Edge works (`p.chromium.launch(channel="msedge")`, no browser download). Plain `msedge --headless --screenshot` captures OctoPrint's loading screen. In a fresh test instance, set `accessControl.autologinLocal`/`autologinAs` so the page is logged in. A first-run wizard dialog covers the page; remove `.modal-scrollable` in the page or dispatch clicks directly.

## Layout

- `octoprint_filamentscale/__init__.py`: the single plugin class. A `RepeatedTimer` polls `/api/weights`, keeps only calibrated sensors, and calls `send_plugin_message` only when the readings change. `on_api_get` returns the cached state, so a newly opened page doesn't have to wait for the next change. The `save`/`clear` API commands manage a snapshot of the weights in `saved.json` in the plugin data folder, so it's shared by all browsers and survives restarts. Every message carries the full state (readings, snapshot, scale URL). Changing settings restarts the timer.
- The `tare`/`setlabel`/`setvalue` API commands are forwarded to the scale's own API and need `Permissions.SETTINGS`. Labels are cut to 31 UTF-8 bytes on a character boundary first, because the firmware's `char[32]` would cut a multi-byte character in half. Calibration deliberately stays in the firmware web UI, which the settings page links to.
- `static/js/filamentscale.js`: one Knockout view model, bound to both `#sidebar_plugin_filamentscale_wrapper` (header buttons and panel body) and `#settings_plugin_filamentscale`. It fetches the state on startup or login, then follows plugin messages. The settings rows (`rows`) are kept across updates and only their observables change; replacing them would re-render the inputs and wipe what the user is typing.
- `templates/`: `filamentscale_sidebar.jinja2` is the panel body. `filamentscale_sidebar_header.jinja2` holds the header buttons (OctoPrint `accordion-heading-button` divs, which float right, so their DOM order is reversed). `filamentscale_settings.jinja2` uses custom bindings, so plugin settings are reached as `settingsViewModel.settings.plugins.filamentscale.*`. Templates are autoescaped.
- Sidebar rows are flex rows, not a table: a table with an ellipsis label column squeezed the values to zero width.

## Device API (source of truth: `../FilamentScale/README.md` and `FilamentScale.ino`)

- Default address: `http://filamentscale.local` on port 80 (mDNS). Users may need to set an IP instead, because mDNS is not always reliable.
- `GET /api/weights` returns `{"sensors":[{"id":1-5,"label","grams","calibrated"}], "avgSize", "displayOn", "sleepThresh", "sleepTimeoutMin", "displayAsleep", "secSinceChange", "lastChangeSensor", "uptimeSec"}`. `grams` is already a rolling average rounded to 0.1 g. Skip sensors with `calibrated:false`; they are empty or unused channels.
- `GET /api/raw` returns raw ADC values and calibration parameters (for debugging).
- POST endpoints take a JSON body: `/api/tare` `{"sensor":n}`, `/api/calibrate` `{"sensor":n,"knownGrams":g}`, `/api/setvalue` `{"sensor":n,"grams":g}`, `/api/setlabel` `{"sensor":n,"label":"..."}`, plus the display and averaging settings. They return `{"success":true}`, or HTTP 400 with `{"success":false,"error":"..."}`.
- `grams` can be negative. This is intentional: if a sensor was tared with a full spool, the reading is the filament consumed.
- Labels are full UTF-8 (Czech text is common).

## Architecture: poll from the server, not the browser

The firmware currently sends no CORS headers. We control it and could add them, but the plugin should still talk to the device from the OctoPrint Python side, because a browser fetch from the frontend breaks in common setups even with CORS:
- If OctoPrint is served over HTTPS (for example behind a reverse proxy), the browser blocks requests to the HTTP-only device as mixed content.
- If OctoPrint is reached remotely (OctoEverywhere, a VPN, port forwarding), the browser is not on the device's LAN.
- Many clients cannot resolve `.local` names.
- Every open browser tab would poll the ESP8266 separately.

The Python side polls the device (for example with `octoprint.util.RepeatedTimer`, about every 2 s, which matches the device's own dashboard) and pushes the data to the UI through `self._plugin_manager.send_plugin_message`. Proxy any write actions (tare, label, and so on) through the plugin's `SimpleApiPlugin`/`BlueprintPlugin` endpoints. We decided not to add CORS to the firmware.

The ESP8266 web server is single-threaded and slow. Keep request timeouts short and never block OctoPrint's main thread on device I/O.
