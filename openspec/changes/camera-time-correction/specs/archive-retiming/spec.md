## ADDED Requirements

### Requirement: Retime plan
The system SHALL plan retiming per dated folder. For each shot whose computed stamp differs from the stamp in its name, the plan lists:
- the current and target names
- the target day folder, applying the day boundary (N7) to the target stamp
- every companion and sidecar of the shot's unit (X10)
- an ambiguity flag (backward-adjustment overlap)
- a hand-rename flag, when the current stamp matches neither the raw reading nor the target

One planner SHALL serve both intake and the restructure tool.

#### Scenario: Plan for the calibration folder
- **WHEN** the acceptance configuration is planned against the calibration folder
- **THEN** the plan renames `…19.08.31…` to `…20.09.51…` and `…20.20.58…` to `…20.20.59…`, each with its `__RAW` file and both `__EXIF` sidecars
- **AND** the day folder is unchanged

#### Scenario: Hand-renamed shot flagged
- **WHEN** a shot's name stamp equals neither its reading nor its target
- **THEN** the plan marks it "renamed by hand?"

### Requirement: Per-folder confirmation
Before re-dating any shot, the system SHALL ask once per affected folder, offering:
- **yes**
- **yes to all remaining folders**: holds for the rest of the invocation
- **no**: leaves the folder untouched; it is asked again on a later run

The question SHALL show the folder, per camera the state, error and total shift with example renames, any day-folder moves, and the name-order verdict. The restructure tool SHALL prompt in the terminal. Intake SHALL prompt through the dashboard prompt mechanism. A dry run SHALL report plans without prompting. The restructure tool's assume-yes switch SHALL count as "yes to all".

#### Scenario: Yes to all
- **WHEN** the user answers "yes to all" at the first of five folders
- **THEN** all five are retimed without further questions

#### Scenario: No
- **WHEN** the user answers "no"
- **THEN** no file in that folder is renamed or moved

#### Scenario: Dry run
- **WHEN** the restructure tool runs without `--apply`
- **THEN** every plan is reported and nothing is asked or changed

### Requirement: Standard-compliant moves
Applying a plan SHALL:
- rename and move each shot together with all of its companions and sidecars at every level (X10)
- resolve name collisions through the sibling rule (F9) and then the collision rules (F4)
- never rewrite a dated folder's date (N6)

A shot whose target day differs SHALL move to the sibling dated folder carrying the same description, creating that folder in the month folder its date belongs to (P5) if it does not exist.

#### Scenario: Shot crosses the day boundary
- **WHEN** a shot reading 03:50:00 on 2026-07-02 in `2026-07-01_(Wed)__… - Party` is shifted +1 h
- **THEN** it becomes 04:50:00 and moves, with its companions, into a `2026-07-02_(Thu)… - Party` folder

#### Scenario: Crosses into another month
- **WHEN** a shift moves a shot's day from 2026-09-30 to 2026-10-01
- **THEN** the target folder is created under `2026\10. October`

### Requirement: Idempotent and reversible
Target stamps SHALL always be computed from the untouched EXIF reading. EXIF in media files SHALL never be written. A shot already at its target SHALL be left alone. Removing configuration entries and re-running SHALL move shots back toward their raw-reading names.

#### Scenario: Second run is a no-op
- **WHEN** retiming is applied and then run again with the same configuration
- **THEN** the second run plans no changes

#### Scenario: Revert by config
- **WHEN** a camera's entries are removed and retiming is re-run
- **THEN** its shots are planned back to their raw-reading stamps

### Requirement: Name-order verdict
For each planned folder, the system SHALL compare the order of its shots by true instant with their order by target name, and SHALL report any shots that differ. Nothing SHALL be reordered.

#### Scenario: Westward seam
- **WHEN** an in-flight shot stamped 16:00 (home zone) and a landed shot stamped 13:45 (trip zone) share a folder
- **THEN** the folder is reported as out of order, naming both shots

### Requirement: Intake integration
The `timezone-and-travel` stage SHALL compute stamps through the engine before renaming. It SHALL group shifted shots by proposed event folder and ask per folder. Shots in a declined folder SHALL be named on their raw reading and listed in the run log for a later restructure. Trip labels SHALL NOT be written into filenames.

#### Scenario: Declined at intake
- **WHEN** the user answers "no" for a proposed folder during intake
- **THEN** its shots are named from their raw readings and logged as pending retime

### Requirement: Restructure step 0
The restructure tool SHALL run retiming as step 0, "Re-time shots", before step 1, keeping existing step numbers. It SHALL accept optional `--from`/`--to` reading bounds. Steps 1, 5 and 6 SHALL then recompute folder times (N3) and group spans (C11). If zone data cannot be loaded, step 0 SHALL be skipped with an error banner and the remaining steps SHALL still run. `src/retime_archive.py` SHALL be removed.

#### Scenario: Step 0 alone
- **WHEN** the tool runs with `--steps 0 --apply` over a year
- **THEN** only retiming happens, with per-folder prompts

#### Scenario: No zone data
- **WHEN** neither the interpreter nor the project venv provides `tzdata`
- **THEN** step 0 is skipped with an error and steps 1–8 run
