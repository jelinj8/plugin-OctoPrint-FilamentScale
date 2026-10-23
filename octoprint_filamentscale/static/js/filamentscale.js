$(function () {
    function FilamentScaleViewModel(parameters) {
        var self = this;

        self.loginState = parameters[0];

        self.online = ko.observable(false);
        self.error = ko.observable("");
        self.sensors = ko.observableArray([]);

        self.update = function (data) {
            self.online(data.online);
            self.error(data.error || "");
            self.sensors(data.sensors || []);
        };

        self.formatGrams = function (grams) {
            return grams.toFixed(1) + " g";
        };

        self.fetchState = function () {
            if (!self.loginState.isUser()) return;
            OctoPrint.simpleApiGet("filamentscale").done(self.update);
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
        elements: ["#sidebar_plugin_filamentscale"]
    });
});
