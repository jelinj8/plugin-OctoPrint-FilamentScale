$(function () {
    function FilamentScaleViewModel(parameters) {
        var self = this;

        self.loginState = parameters[0];

        self.online = ko.observable(false);
        self.error = ko.observable("");
        self.sensors = ko.observableArray([]);
        self.saved = ko.observable(null);
        self.scaleUrl = ko.observable("");

        self.update = function (data) {
            self.online(data.online);
            self.error(data.error || "");
            self.sensors(data.sensors || []);
            self.saved(data.saved || null);
            self.scaleUrl(data.scaleUrl || "");
        };

        self.formatGrams = function (grams) {
            return grams.toFixed(1) + " g";
        };

        // Change since the saved snapshot, empty when nothing is saved for this sensor
        self.formatDelta = function (sensor) {
            var saved = self.saved();
            if (!saved || saved.grams[String(sensor.id)] === undefined) return "";
            var delta = Math.round((sensor.grams - saved.grams[String(sensor.id)]) * 10) / 10;
            var sign = delta > 0 ? "+" : delta < 0 ? "−" : "";
            return sign + Math.abs(delta).toFixed(1) + " g";
        };

        self.savedTime = ko.pureComputed(function () {
            var saved = self.saved();
            return saved ? new Date(saved.time * 1000).toLocaleString() : "";
        });

        self.fetchState = function () {
            if (!self.loginState.isUser()) return;
            OctoPrint.simpleApiGet("filamentscale").done(self.update);
        };

        self.command = function (command, errorText) {
            OctoPrint.simpleApiCommand("filamentscale", command, {})
                .done(self.update)
                .fail(function () {
                    new PNotify({title: "FilamentScale", text: errorText, type: "error"});
                });
        };

        self.save = function () {
            self.command("save", gettext("Could not save the weights."));
        };

        self.clearSaved = function () {
            self.command("clear", gettext("Could not clear the saved weights."));
        };

        self.onStartupComplete = self.fetchState;
        self.onUserLoggedIn = self.fetchState;

        self.onDataUpdaterPluginMessage = function (plugin, data) {
            if (plugin !== "filamentscale") return;
            self.update(data);
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: FilamentScaleViewModel,
        dependencies: ["loginStateViewModel"],
        // The wrapper contains both the header buttons and the panel body
        elements: ["#sidebar_plugin_filamentscale_wrapper"]
    });
});
