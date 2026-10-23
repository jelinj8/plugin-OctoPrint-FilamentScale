import threading

import requests

import octoprint.plugin
from octoprint.util import RepeatedTimer


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
        self._state = {"online": False, "error": "Not polled yet", "sensors": []}

    # Polling

    def on_after_startup(self):
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
        url = self._settings.get(["url"]).rstrip("/") + "/api/weights"
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
            state = {"online": True, "error": None, "sensors": sensors}
        except Exception as e:
            state = {"online": False, "error": str(e), "sensors": []}

        with self._lock:
            if state == self._state:
                return
            if state["online"] != self._state["online"]:
                if state["online"]:
                    self._logger.info("FilamentScale reachable at %s", url)
                else:
                    self._logger.warning("FilamentScale unreachable: %s", state["error"])
            self._state = state

        self._plugin_manager.send_plugin_message(self._identifier, state)

    # SimpleApiPlugin: lets a freshly loaded page fetch the current state

    def is_api_protected(self):
        return True

    def on_api_get(self, request):
        import flask

        with self._lock:
            return flask.jsonify(self._state)

    # SettingsPlugin

    def get_settings_defaults(self):
        return {
            "url": "http://filamentscale.local",
            "interval": 2.0,
            "timeout": 3.0,
        }

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self._start_polling()

    # TemplatePlugin / AssetPlugin

    def get_template_configs(self):
        return [
            {"type": "sidebar", "name": "Filament", "icon": "balance-scale"},
            {"type": "settings", "custom_bindings": False},
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
