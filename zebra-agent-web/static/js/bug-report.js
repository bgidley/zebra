/*
 * Technical context for the "Report a bug" dialog (#186).
 *
 * Loaded in <head> without defer so it sees errors from page load onwards.
 * It keeps the last few JS errors (window.onerror, unhandled promise
 * rejections, console.error) and failed HTMX requests in memory; nothing is
 * sent anywhere until the user submits a report. Cookies and storage are
 * never read.
 */
(function () {
    "use strict";

    var LIMIT = 20;
    var TEXT_LIMIT = 2000;
    var errors = [];
    var failedRequests = [];

    function now() {
        return new Date().toISOString();
    }

    function clip(value) {
        var text = value == null ? "" : String(value);
        return text.length > TEXT_LIMIT ? text.slice(0, TEXT_LIMIT) + "…" : text;
    }

    function push(list, entry) {
        list.push(entry);
        if (list.length > LIMIT) list.shift();
    }

    function describe(value) {
        if (value instanceof Error) return value.name + ": " + value.message;
        if (typeof value === "object") {
            try { return JSON.stringify(value); } catch (e) { return String(value); }
        }
        return String(value);
    }

    window.addEventListener("error", function (event) {
        push(errors, {
            at: now(),
            kind: "error",
            message: clip(event.message),
            source: clip(event.filename),
            line: event.lineno,
            column: event.colno,
            stack: clip(event.error && event.error.stack),
        });
    });

    window.addEventListener("unhandledrejection", function (event) {
        var reason = event.reason;
        push(errors, {
            at: now(),
            kind: "unhandledrejection",
            message: clip(describe(reason)),
            stack: clip(reason && reason.stack),
        });
    });

    var originalConsoleError = console.error;
    console.error = function () {
        try {
            push(errors, {
                at: now(),
                kind: "console.error",
                message: clip(Array.prototype.map.call(arguments, describe).join(" ")),
            });
        } catch (e) { /* never break logging */ }
        return originalConsoleError.apply(console, arguments);
    };

    function recordRequest(kind) {
        return function (event) {
            var detail = event.detail || {};
            var xhr = detail.xhr || {};
            var config = detail.requestConfig || {};
            push(failedRequests, {
                at: now(),
                kind: kind,
                method: config.verb ? config.verb.toUpperCase() : undefined,
                path: (detail.pathInfo && detail.pathInfo.requestPath) || config.path,
                status: xhr.status,
                response: clip(xhr.responseText).slice(0, 500),
            });
        };
    }
    document.addEventListener("htmx:responseError", recordRequest("response"));
    document.addEventListener("htmx:sendError", recordRequest("network"));

    window.ZebraBugReport = {
        /** Snapshot of what the browser knows about this page right now. */
        collect: function () {
            var nav = window.navigator || {};
            var tz;
            try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { tz = null; }
            return {
                collected_at: now(),
                url: window.location.href,
                title: document.title,
                referrer: document.referrer,
                user_agent: nav.userAgent,
                language: nav.language,
                online: nav.onLine,
                time_zone: tz,
                viewport: { width: window.innerWidth, height: window.innerHeight },
                screen: window.screen ? { width: screen.width, height: screen.height } : null,
                device_pixel_ratio: window.devicePixelRatio,
                color_scheme: window.matchMedia &&
                    window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark",
                seconds_on_page: Math.round(performance.now() / 1000),
                errors: errors.slice(),
                failed_requests: failedRequests.slice(),
            };
        },
    };
})();
