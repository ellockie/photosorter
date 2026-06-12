## ADDED Requirements

### Requirement: Pipeline Context Encapsulation
The system SHALL manage execution state in a single `PipelineContext` object passed between pipeline stages. The context MUST contain active `MediaAsset` objects, loaded configuration, counters, prompt queues, stage states, and the input safety snapshot.

#### Scenario: Unified context passing
- **WHEN** the orchestrator starts a pipeline run
- **THEN** it instantiates one `PipelineContext`
- **AND** each stage receives and returns that context without mutating `src/common/globals.py`.

### Requirement: MediaAsset Relationship Tracking
The system SHALL represent each distinct media item as a `MediaAsset` containing the primary file path and a dictionary of related sidecar paths such as `_exif` files, extracted JPEGs, and converted RAW outputs.

#### Scenario: Move asset with sidecars
- **WHEN** a stage moves a `MediaAsset` to a target directory
- **THEN** the primary file and every registered sidecar are moved together
- **AND** the asset registry is updated to the new paths.

#### Scenario: Rename asset with sidecars
- **WHEN** a stage renames a `MediaAsset`
- **THEN** the primary file and registered sidecars receive corresponding new names
- **AND** no sidecar is orphaned under the previous basename.

### Requirement: Windows-Safe File Operations
The system SHALL centralize rename, move, delete, and MD5 file reads behind retry-aware helpers suitable for Windows file-lock behavior.

#### Scenario: Retry transient file lock
- **WHEN** a file operation fails because a file is temporarily locked
- **THEN** the operation is retried with backoff before failing the stage.

### Requirement: Pluggable DAG Stage Interface
The system SHALL allow developers to add pipeline stages by implementing a `PipelineStage` base interface. Each stage MUST declare identity, display name, dependency metadata, input/output contract metadata, `execute(context)`, and `cleanup(context)`.

#### Scenario: Execute dependency-ordered stage
- **WHEN** the orchestrator runs the DAG
- **THEN** it executes a stage only after all declared dependencies are complete
- **AND** records pending, active, paused, complete, or failed state for UI and CLI reporting.

### Requirement: Staged Workspace Isolation
The system SHALL provide `StagedWorkspaceStage` for stages that must run external tools against clean temporary folders containing only targeted file extensions.

#### Scenario: Clean RAW conversion sandbox
- **WHEN** a staged RAW conversion stage targets `.CR2`, `.CRW`, or `.ARW` files
- **THEN** it stages only eligible primary files into an isolated temporary folder
- **AND** after the external workflow completes, it sweeps produced files back into the relevant `MediaAsset` sidecar maps
- **AND** it cleans the temporary folder.

### Requirement: Dynamic JSON Configuration
The system SHALL load runtime settings from `config.json`, including paths, supported extensions, external tool locations, camera symbols, dashboard port, collision thresholds, legacy naming conventions, problematic folder names, and travel/timezone rules.

#### Scenario: Initialize dynamic configuration
- **WHEN** the pipeline starts
- **THEN** it loads `config.json` or creates defaults
- **AND** binds those values inside `PipelineContext`.

### Requirement: File Safety Snapshot and Verification
The system SHALL guarantee zero file loss or silent corruption for input media files. At startup, it MUST record original path, size, timestamp, and MD5 for every input media file. At completion, `SafetyValidationStage` MUST verify output counts, MD5 identity, and non-zero file size for every original input unless the file is explicitly registered as a safe duplicate or exclusion.

#### Scenario: Validate zero file loss
- **WHEN** the pipeline completes successfully
- **THEN** every input media MD5 has a corresponding output or registered safe exception
- **AND** every corresponding output has the expected MD5
- **AND** no output media file is zero bytes.

#### Scenario: Halt on missing output
- **WHEN** an original input media file cannot be found in final outputs or safe exceptions
- **THEN** the validator raises `CatastrophicSafetyError`
- **AND** the pipeline enters a failed halt state.

#### Scenario: Halt on corrupted output
- **WHEN** a final output path exists but its MD5 differs from the input snapshot
- **THEN** the validator raises `CatastrophicSafetyError`.

### Requirement: Advanced Name Collision Resolution
The system SHALL resolve target filename collisions using deterministic MD5, size, and timestamp rules before any overwrite can occur.

#### Scenario: Suppress exact duplicate
- **WHEN** the existing target file and candidate file have identical MD5 hashes
- **THEN** the redundant file is registered as a safe duplicate
- **AND** no overwrite occurs.

#### Scenario: Keep older larger original
- **WHEN** two files collide and one file is older or equal age and larger or equal size
- **THEN** that file is treated as the original
- **AND** the other file is renamed with a duplicate suffix.

#### Scenario: Auto-classify significantly smaller file
- **WHEN** one colliding file is below the configured size ratio threshold, defaulting to under 50% of the larger file
- **THEN** the smaller file is classified as a low-resolution duplicate
- **AND** it is renamed without pausing the pipeline.

#### Scenario: Pause on ambiguous collision
- **WHEN** a collision cannot be resolved by MD5, older/larger, or significantly-smaller rules
- **THEN** the pipeline pauses
- **AND** a prompt payload is emitted for user resolution.

### Requirement: Legacy Duplicate Suffix Compatibility
The system SHALL preserve the legacy duplicate filename suffix grammar `_DUPE_<md5>_<n>` while applying the advanced collision decision rules.

#### Scenario: Rename existing colliding target
- **WHEN** a target file already exists and is not an exact duplicate
- **THEN** the existing target MAY be renamed to `_DUPE_<existing_md5>_0`
- **AND** the incoming file SHALL use `_DUPE_<incoming_md5>_<n>` when it cannot keep the base name.

### Requirement: Legacy Filename Grammar
The system SHALL preserve the legacy media filename grammar:
`YYYY-MM-DD_(Thu)_HH.MM.SS__{RAW__ optional}f...__T...__L...__I...__CAMERA.ext`.

#### Scenario: Rename image from metadata
- **WHEN** metadata extraction provides timestamp, aperture, exposure, focal length, ISO, camera symbol, and raw status
- **THEN** the rename stage emits the legacy filename grammar
- **AND** RAW files include `RAW__`
- **AND** RAW extensions are uppercase while lossy image extensions are lowercase.

### Requirement: Legacy Date Folder Grouping
The system SHALL preserve legacy date folder grouping and folder naming.

#### Scenario: Create legacy date folder
- **WHEN** a final asset is sorted into the archive
- **THEN** the month folder uses `{NN}. {MonthName}`
- **AND** the date folder uses `YYYY-MM-DD_(Thu) - 1. ######`.

#### Scenario: Apply day boundary cutoff
- **WHEN** a file timestamp is earlier than or equal to the configured day boundary `04.44.44`
- **THEN** the date folder is shifted to the previous calendar day.

### Requirement: Standardized Event Folder Subdirectories
The system SHALL use a standardized `__` prefix subdirectory taxonomy inside every final event/date folder. The taxonomy MUST be the only final event-folder artifact taxonomy used by the stage-based pipeline unless a compatibility import stage is reading old folders.

#### Scenario: Place RAW originals
- **WHEN** a RAW original is sorted into a final event/date folder
- **THEN** it is moved under `__RAW`
- **AND** it remains untouched and unmodified.

#### Scenario: Place edited master artifacts
- **WHEN** a non-destructive edit or master working file such as `.xmp`, `.psd`, or high-bit `.tif` is associated with a shot
- **THEN** it is moved under `__EDITED`.

#### Scenario: Place extracted alternates
- **WHEN** a RAW extraction produces alternate or batch-extracted JPEGs that do not become the root representative image
- **THEN** those files are moved under `__EXTRACTED`.

#### Scenario: Place final exports
- **WHEN** a full-resolution JPEG export is produced for print/archive/export use
- **THEN** it is moved under `__EXPORTED`.

#### Scenario: Place resized derivatives
- **WHEN** a downscaled or compressed derivative is produced for web, social media, email, or temporary sharing
- **THEN** it is moved under `__RESIZED`.

#### Scenario: Place duplicate and discard artifacts
- **WHEN** a file is classified as a burst discard, unused bracket, accidental duplicate, low-resolution duplicate, or collision duplicate
- **THEN** it is moved under `__DUPLICATES`.

#### Scenario: Place metadata sidecars
- **WHEN** a final event/date folder is created
- **THEN** related `._exif` sidecars are moved under `__EXIF`
- **AND** GPX track files and JSON camera logs associated with the event or shot are also stored under `__EXIF`.

### Requirement: Event Folder Representative Images
The system SHALL keep only shot-level representative images directly inside the final event/date folder. Supporting assets MUST be moved to the standardized `__` subfolders.

#### Scenario: Keep straight-from-camera representative at root
- **WHEN** a camera-produced representative image exists for a shot
- **THEN** that image MAY live directly in the event/date folder
- **AND** related RAW, metadata, edited, extracted, exported, resized, and duplicate artifacts SHALL live in standardized `__` subfolders.

#### Scenario: Use extracted representative for RAW-only shot
- **WHEN** a shot has RAW input but no straight-from-camera representative image
- **THEN** one selected RAW extraction MAY live directly in the event/date folder as the representative
- **AND** non-representative extracted alternatives SHALL live under `__EXTRACTED`.

#### Scenario: Avoid multiple root representatives
- **WHEN** multiple files represent the same shot
- **THEN** at most one representative image SHALL live directly in the event/date folder
- **AND** all other versions SHALL be routed to the correct standardized subfolder.

### Requirement: Representative Filename Suffix Semantics
The system SHALL append semantic suffixes to root-level representative image filenames so users can see whether RAW, extracted, or edited/master assets exist without opening subfolders.

#### Scenario: Mark representative with RAW original
- **WHEN** a representative image has a related RAW original under `__RAW`
- **THEN** the representative filename SHALL include `_RAW`
- **AND** `_RAW` SHALL be the first semantic suffix immediately after the base legacy filename stem.

#### Scenario: Mark representative extracted from RAW
- **WHEN** a root-level representative image was extracted or derived from RAW rather than captured straight from the camera
- **THEN** the representative filename SHALL include `_EXT`.

#### Scenario: Mark representative with better edited version
- **WHEN** a better edited/master version exists under `__EDITED`
- **THEN** the representative filename SHALL include `_EDT`
- **AND** `_EDT` SHALL be the final semantic suffix before the file extension.

#### Scenario: Apply deterministic suffix ordering
- **WHEN** more than one representative suffix applies
- **THEN** suffixes SHALL be ordered as `_RAW`, then `_EXT`, then `_EDT`
- **AND** the original file extension SHALL remain after all semantic suffixes.

### Requirement: Legacy Problematic Folder Taxonomy
The system SHALL preserve legacy problematic subfolders for unsupported files, zero-byte files, insufficient metadata, duplicate names, and stale EXIF files.

#### Scenario: Quarantine empty media file
- **WHEN** an input media file is zero bytes
- **THEN** it is moved to `##   EMPTY FILES   ##`
- **AND** it is excluded from normal processing with a registered safety explanation.

#### Scenario: Relocate stale EXIF before regeneration
- **WHEN** a pre-existing `._exif` sidecar is found before ExifTool generation
- **THEN** it is moved to the old-EXIF problematic area before fresh metadata is generated.

### Requirement: New Working Folder With Legacy Concept Mapping
The system SHALL keep the new `____INGEST_PIPELINE` working folder model while preserving legacy pipeline semantics.

#### Scenario: Ingest from legacy camera uploads source
- **WHEN** the upload harvest stage runs
- **THEN** files are read from `c:\Users\luxxa\Dropbox\Camera Uploads\`
- **AND** they are staged into `root_folder\____INGEST_PIPELINE\INBOX\`.

#### Scenario: Read legacy unsorted folder during migration
- **WHEN** legacy compatibility mode is enabled and files exist in `c:\__PHOTOS\____TO_SORT\____UNSORTED\`
- **THEN** the pipeline can import those files into the new `INBOX` without treating the repo working directory as a photo destination.

### Requirement: Default Stage Set
The system SHALL provide default stage implementations for initialization, upload harvesting, stale EXIF relocation, empty-file quarantine, batch ExifTool generation, metadata extraction, timezone/travel correction, rename and sort, staged RAW conversion, folder sorting, and safety validation.

#### Scenario: Run default DAG
- **WHEN** the default pipeline is selected
- **THEN** the orchestrator runs the default stage set in dependency order
- **AND** includes `SafetyValidationStage` before successful completion.

### Requirement: Stage Module Isolation
The system SHALL implement each concrete pipeline stage in its own module so stages can be developed, reviewed, and modified independently. Shared helper modules MAY be used for reusable logic, but stage-specific behavior MUST NOT be concentrated in one monolithic stage implementation file.

#### Scenario: Work on one stage independently
- **WHEN** a developer needs to modify one concrete stage
- **THEN** the stage-specific code is contained in that stage's module
- **AND** the developer does not need to load unrelated stage implementations to understand the local change.

#### Scenario: Preserve transition imports
- **WHEN** existing code imports stage classes through a compatibility module
- **THEN** that module may re-export concrete stages
- **BUT** the concrete implementations remain in separate stage modules.
