# P8: Memory Extractor Implementation Plan

## Goal
Transform raw dialogue/messages into structured `MemoryActor` operations via a `MemoryExtractor`.

## Proposed Architecture

1.  **Dialogue Representation**:
    *   Define a `Dialogue` class or use a simple list of messages (e.g., `{"role": "user", "content": "..."}`).
    *   `DialogueMessage` schema: `role`, `content`, `timestamp`, `message_id`.

2.  **MemoryExtractor**:
    *   Interface: `extract_memories(dialogue: List[DialogueMessage]) -> List[MemoryOperation]`.
    *   `MemoryOperation`: A simplified representation of what should be created/updated (content, type, tags).
    *   Implementation: `MockMemoryExtractor` using regex/keywords for now.

3.  **MimRuntime Integration**:
    *   Add `runtime.extract_memories(user_id, dialogue)` method.
    *   Handle duplicate extraction: Track which messages have already been processed (e.g., via `last_processed_message_id` or similar in a new `ExtractionState` actor or simple persistent state).

4.  **ExtractorActor (Optional but recommended for consistency)**:
    *   An actor that maintains the state of extraction for a specific conversation/user.

## Tasks

### 1. Define Dialogue and Extractor Interfaces
- [ ] Create `runtime/extractor.py`.
- [ ] Define `DialogueMessage` and `MemoryOperation` dataclasses.
- [ ] Define `BaseExtractor` abstract class.

### 2. Implement Mock Extractor
- [ ] Implement `MockExtractor` in `runtime/extractor.py`.
- [ ] Use keywords like "project:", "todo:", "remember:" to trigger extraction.

### 3. Integrate with MimRuntime
- [ ] Add `extract_memories` to `MimRuntime`.
- [ ] Implement logic to iterate through dialogue, call extractor, and `dispatch` update/create messages.
- [ ] Implement a simple mechanism to avoid re-processing the same dialogue.

### 4. CLI and Demo
- [ ] Add `ingest` command to `cli.py` to simulate a dialogue.
- [ ] Create `examples/memory_extraction_demo.py`.

## Review existing `MemoryActor` fields
- `content`: LWWRegister
- `memory_type`: LWWRegister
- `tags`: ORSet
- `status`: LWWRegister
- `embedding`: LWWRegister

Extractor should target these.
