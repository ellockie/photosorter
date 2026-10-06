## ADDED Requirements

### Requirement: Scan every photo root
The visualiser SHALL scan every `photo_roots` entry, reading only folder names and `__EXIF` sidecars. It SHALL list dated folders at any nesting depth. Folders with the same path relative to their roots SHALL be merged into one row tagged with every root that holds them. Scans SHALL be cached per root, outside the archive, so that an unchanged folder is not re-read. Filters SHALL be available by year, by date range and by root.

#### Scenario: Merged row
- **WHEN** `2026\09. September\X` exists under both `c:\__PHOTOS` and the NAS root
- **THEN** it appears once, tagged with both roots

#### Scenario: Nested folders
- **WHEN** a group holds dated children three levels deep
- **THEN** every level appears as its own row

### Requirement: Fixed lanes and slots
The view SHALL draw one lane per UTC offset present in the scanned range, ascending, at fixed columns. Each lane SHALL have fixed slots:
- slot 0: a distinct local-time marker
- then one slot per camera, in a global order that does not change between rows

For each row, every camera with shots in the folder SHALL be drawn in the lane of its clock offset, and the local marker in the lane of local time. A camera and the local marker on the same offset SHALL occupy different slots. A camera whose offset changes within a folder SHALL appear in every lane it used, marked as changing.

#### Scenario: Same offset, no overlap
- **WHEN** local time and two cameras are all at UTC+1 in a folder
- **THEN** three distinct symbols appear in the UTC+1 lane

#### Scenario: DST-off camera
- **WHEN** `ILC7R5` is `home-winter` in a BST folder
- **THEN** it is drawn in the UTC+0 lane while the local marker is in UTC+1

### Requirement: Aligned names and depth
Folder names SHALL all start at the same column. Nesting depth SHALL be shown in a separate column before the name. Each row SHALL carry its root tags.

#### Scenario: Alignment
- **WHEN** folders of depth 1 and depth 3 are listed
- **THEN** their names start at the same column and their depth column shows 1 and 3

### Requirement: Rules and annotations
The view SHALL insert full-width rules, in chronological position between rows, for every DST change of home and trip zones and for every trip start and end. Each row SHALL be annotated with:
- whether each camera's state is assumed, configured or calibrated
- the shift that retiming would apply
- the name-order verdict

#### Scenario: DST rule
- **WHEN** the scanned range spans 2026-03-29
- **THEN** a rule "DST GB +0 → +1" appears between the last folder before and the first folder after that moment

#### Scenario: Assumed state
- **WHEN** a camera has no entries inside a trip
- **THEN** its row annotation says it is assumed on home time
