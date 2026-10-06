/*
 * The camera time calculator's arithmetic -- a browser copy of
 * timezone_engine.calculate() (src/pipeline_stages/timezone_engine.py).
 *
 * A second spelling of the same rule, which T8 allows only because a page
 * opened from disk cannot run Python. It is held to the engine by test:
 * tests/test_time_calculator.py runs tests/fixtures/time_vectors.json through
 * this file with Node and compares every answer. Change one, change both.
 *
 * Zones come from the browser's own time-zone database (Intl), so DST is exact
 * and nothing is typed. Errors are whole seconds, camera minus truth, rounded
 * half away from zero; a stamp is truncated to the second.
 */
(function (root) {
  "use strict";

  var WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var STATES = ["home", "home-winter", "home-summer", "local"];
  // stamps.STAMP_CAPTURE_PATTERN plus the F9 fraction (stamps.SUBSECOND_PATTERN).
  var STAMP_RE = /^(\d{4})-(\d{2})-(\d{2})(?:[ _]+\([A-Za-z]{3}\))?[ _]+(\d{2})\.(\d{2})\.(\d{2})(?:\.(\d{1,6}))?/;
  var ISO_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?/;
  var TIME_RE = /^(\d{1,2})[:.](\d{2})[:.](\d{2})(?:\.(\d{1,6}))?$/;
  var OFFSET_RE = /^([+-])(\d{1,2}):(\d{2})$/;
  var formatters = {};

  function fractionMs(digits) {
    return digits ? Math.floor(parseInt((digits + "000000").slice(0, 6), 10) / 1000) : 0;
  }

  // A stamp as a "wall" millisecond count (the wall clock read as if it were UTC).
  function parseStamp(text) {
    text = String(text || "").trim();
    var m = STAMP_RE.exec(text) || ISO_RE.exec(text);
    if (!m) return null;
    return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6], fractionMs(m[7]));
  }

  // A bare time of day ("20:09:52.208") as milliseconds since midnight, or null.
  function parseTime(text) {
    var m = TIME_RE.exec(String(text || "").trim());
    if (!m) return null;
    return ((+m[1] * 60 + +m[2]) * 60 + +m[3]) * 1000 + fractionMs(m[4]);
  }

  function pad(n, w) { n = String(n); while (n.length < (w || 2)) n = "0" + n; return n; }

  function formatStamp(wall) {
    var d = new Date(wall);
    return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()) +
      "_(" + WEEKDAYS[d.getUTCDay()] + ")__" + pad(d.getUTCHours()) + "." + pad(d.getUTCMinutes()) + "." +
      pad(d.getUTCSeconds());
  }

  function formatStampFraction(wall) {
    var ms = ((wall % 1000) + 1000) % 1000;
    return formatStamp(wall) + (ms ? "." + pad(ms, 3) : "");
  }

  // Offset of a zone at a UTC instant, in milliseconds.
  function offsetAt(zone, utc) {
    var f = formatters[zone];
    if (!f) {
      f = formatters[zone] = new Intl.DateTimeFormat("en-US", {
        timeZone: zone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit"
      });
    }
    var parts = {};
    f.formatToParts(new Date(utc)).forEach(function (p) { parts[p.type] = p.value; });
    var wall = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour % 24, +parts.minute, +parts.second);
    var whole = utc - (((utc % 1000) + 1000) % 1000);
    return Math.round((wall - whole) / 60000) * 60000;
  }

  // Wall time in a zone -> UTC, the way Python's zoneinfo does with fold=0: in a
  // repeated hour the first occurrence, in a skipped hour the offset before it.
  function wallToUtc(zone, wall) {
    var before = offsetAt(zone, wall - 12 * 3600000);
    var after = offsetAt(zone, wall + 12 * 3600000);
    var first = wall - before;
    if (offsetAt(zone, first) === before) return first;
    var second = wall - after;
    if (offsetAt(zone, second) === after) return second;
    return first;
  }

  function utcToWall(zone, utc) { return utc + offsetAt(zone, utc); }

  function winterSummer(zone, year) {
    var a = offsetAt(zone, Date.UTC(year, 0, 15, 12)), b = offsetAt(zone, Date.UTC(year, 6, 15, 12));
    return [Math.min(a, b), Math.max(a, b)];
  }

  function fixedOffset(text) {
    var m = OFFSET_RE.exec(String(text || "").trim());
    if (!m) return null;
    var ms = (+m[2] * 60 + +m[3]) * 60000;
    return m[1] === "-" ? -ms : ms;
  }

  // A clock state as {zone} (with that zone's DST) or {offset(year)} (fixed).
  function clockFor(state, home, location) {
    if (state === "home") return { zone: home };
    if (state === "local") return { zone: location };
    if (state === "home-winter" || state === "home-summer") {
      return { fixed: function (year) { return winterSummer(home, year)[state === "home-winter" ? 0 : 1]; } };
    }
    var offset = fixedOffset(state);
    if (offset !== null) return { fixed: function () { return offset; } };
    return { zone: state };  // an IANA zone the page has already resolved
  }

  function clockUtc(clock, wall) {
    if (clock.zone) return wallToUtc(clock.zone, wall);
    return wall - clock.fixed(new Date(wall).getUTCFullYear());
  }

  function roundSeconds(ms) {
    var seconds = ms / 1000;
    return (seconds < 0 ? -1 : 1) * Math.floor(Math.abs(seconds) + 0.5) || 0;
  }

  /*
   * opts: home, location (IANA zones), reading (stamp, fraction allowed),
   * reference (true local stamp, or a bare time), state, error (seconds).
   * With a reference the state leaving the smallest remainder is inferred.
   */
  function calculate(opts) {
    var home = opts.home, location = opts.location;
    var reading = parseStamp(opts.reading);
    if (reading === null) throw new Error("The camera reading is not a stamp like 2026-09-27_(Sun)__19.08.31");
    var state = opts.state || "home", error = +opts.error || 0, remainderMs = null, trueWall = null;
    if (opts.reference !== undefined && opts.reference !== null && String(opts.reference).trim() !== "") {
      var candidates = [];
      var ref = parseStamp(opts.reference);
      if (ref !== null) {
        candidates.push(ref);
      } else {
        var time = parseTime(opts.reference);
        if (time === null) throw new Error("The reference is neither a stamp nor a time like 20:09:52.208");
        var day = reading - (((reading % 86400000) + 86400000) % 86400000);
        [-86400000, 0, 86400000].forEach(function (shift) { candidates.push(day + shift + time); });
      }
      var best = null;
      candidates.forEach(function (candidate) {
        var trueUtc = wallToUtc(location, candidate);
        STATES.forEach(function (name) {
          var remainder = clockUtc(clockFor(name, home, location), reading) - trueUtc;
          if (best === null || Math.abs(remainder) < Math.abs(best.remainder)) {
            best = { state: name, remainder: remainder, trueWall: candidate };
          }
        });
      });
      state = best.state; error = roundSeconds(best.remainder); remainderMs = best.remainder; trueWall = best.trueWall;
    }
    var clock = clockFor(state, home, location);
    var whole = reading - (((reading % 1000) + 1000) % 1000);
    var stamp;
    if (clock.zone && clock.zone === location) {
      stamp = whole - error * 1000;
    } else {
      stamp = utcToWall(location, clockUtc(clock, whole) - error * 1000);
    }
    return {
      state: state, error: error, stamp: formatStamp(stamp), remainderMs: remainderMs,
      reading: formatStampFraction(reading), trueStamp: trueWall === null ? null : formatStampFraction(trueWall),
      shiftSeconds: Math.round((stamp - whole) / 1000)
    };
  }

  function formatDuration(seconds) {
    var sign = seconds < 0 ? "-" : "+";
    seconds = Math.abs(seconds);
    var h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
    if (h) return sign + h + "h " + pad(m) + "m " + pad(s) + "s";
    if (m) return sign + m + "m " + pad(s) + "s";
    return sign + s + "s";
  }

  var api = {
    calculate: calculate, parseStamp: parseStamp, formatStamp: formatStamp, offsetAt: offsetAt,
    formatDuration: formatDuration, STATES: STATES
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TimeCalc = api;
})(this);
