## ADDED Requirements

### Requirement: Folder Intake With Don't-Move Exclusion
The system SHALL accept both loose media files and folders containing media in the intake folders (`INBOX` and, during migration, the legacy `____TO_SORT\____UNSORTED`). A top-level folder named `__DONT_MOVE` MUST be excluded entirely: the pipeline never reads, moves, renames, or deletes anything inside it. The exclusion applies at the top level of the intake folder only.

#### Scenario: Ingest media from a subfolder
- **WHEN** the intake folder contains a subfolder with media files
- **THEN** the pipeline ingests those files recursively
- **AND** each file records the containing folder it came from.

#### Scenario: Skip the don't-move folder
- **WHEN** the intake folder contains a top-level folder named `__DONT_MOVE`
- **THEN** the pipeline does not enumerate, move, or modify any file inside it
- **AND** the folder itself remains in place untouched.

### Requirement: Origin Label Extraction and Persistence
The system SHALL derive an origin label for every file ingested from a subfolder: the containing folder's name with any leading date or date-time part stripped. Files lying directly in the intake folder have no origin label. The origin label and original path MUST be persisted to a durable run journal (one record per file, including MD5) before the file is moved, so provenance survives crashes and restarts.

#### Scenario: Strip date prefix from folder name
- **WHEN** a file is ingested from a folder named `2024-01-15 Birthday`
- **THEN** its origin label is `Birthday`.

#### Scenario: Strip date-time prefix from folder name
- **WHEN** a file is ingested from a folder named `2024-01-15_18.30 Party`
- **THEN** its origin label is `Party`.

#### Scenario: Persist provenance before moving
- **WHEN** an ingested file is about to be moved out of its origin folder
- **THEN** a journal record with origin path, origin label, and MD5 exists on disk first.

### Requirement: Labeled Event Folder Naming
The system SHALL name the final event/date folder of a labeled file `YYYY-MM-DD_(Ddd) - {origin label}` instead of the generic legacy suffix. Labeled and unlabeled files sharing the same capture date MUST be sorted into separate event folders; the system MUST NOT merge differently labeled groups, because same-date folders may represent different events.

#### Scenario: Sort labeled file into labeled event folder
- **WHEN** a file with origin label `Birthday` and capture date 2024-01-15 is sorted
- **THEN** it lands in `2024-01-15_(Mon) - Birthday/`.

#### Scenario: Keep same-date groups separate
- **WHEN** files with origin label `Birthday` and files without a label share capture date 2024-01-15
- **THEN** labeled files land in `2024-01-15_(Mon) - Birthday/`
- **AND** unlabeled files land in the generic `2024-01-15_(Mon) - 1. ######/`
- **AND** neither group is moved into the other.

### Requirement: Pre-existing Metadata File Travel
The system SHALL discover metadata files that already exist next to an ingested image — most importantly `._exif` sidecars matched by full filename (`IMG_001.jpg` ↔ `IMG_001.jpg._exif`) — register them as sidecars of the corresponding `MediaAsset`, and move them together with the image through every rename, move, and sort operation.

#### Scenario: Carry an existing exif sidecar from a subfolder
- **WHEN** an ingested image has a matching `._exif` file in its origin folder
- **THEN** the sidecar is registered on the asset at ingest time
- **AND** after final sorting the sidecar resides in the event folder's `__EXIF` subfolder under the image's final name.

#### Scenario: Move folder-level geodata with the group
- **WHEN** an origin folder contains a folder-level geodata file such as a GPX track
- **THEN** that file travels to the `__GEOLOCATIONS` subfolder of the event folder(s) derived from that origin folder.
