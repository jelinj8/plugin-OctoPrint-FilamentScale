import json
import math
import os
import threading
import time

import flask
import requests

import octoprint.plugin
from octoprint.access.permissions import Permissions
from octoprint.util import RepeatedTimer

# The firmware stores labels in char[32] and cuts them at the byte limit
LABEL_MAX_BYTES = 31


class FilamentScalePlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
):
    def __init__(self):
        self._timer = None
        self._lock = threading.Lock()
        self._readings = {"online": False, "error": "Not polled yet", "sensors": []}
        # Snapshot taken with the Save button: {"time": epoch, "grams": {"<id>": grams}}
        self._saved = None

    # Polling

    def on_after_startup(self):
        self._saved = self._load_saved()
        self._start_polling()

    def on_shutdown(self):
        self._stop_polling()

    def _start_polling(self):
        self._stop_polling()
        interval = max(1.0, self._settings.get_float(["interval"]))
        self._timer = RepeatedTimer(interval, self._poll, run_first=True)
        self._timer.daemon = True
        self._timer.start()

    def _stop_polling(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _poll(self):
        url = self._scale_url() + "/api/weights"
        timeout = self._settings.get_float(["timeout"])
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            # Uncalibrated channels are empty or unused positions on the scale
            sensors = [
                {"id": s["id"], "label": s["label"], "grams": s["grams"]}
                for s in data.get("sensors", [])
                if s.get("calibrated")
            ]
            readings = {"online": True, "error": None, "sensors": sensors}
        except Exception as e:
            readings = {"online": False, "error": str(e), "sensors": []}

        with self._lock:
            if readings == self._readings:
                return
            if readings["online"] != self._readings["online"]:
                if readings["online"]:
                    self._logger.info("FilamentScale reachable at %s", url)
                else:
                    self._logger.warning("FilamentScale unreachable: %s", readings["error"])
            self._readings = readings
            payload = self._payload()

        self._plugin_manager.send_plugin_message(self._identifier, payload)

    def _scale_url(self):
        return self._settings.get(["url"]).rstrip("/")

    def _payload(self):
        """Full state for the frontend. Call with self._lock held."""
        return dict(self._readings, saved=self._saved, scaleUrl=self._scale_url())

    # Saved snapshot

    def _saved_path(self):
        return os.path.join(self.get_plugin_data_folder(), "saved.json")

    def _load_saved(self):
        try:
            with open(self._saved_path(), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except Exception:
            self._logger.exception("Could not read the saved weights, ignoring them")
            return None

    def _store_saved(self, saved):
        path = self._saved_path()
        if saved is None:
            if os.path.exists(path):
                os.remove(path)
            return
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(saved, f)
        os.replace(tmp, path)

    # SimpleApiPlugin: current state for a freshly loaded page, the Save/Clear commands,
    # and the scale commands from the settings page

    def is_api_protected(self):
        return True

    def on_api_get(self, request):
        with self._lock:
            return flask.jsonify(self._payload())

    def get_api_commands(self):
        return {
            "save": [],
            "clear": [],
            "tare": ["sensor"],
            "setlabel": ["sensor", "label"],
            "setvalue": ["sensor", "grams"],
        }

    def on_api_command(self, command, data):
        if command in ("tare", "setlabel", "setvalue"):
            return self._scale_command(command, data)

        with self._lock:
            if command == "save":
                if not self._readings["online"]:
                    return self._error(409, "The scale is offline")
                saved = {
                    "time": time.time(),
                    "grams": {str(s["id"]): s["grams"] for s in self._readings["sensors"]},
                }
            else:
                saved = None
            self._store_saved(saved)
            self._saved = saved
            payload = self._payload()

        self._plugin_manager.send_plugin_message(self._identifier, payload)
        return flask.jsonify(payload)

    def _scale_command(self, command, data):
        """Forward tare/setlabel/setvalue to the scale's own API."""
        if not Permissions.SETTINGS.can():
            return self._error(403, "Changing the scale needs the Settings permission")

        try:
            body = {"sensor": int(data["sensor"])}
            if command == "setlabel":
                label = str(data["label"]).strip().encode("utf-8")[:LABEL_MAX_BYTES]
                body["label"] = label.decode("utf-8", "ignore")
            elif command == "setvalue":
                body["grams"] = float(data["grams"])
                if not math.isfinite(body["grams"]):
                    raise ValueError
        except (TypeError, ValueError):
            return self._error(400, "Invalid parameters")

        try:
            response = requests.post(
                self._scale_url() + "/api/" + command,
                json=body,
                timeout=self._settings.get_float(["timeout"]),
            )
            result = response.json()
        except Exception as e:
            return self._error(502, "The scale is not reachable: {}".format(e))
        if not result.get("success"):
            return self._error(400, "The scale refused it: {}".format(result.get("error", "unknown error")))

        self._logger.info("Scale command %s %r done", command, body)
        # Show the result right away instead of waiting for the next poll
        self._poll()
        with self._lock:
            return flask.jsonify(self._payload())

    @staticmethod
    def _error(status, message):
        return flask.make_response(flask.jsonify(error=message), status)

    # SettingsPlugin

    def get_settings_defaults(self):
        return {
            "url": "http://filamentscale.local",
            "interval": 2.0,
            "timeout": 3.0,
        }

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        with self._lock:
            payload = self._payload()
        self._plugin_manager.send_plugin_message(self._identifier, payload)
        self._start_polling()

    # TemplatePlugin / AssetPlugin

    def get_template_configs(self):
        return [
            {
                "type": "sidebar",
                "name": "Filament",
                "icon": "balance-scale",
                "template_header": "filamentscale_sidebar_header.jinja2",
            },
            {"type": "settings", "custom_bindings": True},
        ]

    def is_template_autoescaped(self):
        return True

    def get_assets(self):
        return {
            "js": ["js/filamentscale.js"],
            "css": ["css/filamentscale.css"],
        }


__plugin_name__ = "FilamentScale"
__plugin_pythoncompat__ = ">=3,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamentScalePlugin()
