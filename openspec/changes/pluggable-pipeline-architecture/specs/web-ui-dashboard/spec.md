## ADDED Requirements

### Requirement: Local FastAPI Dashboard Server
The system SHALL run an embedded FastAPI server on localhost for dashboard and pipeline controls. The default port SHALL be 8888 and MUST be configurable through CLI arguments and `config.json`.

#### Scenario: Start dashboard server
- **WHEN** the user launches the application in UI mode
- **THEN** the FastAPI server starts on the configured localhost port
- **AND** serves the dashboard static files.

### Requirement: Pipeline REST Controls
The system SHALL expose local REST routes to start, pause, resume, step, inspect, and configure the pipeline.

#### Scenario: Pause and resume pipeline
- **WHEN** the dashboard sends pause and resume requests
- **THEN** the backend updates the orchestrator state
- **AND** broadcasts the updated state to connected clients.

### Requirement: WebSocket State Broadcasting
The system SHALL broadcast real-time pipeline status through WebSockets, including active stage, completed assets, remaining assets, elapsed time, speed, log lines, prompts, failures, and safety alerts.

#### Scenario: Real-time progress update
- **WHEN** a stage starts, processes an asset, emits a log line, pauses, fails, or completes
- **THEN** the backend broadcasts a JSON event over WebSockets
- **AND** the dashboard updates without a page refresh.

### Requirement: Interactive Node Graph Visualization
The system SHALL render the pipeline DAG in the dashboard as a node graph with clear visual states for pending, active, paused, complete, and failed nodes.

#### Scenario: Visual graph rendering
- **WHEN** the user opens the dashboard
- **THEN** the dashboard retrieves or receives the pipeline graph
- **AND** renders connected stage nodes with the current active node highlighted.

### Requirement: React Vite Static Frontend
The dashboard frontend SHALL be implemented as a Vite + React application using React Flow for the stage graph and Tailwind CSS for styling. The compiled static bundle SHALL be committed and served by FastAPI without requiring Node.js at runtime.

#### Scenario: Serve dashboard assets
- **WHEN** the browser requests the dashboard
- **THEN** FastAPI serves the compiled Vite static bundle directly.

#### Scenario: Runtime does not require Node.js
- **WHEN** the user launches the dashboard through the Python application
- **THEN** the app runs from the committed static bundle
- **AND** does not invoke `npm`, `vite`, or another Node.js build command.

### Requirement: Interactive Prompt Handling
The system SHALL support prompts that pause pipeline execution and collect user decisions through the dashboard.

#### Scenario: Unknown camera prompt
- **WHEN** an unknown camera model is detected
- **THEN** the pipeline pauses
- **AND** the dashboard displays a prompt for a camera shorthand symbol
- **AND** the answer is persisted to `config.json`
- **AND** the pipeline resumes after submission.

#### Scenario: RAW developer manual completion
- **WHEN** a staged external RAW development workflow requires user completion
- **THEN** the dashboard displays a waiting prompt
- **AND** the pipeline resumes only after the user confirms completion.

#### Scenario: Collision prompt
- **WHEN** filename collision rules produce an ambiguous result
- **THEN** the dashboard displays both file paths, timestamps, sizes, and available actions
- **AND** the selected action is sent back to the backend before the stage continues.

### Requirement: Critical Safety Alert HUD
The dashboard SHALL display high-importance warning states when `SafetyValidationStage` detects missing files, MD5 mismatches, or zero-byte outputs.

#### Scenario: Show catastrophic safety failure
- **WHEN** the backend broadcasts a `CatastrophicSafetyError`
- **THEN** the dashboard displays a critical alert
- **AND** the pipeline controls indicate the run is halted.
