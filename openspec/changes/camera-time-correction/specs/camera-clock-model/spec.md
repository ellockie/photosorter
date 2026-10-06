## ADDED Requirements

### Requirement: Timezone configuration schema
The system SHALL load camera-time rules from `timezone.json` in the repository root. The file has these keys:
- `home`: country or IANA zone
- `mobiles`: list of camera symbols
- `trips`: list of `{country, from, to}`
- `camera_clocks`: list of `{camera, from?, counter?, clock}`
- `calibrations`: list of `{camera, reading, true}`

Stamps SHALL be parsed by the single stamp grammar (`stamps.py`). Calibration stamps MAY carry a `.fff` fraction. The keys of the superseded schema (`zones`, `locations`, `camera_clock_sets`) SHALL be rejected with a message naming the replacement keys.

#### Scenario: Load a valid file
- **WHEN** `timezone.json` holds `home`, `mobiles`, `trips`, `camera_clocks` and `calibrations` in the documented shapes
- **THEN** the configuration loads with no validation messages

#### Scenario: Reject the superseded schema
- **WHEN** `timezone.json` contains `camera_clock_sets` or `locations`
- **THEN** loading fails with a message naming `camera_clocks` and `trips` as their replacements

#### Scenario: Empty file is identity
- **WHEN** `timezone.json` has no trips, camera clocks or calibrations
- **THEN** every reading maps to a stamp equal to the reading

### Requirement: Country to zone resolution
The system SHALL resolve an ISO-3166 alpha-2 country to its IANA zone using the `iso3166.tab` and `zone1970.tab` tables shipped with `tzdata`. A country with more than one zone SHALL be rejected unless it is given as an IANA region name, and the rejection SHALL list the candidate regions. DST rules SHALL come from the resolved zone and SHALL never be typed by the user.

#### Scenario: Single-zone country
- **WHEN** a trip names `JP`
- **THEN** the trip zone is `Asia/Tokyo`

#### Scenario: Multi-zone country needs a region
- **WHEN** a trip names `US`
- **THEN** validation fails and lists regions such as `America/New_York` and `America/Los_Angeles`

#### Scenario: Home DST is automatic
- **WHEN** `home` is `GB`
- **THEN** home local time is UTC+0 in winter and UTC+1 between the last Sundays of March and October

### Requirement: Clock states
Each `camera_clocks` entry SHALL carry one of these clock states:

| State | The camera's clock follows |
|---|---|
| `home` | the home zone, with its DST |
| `local` | the zone the user was in at the entry's `from`, resolved once at that moment, with that zone's DST |
| `home-winter` | home's standard UTC offset, fixed |
| `home-summer` | home's daylight UTC offset, fixed |
| a country or IANA zone | that zone, with its DST |
| a `±HH:MM` offset | that offset, fixed |

#### Scenario: DST-off camera in summer
- **WHEN** camera `ILC7R5` is `home-winter`, home is `GB`, and a shot reads 2026-07-01 12:00:00
- **THEN** its local stamp is 2026-07-01 13:00:00

#### Scenario: Local stays on the trip zone after return
- **WHEN** a camera is set `local` at a reading inside a JP trip and has no later entry
- **THEN** its shots after the trip are still interpreted as Tokyo time

### Requirement: Camera clock segments and defaults
A camera's entries, ordered by `from`, SHALL divide its readings into segments. An entry without `from` SHALL cover the camera from its first shot. The implicit segment before a camera's first entry SHALL have state `home` and zero error. `from` SHALL be the first reading shown after the adjustment. Validation SHALL warn when consecutive entries imply a true time that goes backwards, the signature of a `from` recorded in the old clock frame.

Cameras listed in `mobiles` SHALL always be treated as showing correct local time with zero error. A `camera_clocks` entry or calibration naming a mobile SHALL be a validation error.

#### Scenario: Outside any trip, no record means no shift
- **WHEN** a camera has no entries and a shot falls outside every trip
- **THEN** its stamp equals its reading

#### Scenario: Inside a trip, no record means home time
- **WHEN** a camera has no entries and a shot reads 2026-04-12 09:00:00 during a JP trip, with home `GB` (BST)
- **THEN** its stamp is 2026-04-12 17:00:00

#### Scenario: Mobile is never shifted
- **WHEN** a mobile's shot falls inside a trip
- **THEN** its stamp equals its reading

#### Scenario: Old-frame boundary warns
- **WHEN** an entry's `from` implies a true instant earlier than the previous entry's
- **THEN** validation warns that `from` must be the first reading after the adjustment

### Requirement: Calibration error
A calibration SHALL yield an error for the segment containing its reading. The error is the reading's UTC instant (interpreted in the segment's state) minus the `true` stamp's UTC instant (interpreted in the location zone at that moment), rounded to whole seconds.

- A segment's error SHALL be taken from the calibration nearest in reading.
- The error SHALL apply constantly across the whole segment. For a camera's first segment, that runs back to the camera's first shot.
- A segment with no calibration SHALL have zero error.
- When two calibrations in one segment differ by more than 2 s, validation SHALL warn.
- When an error's magnitude is 15 minutes or more, validation SHALL warn and suggest the state that leaves the smallest remainder.

#### Scenario: Acceptance pair, before the sync
- **WHEN** `ILC7R5` is `home-winter` from its first shot, with a calibration reading `2026-09-27_(Sun)__19.08.31.774` true `2026-09-27_(Sun)__20.09.52.208`, home `GB`
- **THEN** the segment error is −80 s
- **AND** reading 2026-09-27 19:08:31 maps to stamp `2026-09-27_(Sun)__20.09.51`

#### Scenario: Acceptance pair, after the sync
- **WHEN** `ILC7R5` is `local` from `2026-09-27_(Sun)__20.20.58` with a calibration reading `2026-09-27_(Sun)__20.20.58.925` true `2026-09-27_(Sun)__20.20.59.934`
- **THEN** the segment error is −1 s
- **AND** reading 2026-09-27 20:20:58 maps to stamp `2026-09-27_(Sun)__20.20.59`

#### Scenario: Wrong state suggested
- **WHEN** the same pre-sync calibration is given while the camera's state is `home`
- **THEN** validation warns that the error is about −1 h 01 m and suggests `home-winter`

### Requirement: Reading to local stamp
The system SHALL compute a shot's stamp as follows:
1. Take the raw `Date/Time Original` reading.
2. Apply the camera segment's state and error to get a UTC instant.
3. Find the location zone at that instant: the trip zone between a trip's `from` and `to` (both in the trip zone's local time), otherwise home.
4. Convert the instant to local wall time in that zone and truncate to whole seconds.

The camera SHALL be identified from the EXIF model, never from the filename. Declared in-camera offsets (`OffsetTimeOriginal`) SHALL NOT influence the result.

#### Scenario: Declared offset ignored
- **WHEN** a shot declares `+01:00` but its camera's configured state is `home-winter`
- **THEN** the stamp follows `home-winter`

#### Scenario: No reading
- **WHEN** a shot has no `Date/Time Original`
- **THEN** no stamp is computed for it

### Requirement: Backward-adjustment overlap
When an adjustment moves a camera's clock backwards, a reading in the repeated interval SHALL be assigned by shutter counter when both the entry and the shot carry one. Otherwise it SHALL be assigned to the post-adjustment segment and flagged ambiguous.

#### Scenario: Counter disambiguates
- **WHEN** an entry has `counter` 5000 and a repeated reading belongs to a shot with counter 4998
- **THEN** that shot is interpreted in the pre-adjustment segment

#### Scenario: No counter
- **WHEN** neither carries a counter
- **THEN** the shot is interpreted in the post-adjustment segment and reported as ambiguous
