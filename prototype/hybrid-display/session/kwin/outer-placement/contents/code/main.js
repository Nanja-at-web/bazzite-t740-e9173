/* Experimental private-session script; tests never load it into real KWin. */
(function () {
    "use strict";
    var gaming = readConfig("GamingOutput", "");
    var side = readConfig("SideOutput", "");
    var receipt = readConfig("Receipt", "");
    var selected = null;
    var failed = false;
    var deadline = new QTimer();
    deadline.interval = 60000;
    deadline.singleShot = true;

    function fail() {
        if (failed) return;
        failed = true;
        deadline.stop();
        console.warn("HYBRID_OUTER_FAIL_V1:" + receipt);
        if (selected !== null) selected.closeWindow();
    }
    function target() {
        var screens = workspace.screens;
        if (screens.length !== 2 || gaming === side) return null;
        var a = screens[0].geometry, b = screens[1].geometry;
        if (!(a.x + a.width <= b.x || b.x + b.width <= a.x ||
              a.y + a.height <= b.y || b.y + b.height <= a.y)) return null;
        var found = null;
        var sides = 0;
        for (var i = 0; i < screens.length; i++) {
            var screen = screens[i];
            if (!(screen.geometry.width > 0 && screen.geometry.height > 0)) return null;
            if (screen.name === gaming) {
                if (found !== null) return null;
                found = screen;
            } else if (screen.name === side) {
                sides++;
            } else return null;
        }
        return sides === 1 ? found : null;
    }
    function identity(window) {
        return window.normalWindow === true && window.resourceClass === "gamescope" &&
            (window.resourceName === "gamescope" || window.resourceName === "") &&
            window.desktopFileName === "gamescope" &&
            window.pid > 0;
    }
    function added(window) {
        if (failed || window.normalWindow !== true) return;
        if (!identity(window)) {
            if (selected === null) fail();
            return;
        }
        if (selected !== null) { fail(); return; }
        selected = window;
        window.closed.connect(function () {
            selected = null;
            fail();
        });
        var output = target();
        if (output === null) { fail(); return; }
        try {
            workspace.sendClientToScreen(window, output);
            if (window.output !== output) { fail(); return; }
            window.fullScreen = true;
            if (window.output !== output || window.fullScreen !== true) { fail(); return; }
            deadline.stop();
            // Internal check only, not an external or same-UID authority receipt.
        } catch (error) { fail(); }
    }
    if (!/^[A-Za-z0-9_-]{1,32}$/.test(gaming) ||
            !/^[A-Za-z0-9_-]{1,32}$/.test(side) ||
            !/^[A-Za-z0-9_-]{1,64}$/.test(receipt)) { fail(); return; }
    if (target() === null) { fail(); return; }
    var initial = workspace.windowList();
    for (var i = 0; i < initial.length; i++) {
        if (initial[i].normalWindow === true) { fail(); return; }
    }
    workspace.windowAdded.connect(added);
    workspace.screensChanged.connect(function () {
        if (target() === null || (selected !== null && selected.output !== target())) fail();
    });
    deadline.timeout.connect(fail);
    deadline.start();
    console.warn("HYBRID_OUTER_READY_V1:" + receipt);
}());
