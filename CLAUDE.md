# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Goal

An OctoPrint plugin that shows the spool weights reported by the FilamentScale device (sibling project `../FilamentScale`, ESP8266 firmware).

Placement: a slim left sidebar panel (`TemplatePlugin` template type `sidebar`). The navbar was rejected because it is already full. Keep the panel compact: one row per calibrated sensor showing the label and grams.

## Development

There are no automated tests. To check changes, run the plugin in a throwaway OctoPrint instance:

```
python -m venv venv && venv\Scripts\pip install octoprint && venv\Scripts\pip install -e .
venv\Scripts\octoprint serve --basedir <temp dir> --port 5055
```

Look for `octoprint.plugins.filamentscale` lines in the console log. The plugin's API (`/api/plugin/filamentscale`) answers 403 without a login.

## Layout

- `octoprint_filamentscale/__init__.py`: the single plugin class. A `RepeatedTimer` polls `/api/weights`, keeps only calibrated sensors, and calls `send_plugin_message` only when the state changes. `on_api_get` returns the cached state, so a newly opened page doesn't have to wait for the next change. Changing settings restarts the timer.
- `static/js/filamentscale.js`: a Knockout view model bound to `#sidebar_plugin_filamentscale`. It fetches the state on startup or login, then follows plugin messages.
- `templates/filamentscale_sidebar.jinja2` and `filamentscale_settings.jinja2`: the settings template uses the default settings binding (`settings.plugins.filamentscale.*`). Templates are autoescaped.

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
