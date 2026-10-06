r"""Build the offline camera time calculator page (tools\time_calculator.html).

    python tools\build_time_calculator.py

The page turns a clock photo -- or a phone photo taken at the same moment --
into a camera's clock state and whole-second error, translates any reading
into local time, and prints the ``timezone.json`` lines to paste. One file, no
network: the country table is embedded here from ``tzdata`` and DST comes from
the browser. Its arithmetic is ``tools\time_calculator_engine.js``, held to the
Python engine by ``tests\test_time_calculator.py`` (openspec change
camera-time-correction, capability camera-time-calculator).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clock_tools_common import engine  # noqa: E402

TOOLS = Path(__file__).resolve().parent
ENGINE_JS = TOOLS / "time_calculator_engine.js"
OUTPUT = TOOLS / "time_calculator.html"


def country_data() -> dict:
    """``{code: [name, [distinct zones, principal first]]}`` for every country with a zone."""
    names, _ = engine.country_tables()
    data = {}
    for code in sorted(names):
        zones = engine.country_zones(code)
        if zones:
            data[code] = [names[code], zones]
    return data


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Camera time calculator</title>
<style>
:root { --bg:#fbfbf9; --panel:#fff; --fg:#1d1d1b; --muted:#6f6d67; --line:#e2e0da; --accent:#2f6fde; --good:#1f7a3a; --warn:#b4471f; }
@media (prefers-color-scheme: dark) { :root { --bg:#17181a; --panel:#202124; --fg:#e9e7e2; --muted:#a19e96; --line:#34353a; --accent:#7aa7ff; --good:#6cc287; --warn:#ff9a73; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; }
main { max-width:860px; margin:0 auto; padding:20px 16px 48px; }
h1 { font-size:22px; margin:0 0 4px; } p.lede { color:var(--muted); margin:0 0 18px; }
section { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px; margin-bottom:14px; }
h2 { font-size:15px; margin:0 0 10px; }
label { display:block; font-size:13px; color:var(--muted); margin:10px 0 4px; }
input, select { width:100%; font:inherit; padding:7px 9px; border:1px solid var(--line); border-radius:7px; background:var(--bg); color:var(--fg); }
.row { display:grid; grid-template-columns:1fr 1fr; gap:0 14px; }
@media (max-width:600px) { .row { grid-template-columns:1fr; } }
.modes { display:flex; gap:18px; flex-wrap:wrap; } .modes label { display:flex; gap:6px; align-items:center; margin:0; color:var(--fg); font-size:14px; }
.modes input { width:auto; }
.hint { font-size:12px; color:var(--muted); margin-top:3px; }
.result { font-size:26px; font-family:ui-monospace, Consolas, monospace; margin:2px 0 6px; overflow-wrap:anywhere; }
dl { display:grid; grid-template-columns:max-content 1fr; gap:4px 14px; margin:8px 0 0; font-size:14px; } dt { color:var(--muted); } dd { margin:0; font-family:ui-monospace, Consolas, monospace; }
pre { margin:6px 0 0; padding:9px 11px; background:var(--bg); border:1px solid var(--line); border-radius:7px; overflow-x:auto; font-size:13px; }
button { font:inherit; font-size:13px; padding:4px 10px; border-radius:6px; border:1px solid var(--line); background:var(--bg); color:var(--fg); cursor:pointer; }
.error { color:var(--warn); } .ok { color:var(--good); }
.paste-head { display:flex; justify-content:space-between; align-items:center; margin-top:12px; font-size:13px; color:var(--muted); }
.hidden { display:none; }
</style></head><body><main>
<h1>Camera time calculator</h1>
<p class="lede">Turn a photo of a clock (or a phone photo taken at the same moment) into what the camera's clock was set to and how far off it was &mdash; or translate any camera reading into local time. Nothing leaves this page.</p>

<section>
  <div class="modes">
    <label><input type="radio" name="mode" value="calibrate" checked> Calibrate from a clock or phone photo</label>
    <label><input type="radio" name="mode" value="translate"> Translate a reading</label>
  </div>
  <div class="row">
    <div><label for="camera">Camera symbol</label><input id="camera" value="ILC7R5" autocomplete="off"><div class="hint">As in the filename, e.g. ILC7R5, C6D.</div></div>
    <div><label for="home">Home</label><select id="home"></select></div>
  </div>
  <label for="reading">Camera reading</label>
  <input id="reading" placeholder="2026-09-27_(Sun)__19.08.31.774" autocomplete="off">
  <div class="hint">Paste the photo's filename or stamp. Add the sub-second (<code>.774</code>, from <code>Sub Sec Time Original</code>) for a precise calibration.</div>
  <div id="reference-box">
    <label for="reference">True local time at that moment</label>
    <input id="reference" placeholder="20:09:52.208   or   2026-09-27_(Sun)__20.09.52.208" autocomplete="off">
    <div class="hint">The clock visible in the photo, or the stamp of a phone photo taken at the same moment.</div>
  </div>
  <div class="row">
    <div><label for="country">Where you were</label><select id="country"></select></div>
    <div id="region-box" class="hidden"><label for="region">Region</label><select id="region"></select></div>
  </div>
  <div id="state-box" class="hidden">
    <div class="row">
      <div><label for="state">Camera clock</label>
        <select id="state">
          <option value="home">home &mdash; home time, kept up with DST</option>
          <option value="home-winter">home-winter &mdash; home winter time all year (DST off)</option>
          <option value="home-summer">home-summer &mdash; home summer time all year</option>
          <option value="local">local &mdash; set to where I was</option>
          <option value="other">other zone or offset&hellip;</option>
        </select></div>
      <div><label for="error">Error (seconds, camera minus truth)</label><input id="error" type="number" value="0" step="1"></div>
    </div>
    <div id="other-box" class="hidden"><label for="other">Zone or fixed offset</label><input id="other" placeholder="Europe/Warsaw   or   +02:00"></div>
  </div>
</section>

<section aria-live="polite">
  <h2>Local time</h2>
  <div id="out-stamp" class="result">&mdash;</div>
  <div id="out-error" class="error"></div>
  <dl id="out-details"></dl>
  <div id="out-paste"></div>
</section>
</main>
<script>/*ENGINE*/</script>
<script>
var COUNTRIES = /*COUNTRIES*/;
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var codes = Object.keys(COUNTRIES).sort(function (a, b) { return COUNTRIES[a][0].localeCompare(COUNTRIES[b][0]); });
  function fill(select, selected) {
    codes.forEach(function (code) {
      var o = document.createElement("option");
      o.value = code; o.textContent = COUNTRIES[code][0] + " (" + code + ")" + (COUNTRIES[code][1].length > 1 ? " — several zones" : "");
      if (code === selected) o.selected = true;
      select.appendChild(o);
    });
  }
  fill($("home"), "GB"); fill($("country"), "GB");
  try { var saved = JSON.parse(localStorage.getItem("timecalc") || "{}");
    ["camera", "home", "country"].forEach(function (k) { if (saved[k]) $(k).value = saved[k]; }); } catch (e) {}

  function zoneOf(code, region) {
    var zones = COUNTRIES[code][1];
    return zones.length === 1 ? zones[0] : (region || zones[0]);
  }
  function placeName(code, zone) { return COUNTRIES[code][1].length === 1 ? code : zone; }
  function mode() { return document.querySelector("input[name=mode]:checked").value; }

  function updateRegion() {
    var zones = COUNTRIES[$("country").value][1], box = $("region-box"), select = $("region");
    if (zones.length < 2) { box.classList.add("hidden"); return; }
    if (select.dataset.country !== $("country").value) {
      select.innerHTML = ""; select.dataset.country = $("country").value;
      zones.forEach(function (z) { var o = document.createElement("option"); o.value = o.textContent = z; select.appendChild(o); });
    }
    box.classList.remove("hidden");
  }

  function line(obj) { return JSON.stringify(obj).replace(/":/g, "\": ").replace(/,"/g, ", \"").replace(/^\{/, "{ ").replace(/\}$/, " },"); }
  function pasteBlock(title, text) {
    var id = "p" + Math.random().toString(36).slice(2);
    return '<div class="paste-head"><span>' + title + '</span><button data-copy="' + id + '">Copy</button></div><pre id="' + id + '">' +
      text.replace(/&/g, "&amp;").replace(/</g, "&lt;") + "</pre>";
  }

  function run() {
    updateRegion();
    var isCal = mode() === "calibrate";
    $("reference-box").classList.toggle("hidden", !isCal);
    $("state-box").classList.toggle("hidden", isCal);
    $("other-box").classList.toggle("hidden", $("state").value !== "other");
    try { localStorage.setItem("timecalc", JSON.stringify({ camera: $("camera").value, home: $("home").value, country: $("country").value })); } catch (e) {}
    $("out-error").textContent = ""; $("out-details").innerHTML = ""; $("out-paste").innerHTML = ""; $("out-stamp").textContent = "—";
    var reading = $("reading").value.trim();
    if (!reading) return;
    var home = zoneOf($("home").value), location = zoneOf($("country").value, $("region").value);
    var opts = { home: home, location: location, reading: reading };
    if (isCal) {
      if (!$("reference").value.trim()) { $("out-error").textContent = "Enter the true local time to calibrate."; return; }
      opts.reference = $("reference").value;
    } else {
      opts.state = $("state").value === "other" ? $("other").value.trim() : $("state").value;
      opts.error = parseInt($("error").value || "0", 10);
    }
    var r;
    try { r = TimeCalc.calculate(opts); } catch (e) { $("out-error").textContent = e.message; return; }
    $("out-stamp").textContent = r.stamp;
    var camera = $("camera").value.trim() || "CAMERA";
    var details = [["Clock", r.state], ["Error", (r.error >= 0 ? "+" : "") + r.error + " s"],
                   ["Shift applied", TimeCalc.formatDuration(r.shiftSeconds)], ["Zone", location]];
    if (r.remainderMs !== null) details.push(["Measured", (r.remainderMs / 1000).toFixed(3) + " s off (" + r.state + ")"]);
    if (Math.abs(r.error) >= 900) details.push(["Note", "Over 15 min left over: probably a clock setting not listed here"]);
    $("out-details").innerHTML = details.map(function (d) { return "<dt>" + d[0] + "</dt><dd>" + d[1] + "</dd>"; }).join("");
    var clock = r.state === "local" ? "local" : r.state;
    var html = "";
    if (isCal) {
      html += pasteBlock("calibrations — one measurement", line({ camera: camera, reading: r.reading, "true": r.trueStamp }));
      html += pasteBlock("camera_clocks — if not recorded yet (drop “from” to mean “since the first shot”; otherwise use the first reading after you set it)",
        line({ camera: camera, from: r.reading.slice(0, 26), clock: clock }));
    } else if ($("country").value !== $("home").value) {
      html += pasteBlock("trips — if this place is not recorded yet", line({ country: placeName($("country").value, location), from: r.stamp, to: "??" }));
    }
    $("out-paste").innerHTML = html;
  }
  document.addEventListener("input", run);
  document.addEventListener("change", run);
  document.addEventListener("click", function (e) {
    var id = e.target.getAttribute && e.target.getAttribute("data-copy");
    if (!id) return;
    var text = $(id).textContent;
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () {
      e.target.textContent = "Copied"; setTimeout(function () { e.target.textContent = "Copy"; }, 1200);
    }, function () { var range = document.createRange(); range.selectNodeContents($(id)); getSelection().removeAllRanges(); getSelection().addRange(range); });
  });
  run();
})();
</script>
</body></html>
"""


def build() -> str:
    return (PAGE.replace("/*ENGINE*/", ENGINE_JS.read_text(encoding="utf-8"))
            .replace("/*COUNTRIES*/", json.dumps(country_data(), separators=(",", ":"))))


def main() -> int:
    OUTPUT.write_text(build(), encoding="utf-8")
    print(f"Written {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
