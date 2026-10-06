## ADDED Requirements

### Requirement: Offline calculator page
The system SHALL provide a single self-contained HTML page that works offline from a local file, generated from the `tzdata` country tables. It SHALL use the browser's built-in time-zone rules for DST, and SHALL load no external resources.

#### Scenario: Open from disk
- **WHEN** the generated file is opened from disk with no network
- **THEN** every country and region is selectable and calculations work

### Requirement: Calibration mode
Given a camera symbol, a camera reading (a stamp, optionally with `.fff`), a reference, and a location (country or region), the page SHALL infer the clock state that leaves the smallest remainder and report that remainder as a whole-second error. The reference is either:
- the time of a clock visible in the photo, or
- the stamp of a phone photo taken at the same moment

The page SHALL emit paste-ready `calibrations` and `camera_clocks` lines.

#### Scenario: Acceptance pair
- **WHEN** the reading is `2026-09-27_(Sun)__19.08.31.774`, the clock shows 20:09:52.208, and the location is GB
- **THEN** the page infers `home-winter` with error −80 s and local stamp `2026-09-27_(Sun)__20.09.51`
- **AND** emits the matching calibration line

#### Scenario: Phone reference
- **WHEN** the reference is a phone stamp taken at the same moment
- **THEN** the phone stamp is treated as true local time for the chosen location

### Requirement: Translate mode
Given a reading, a location and a chosen clock state (`home`, `home-winter`, `home-summer`, `local`, a country/zone, or an offset) plus an optional error, the page SHALL show the local stamp.

#### Scenario: Translate a DST-off reading
- **WHEN** the reading is 2026-07-01 12:00:00, location GB, state `home-winter`
- **THEN** the page shows `2026-07-01_(Wed)__13.00.00`

### Requirement: Same results as the engine
The page and the Python engine SHALL pass the same shared JSON test vectors, including the acceptance pair.

#### Scenario: Vectors agree
- **WHEN** the test suite runs the shared vectors against both implementations
- **THEN** every vector yields identical stamps, states and errors
