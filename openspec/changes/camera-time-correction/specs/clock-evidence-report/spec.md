## ADDED Requirements

### Requirement: Report-only evidence
The system SHALL produce a clock evidence report from `__EXIF` sidecars over a chosen root, year or date range. Nothing in the report SHALL change files or configuration or influence stamps. The report SHALL be printed and also written as a text file to the run's log folder.

#### Scenario: Report changes nothing
- **WHEN** the report runs over a year
- **THEN** no file is renamed or moved and `timezone.json` is unchanged

### Requirement: Counter-ordered jump detection
For each non-mobile camera, the report SHALL order shots by shutter counter (`Shutter Count`, else `Image Number` / `File Number`), falling back to reading order when no counter exists. It SHALL report:
- every place where the reading goes backwards while the counter advances, marked as a certain adjustment
- every change in declared `Offset Time Original`, marked as a possible adjustment
- forward reading gaps only when they coincide with one of the above

#### Scenario: Backward jump
- **WHEN** counter 4211 reads 23:58:10 and counter 4212 reads 23:02:44 on the same day
- **THEN** the report lists a certain adjustment of about −56 min between them

#### Scenario: Declared offset change at the calibration
- **WHEN** `ILC7R5` counter 16878 declares `+00:00` and 16879 declares `+01:00`
- **THEN** the report lists a possible adjustment between them

### Requirement: Mobile offset changes
For cameras listed in `mobiles`, the report SHALL list changes in declared offset as likely trip boundaries, with the last stamp before and the first stamp after.

#### Scenario: Trip start
- **WHEN** phone shots change from `+01:00` to `+09:00` between two stamps
- **THEN** the report lists a likely trip start at the first `+09:00` stamp

### Requirement: Paste-ready lines
Every finding SHALL include a ready-to-paste `timezone.json` line built from the actual stamps: a `camera_clocks` entry with `from` and, where known, `counter`; or a `trips` entry with `from` and a placeholder country. Findings already covered by the configuration SHALL be marked "recorded".

#### Scenario: Line for the calibration adjustment
- **WHEN** the report lists the `ILC7R5` adjustment at counter 16879
- **THEN** it prints `{ "camera": "ILC7R5", "from": "2026-09-27_(Sun)__20.20.58", "counter": 16879, "clock": "??" },`

#### Scenario: Already recorded
- **WHEN** `timezone.json` already has an entry for that camera at that `from`
- **THEN** the finding is marked "recorded"
