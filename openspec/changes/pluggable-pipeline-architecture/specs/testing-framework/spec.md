## ADDED Requirements

### Requirement: Stage Contract Verification
The system SHALL provide pytest contract tests that verify every `PipelineStage` subclass declares required metadata, accepts a valid `PipelineContext`, returns a valid `PipelineContext`, and preserves required context invariants.

#### Scenario: Verify stage interface contract
- **WHEN** pytest executes contract tests for a pluggable stage
- **THEN** the tests assert stage metadata, dependency declarations, execute return type, and context integrity.

### Requirement: MediaAsset and File Operation Unit Tests
The system SHALL provide unit tests for `MediaAsset` sidecar tracking and Windows-safe file operation helpers.

#### Scenario: Rename asset with sidecars in test fixture
- **WHEN** a test renames a `MediaAsset` with registered sidecars
- **THEN** all files are renamed consistently
- **AND** the sidecar registry points to existing files.

### Requirement: Isolated Sandbox Unit Testing
The system SHALL provide tests proving `StagedWorkspaceStage` isolates target extensions, sweeps generated sidecars, and cleans temporary folders.

#### Scenario: Validate sandbox directory isolation
- **WHEN** sandbox tests run with mixed file extensions
- **THEN** only targeted files are staged
- **AND** non-target files remain untouched.

### Requirement: Collision Resolver Testing
The system SHALL provide unit tests and integration coverage for all name collision rules.

#### Scenario: Validate collision rules
- **WHEN** tests exercise exact MD5, older/larger, significantly-smaller, and ambiguous cases
- **THEN** the resolver returns duplicate suppression, automatic rename, low-resolution duplicate rename, or prompt-required decisions as appropriate.

### Requirement: Safety Validation Testing
The system SHALL provide tests proving the safety validator passes valid runs and halts invalid runs.

#### Scenario: Halt on missing or corrupted output
- **WHEN** a test removes an expected output, changes its MD5, or creates a zero-byte output
- **THEN** `SafetyValidationStage` raises `CatastrophicSafetyError`.

### Requirement: Backend and WebSocket Contract Testing
The system SHALL provide tests for dashboard backend route behavior and WebSocket event payload schemas.

#### Scenario: Validate backend control payloads
- **WHEN** tests call start, pause, resume, state, graph, and prompt-answer routes
- **THEN** responses contain the expected status fields
- **AND** emitted events match documented payload shapes.

### Requirement: End-to-End Pipeline Verification
The system SHALL support E2E tests that execute the default pipeline on isolated dummy photo folders and verify rename, sort, duplicate handling, and final zero-file-loss safety validation.

#### Scenario: E2E sorting and verification run
- **WHEN** an integration test executes the orchestrator with mock files
- **THEN** files are renamed and sorted into expected folders
- **AND** duplicates are safely resolved
- **AND** final safety validation passes.

### Requirement: Legacy Parity Fixture Matrix
The system SHALL provide E2E fixtures that prove the new staged pipeline preserves legacy observable behavior while using the new working folder structure.

#### Scenario: Preserve legacy naming and folder grammar
- **WHEN** mock media is processed through the full staged pipeline
- **THEN** output filenames match the legacy grammar
- **AND** final folders use `{year}\{NN}. {MonthName}\YYYY-MM-DD_(Thu) - 1. ######`.

#### Scenario: Preserve legacy sidecar and RAW placement
- **WHEN** mock media has associated `._exif` sidecars and RAW originals
- **THEN** sidecars land under `__EXIF`
- **AND** RAW originals land under `__RAW`.

#### Scenario: Verify standardized event subfolder taxonomy
- **WHEN** a mock event contains RAW originals, edited masters, extracted alternates, final exports, resized derivatives, duplicates, EXIF sidecars, GPX tracks, and JSON logs
- **THEN** each artifact lands in its required folder: `__RAW`, `__EDITED`, `__EXTRACTED`, `__EXPORTED`, `__RESIZED`, `__DUPLICATES`, or `__EXIF`
- **AND** no non-standard final event subfolder is created for those artifact classes.

#### Scenario: Verify root representative image rule
- **WHEN** a mock shot has multiple versions of the same capture
- **THEN** at most one representative image lands directly in the final event/date folder
- **AND** all supporting versions land in standardized `__` subfolders.

#### Scenario: Verify representative suffix ordering
- **WHEN** a root representative has a RAW original, was extracted from RAW, and has an edited/master version
- **THEN** the representative filename includes `_RAW_EXT_EDT` before the file extension
- **AND** `_RAW` appears first
- **AND** `_EDT` appears last.

#### Scenario: Preserve legacy duplicate naming
- **WHEN** mock files collide by target name
- **THEN** duplicate outputs use `_DUPE_<md5>_<n>` naming.

#### Scenario: Preserve legacy day boundary
- **WHEN** mock media timestamp is before the configured `04.44.44` boundary
- **THEN** it is sorted into the previous date folder.
