# Query
Design an architecture of a python app that processes photos, for example fetches them, extracts exif files, renames, extracts RAW files, clusters them, stores in dated folders, renames etc. Design it to be easily pluggable - so at any moment a new processing stage can be added, that gets some expected, standard (across the app) input metadata and produces some standard output metadata, while in the meantime doing it's job. It would be good to be able to monitor the progress in some GUI. Make it easy to test each "module" / "plugin" / "processing stage"

# Answer

To design an architecture for a Python photo processing app that's easily extendable, we can use a plug-and-play approach where each processing stage is treated as a separate module or plugin. Each module will take a standardized input, process the data, and produce a standardized output, allowing for flexibility in adding, removing, or reordering steps. Below is an architectural outline that fulfills these requirements.

---

### Key Elements of the Architecture

1. **Core Framework**:
    - **Pipeline Manager**: Central controller that manages the sequential processing stages.
    - **Metadata Standard**: A unified format (e.g., JSON) that will hold metadata information as the data passes through each stage.
    - **Event Bus/System**: For communication between modules and the core framework, allowing for progress tracking, error handling, etc.
    - **Plugin Interface**: Defines the required methods any plugin must implement, ensuring consistency across the app.
    - **Task Queue**: A mechanism to manage and queue individual tasks.

2. **Modules/Plugins**:
    - Each module handles one specific processing task (e.g., fetching photos, extracting EXIF, renaming files, clustering, storing).
    - Modules can be dynamically added or removed.
    - Use a consistent input/output format for metadata.

3. **Storage/Repository**:
    - Interface for interacting with storage, abstracting away filesystem specifics.
    - Handles dated folders, renaming, and file serialization.

4. **GUI**:
    - Provides feedback to the user.
    - Monitors the progress of the pipeline execution.
    - Allows the user to start/stop the pipeline processing, handle errors, etc.
  
5. **Testing Framework**:
    - Unit tests for each module.
    - Integration tests for the entire pipeline.
    - Mock-based testing system to simulate input/output data for individual modules.

---

### 1. Core Framework

#### Pipeline Manager
```python
class PipelineManager:
    def __init__(self):
        self.plugins = []

    def add_plugin(self, plugin):
        if isinstance(plugin, BasePlugin):
            self.plugins.append(plugin)

    def run(self, initial_metadata):
        metadata = initial_metadata
        for plugin in self.plugins:
            metadata = plugin.process(metadata)
        return metadata
```

#### Metadata Standard
Metadata is passed between plugins in a standardized format, e.g., a Python dictionary:

```python
{
    "input_file": "path/to/image.jpg",
    "exif_data": {},
    "cluster_id": null,
    "errors": [],
    // Additional metadata captured at various stages
}
```

#### Event Bus/System
```python
class EventBus:
    def __init__(self):
        self.subscribers = {}

    def subscribe(self, event_type, callback):
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)

    def publish(self, event_type, data=None):
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                callback(data)
```

#### Plugin Interface
```python
from abc import ABC, abstractmethod

class BasePlugin(ABC):
    
    @abstractmethod
    def process(self, metadata):
        pass
```

### 2. Modules/Plugins

Separate modules for each step in the pipeline:
 
#### Example: Fetch Photos Plugin
```python
import glob

class FetchPhotosPlugin(BasePlugin):
    def process(self, metadata):
        photos = glob.glob(metadata["photo_directory"] + "/*.jpg")
        metadata["input_files"] = photos
        return metadata
```

#### Example: Extract EXIF Plugin
```python
from PIL import Image
from PIL.ExifTags import TAGS

class ExtractExifPlugin(BasePlugin):
    def process(self, metadata):
        exif_data = {}
        for file in metadata["input_files"]:
            image = Image.open(file)
            info = image._getexif()
            if info:
                exif = {TAGS.get(tag): value for tag, value in info.items()}
                exif_data[file] = exif
        metadata["exif_data"] = exif_data
        return metadata
```

### 3. Storage/Repository

#### Dated Storage
```python
import os
import shutil
from datetime import datetime

class DatedStorage:
    def __init__(self, base_directory):
        self.base_directory = base_directory

    def store(self, metadata):
        date_folder = datetime.now().strftime('%Y-%m-%d')
        destination_folder = os.path.join(self.base_directory, date_folder)
        os.makedirs(destination_folder, exist_ok=True)

        for file in metadata["input_files"]:
            shutil.move(file, destination_folder)

        metadata["stored_in"] = destination_folder
        return metadata
```

### 4. GUI

#### Simple GUI with Progress Monitoring
A simple tkinter-based GUI or console-based UX can be implemented for monitoring:

```python
from tkinter import *

class AppUI:
    def __init__(self, pipeline_manager):
        self.pipeline_manager = pipeline_manager
        self.root = Tk()
        
    def start_pipeline(self):
        initial_metadata = {"photo_directory": "./photos"}
        results = self.pipeline_manager.run(initial_metadata)
        self.display_results(results)
        
    def display_results(self, metadata):
        result_text = f"Stored in {metadata['stored_in']}"
        label = Label(self.root, text=result_text)
        label.pack()
        
    def run(self):
        start_button = Button(self.root, text="Start", command=self.start_pipeline)
        start_button.pack()
        self.root.mainloop()
```

### 5. Testing Framework

#### Unit Tests
```python
import unittest
from unittest.mock import MagicMock

class TestFetchPhotosPlugin(unittest.TestCase):
    
    def test_fetch_photos(self):
        plugin = FetchPhotosPlugin()
        initial_metadata = {"photo_directory": "./test_photos"}
        
        result = plugin.process(initial_metadata)
        
        self.assertIn("input_files", result)
```

#### Integration Testing
```python
class TestFullPipeline(unittest.TestCase):
    
    def test_pipeline(self):
        metadata = {"photo_directory": "./test_photos"}

        pipeline_manager = PipelineManager()
        pipeline_manager.add_plugin(FetchPhotosPlugin())
        pipeline_manager.add_plugin(ExtractExifPlugin())
        
        result_metadata = pipeline_manager.run(metadata)
        
        self.assertIn("exif_data", result_metadata)
```

---

### Summary

In this architecture:
- **PipelineManager** is responsible for handling the execution flow of the pipeline.
- **Modules/Plugins** can be any stage of processing and follow a standardized interface.
- **DatedStorage** handles the storage of processed files in date-based folders.
- **GUI** (using tkinter or some other framework) provides progress feedback and a way to initialize tasks.
- **Testing System** is in place for both unit and integration testing.

This design encourages modular development and ensures that new processing stages can be added without significantly disrupting existing code, making the application extensible and maintainable.
