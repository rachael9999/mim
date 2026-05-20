# mim
An AI-Native, Decentralized, Graph-Actor Micro-Database powered by [Zero](https://zerolang.ai/).

## The Vision
Traditional databases (MySQL, PostgreSQL, MongoDB) were designed for human programmers. They have massive drivers, complex query languages, and heavy memory footprints. **mim** is designed exclusively for AI Agents. 

Instead of a centralized monolith, `mim` treats every entity as a living, autonomous "cell" (Actor) weighing just a few kilobytes. Agents communicate with these cells asynchronously. It is a database without tables, without global locks, and without a central server.

## Core Architecture

`mim` is built on a revolutionary 3-layer architecture:

### 1. CRDT Primitives (Lock-Free Concurrency)
AI Agents operate concurrently and unpredictably. Instead of traditional database locks, `mim` uses Conflict-free Replicated Data Types (CRDTs) baked into the Zero language layer.
- **G-Counter**: Grow-only counters for aggregations (e.g., tracking total carbon emissions).
- **LWW-Register**: Last-Write-Wins registers for scalar state updates.
- **OR-Set**: Observed-Remove sets for collections.
*Math guarantees eventual consistency, no matter the message order.*

### 2. Graph-Native Schema with Vectors
There are no relational tables. Data is stored as a network of **Nodes** and **Edges**.
Crucially, edges carry **Vector Embeddings**. When an Agent asks to "find similar behaviors," the engine doesn't do a SQL `JOIN`—it walks the graph using cosine similarity across the edge embeddings.

### 3. The Actor Model
Every node in the graph is an independent micro-process (an Actor) compiled via the Zero language into a tiny ~2KB executable (and eventually WASM). 
Actors receive JSON messages, update their internal CRDT state, and can persist themselves to disk when idle. 

## Current Implementation Status

- [x] **P0: Zero CRDT & Compilation Pipeline**: Zero compiler toolchain validated. Implemented core CRDT merge logic as pure mathematical functions. Zero emits ultra-lightweight binaries (1.5 KiB).
- [x] **P1: Host Actor Runtime (Python)**: Implemented `ActorRegistry` to manage the lifecycles of autonomous processes. Built state snapshot and recovery mechanisms to persist Actor states (JSON dumps) and survive process crashes.
- [ ] **P2: Graph-Native Semantic Traversal**: Implement Edge embeddings and vector-based semantic traversal across the Actor network.
- [ ] **P3: Full WASM Sandbox Transition**: Transition from native executables to isolated WASM modules with `asyncify` message loops.

## Repository Structure

```text
mim/
├── .zero/
│   ├── out/           # Compiled Zero binaries (Actors)
│   └── snapshots/     # Persisted Actor state (JSON)
├── zero/
│   ├── stdlib/
│   │   └── crdt.0     # Core CRDT mathematical primitives
│   └── actors/
│       └── action_actor.0  # Prototype Action entity Actor
├── actor_runtime.py   # Python Host Runtime & Message Bus
└── README.md
```

## Getting Started

1. **Install Zero Compiler**: Ensure you have the Zero language installed (`zerolang.ai`).
2. **Compile the Actors**:
   ```bash
   mkdir -p .zero/out/zero/actors
   zero build zero/actors/action_actor.0
   ```
3. **Run the Host Runtime**:
   ```bash
   python actor_runtime.py
   ```
   This will spin up the simulated Actor network, push concurrent messages, validate the CRDT merge logic, and test the Snapshot/Restore flow.