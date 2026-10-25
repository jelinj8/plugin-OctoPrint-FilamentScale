$(function () {
    function FilamentScaleViewModel(parameters) {
        var self = this;

        self.loginState = parameters[0];
        self.settingsViewModel = parameters[1];

        self.online = ko.observable(false);
        self.error = ko.observable("");
        self.sensors = ko.observableArray([]);
        self.saved = ko.observable(null);
        self.hidden = ko.observableArray([]);
        self.scaleUrl = ko.observable("");

        self.visibleSensors = ko.pureComputed(function () {
            var hidden = self.hidden();
            return _.filter(self.sensors(), function (sensor) {
                return !_.contains(hidden, sensor.id);
            });
        });

        // Settings page rows. They are kept across updates (only their observables change),
        // so the inputs aren't re-rendered and cleared while the user is typing.
        self.rows = ko.observableArray([]);

        self.update = function (data) {
            self.online(data.online);
            self.error(data.error || "");
            self.sensors(data.sensors || []);
            self.saved(data.saved || null);
            self.hidden(data.hidden || []);
            self.scaleUrl(data.scaleUrl || "");
            self.syncRows(data.sensors || []);
        };

        self.syncRows = function (sensors) {
            var byId = {};
            _.each(self.rows(), function (row) {
                byId[row.id] = row;
            });

            var rows = _.map(sensors, function (sensor) {
                var row = byId[sensor.id];
                if (!row) {
                    return self.createRow(sensor);
                }
                // Follow a rename made elsewhere, unless the user is editing the name here
                if (row.labelInput() === row.label()) row.labelInput(sensor.label);
                row.label(sensor.label);
                row.grams(sensor.grams);
                return row;
            });

            var ids = function (list) {
                return _.pluck(list, "id").join(",");
            };
            if (ids(rows) !== ids(self.rows())) self.rows(rows);
        };

        self.createRow = function (sensor) {
            var row = {
                id: sensor.id,
                label: ko.observable(sensor.label),
                grams: ko.observable(sensor.grams),
                labelInput: ko.observable(sensor.label),
                valueInput: ko.observable("")
            };
            // The Show checkbox reads the hidden list and writes straight to the server
            row.shown = ko.pureComputed({
                read: function () {
                    return !_.contains(self.hidden(), row.id);
                },
                write: function (shown) {
                    self.command(
                        "sethidden",
                        {sensor: row.id, hidden: !shown},
                        gettext("Could not change the sensor visibility.")
                    ).fail(function () {
                        // Put the checkbox back to the actual state
                        row.shown.notifySubscribers(row.shown());
                    });
                }
            });
            return row;
        };

        // Typographic minus, same as in the deltas; rounding first avoids "−0.0"
        self.formatGrams = function (grams) {
            var rounded = Math.round(grams * 10) / 10;
            return (rounded < 0 ? "−" : "") + Math.abs(rounded).toFixed(1) + " g";
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

        self.command = function (command, data, errorText) {
            return OctoPrint.simpleApiCommand("filamentscale", command, data || {})
                .done(self.update)
                .fail(function (xhr) {
                    var detail = xhr.responseJSON && xhr.responseJSON.error;
                    new PNotify({
                        title: "FilamentScale",
                        // The detail can come from the scale, so never treat it as HTML
                        text: detail ? errorText + " " + detail : errorText,
                        text_escape: true,
                        type: "error"
                    });
                });
        };

        // Sidebar header

        self.save = function () {
            self.command("save", {}, gettext("Could not save the weights."));
        };

        self.clearSaved = function () {
            self.command("clear", {}, gettext("Could not clear the saved weights."));
        };

        // Settings page

        self.rename = function (row) {
            self.command(
                "setlabel",
                {sensor: row.id, label: row.labelInput()},
                gettext("Could not rename the sensor.")
            ).done(function () {
                // The scale may have shortened the name, or replaced an empty one
                row.labelInput(row.label());
            });
        };

        self.tare = function (row) {
            showConfirmationDialog({
                message: _.sprintf(
                    gettext('Tare "%(label)s"? Its current reading becomes 0 g.'),
                    {label: _.escape(row.label())}
                ),
                proceed: gettext("Tare"),
                onproceed: function () {
                    self.command("tare", {sensor: row.id}, gettext("Could not tare the sensor."));
                }
            });
        };

        self.setValue = function (row) {
            var grams = parseFloat(String(row.valueInput()).replace(",", "."));
            if (isNaN(grams)) return;
            self.command(
                "setvalue",
                {sensor: row.id, grams: grams},
                gettext("Could not set the weight.")
            ).done(function () {
                row.valueInput("");
            });
        };

        self.renameOnEnter = function (row, event) {
            if (event.keyCode === 13 && row.labelInput() !== row.label()) self.rename(row);
            return true;
        };

        self.setValueOnEnter = function (row, event) {
            if (event.keyCode === 13 && row.valueInput() !== "") self.setValue(row);
            return true;
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
        dependencies: ["loginStateViewModel", "settingsViewModel"],
        // The sidebar wrapper contains both the header buttons and the panel body
        elements: ["#sidebar_plugin_filamentscale_wrapper", "#settings_plugin_filamentscale"]
    });
});
