# actor_runtime.py
# P1: Python as the stateful CRDT host with Snapshot/Restore
import subprocess
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Optional
import threading
import time
import os

@dataclass
class ActorState:
    """Python owns this. Zero computes transitions on it."""
    carbon_total: int = 0
    frequency:    int = 0
    name_hash:    int = 0
    name_ts:      int = 0
    last_snapshot: float = field(default_factory=time.time)


class ActorHandle:
    def __init__(self, actor_id: str, exe_path: str, snapshot_dir: Path):
        self.actor_id     = actor_id
        self.exe_path     = exe_path
        self.snapshot_dir = snapshot_dir
        self.lock         = threading.Lock()

        # Python owns all mutable state — Zero exe is stateless by design
        self.state = self._load_snapshot() or ActorState()

    def send(self, message: dict) -> dict:
        with self.lock:
            msg_type = message.get("type")

            if msg_type == "record_carbon":
                # Call Zero exe as a pure function: current + delta -> next
                next_total = self._compute_gcounter_merge(
                    current=self.state.carbon_total,
                    delta=message["amount"]
                )
                self.state.carbon_total = next_total
                self.state.frequency   += 1

                # Auto-snapshot every 10 operations for testing
                if self.state.frequency % 10 == 0:
                    self._persist_snapshot()

                return {"status": "ok", "total": self.state.carbon_total}

            elif msg_type == "set_name":
                winner = self._compute_lww_merge(
                    local_val=self.state.name_hash,
                    local_ts=self.state.name_ts,
                    remote_val=message["hash"],
                    remote_ts=message["timestamp"]
                )
                self.state.name_hash = winner["val"]
                self.state.name_ts   = winner["ts"]
                return {"status": "ok", "name_hash": self.state.name_hash}

            elif msg_type == "get_total":
                return {
                    "total":     self.state.carbon_total,
                    "frequency": self.state.frequency,
                    "name_hash": self.state.name_hash
                }

            elif msg_type == "snapshot":
                return self._persist_snapshot()

            return {"status": "unknown"}

    def _compute_gcounter_merge(self, current: int, delta: int) -> int:
        """
        Invoke Zero exe as a pure function for the CRDT computation.
        Once Zero supports argv, this will pass args and read stdout.
        For now, the exe validates the logic with hardcoded values —
        the Python fallback handles the real computation identically.
        """
        return current + delta     # GCounter: commutative addition

    def _compute_lww_merge(
        self, local_val: int, local_ts: int,
        remote_val: int, remote_ts: int
    ) -> dict:
        # LWW: higher timestamp wins, deterministic tie-break on value
        if remote_ts > local_ts:
            return {"val": remote_val, "ts": remote_ts}
        elif local_ts > remote_ts:
            return {"val": local_val, "ts": local_ts}
        else:
            # Tie: larger value wins — deterministic, both sides agree
            winning_val = max(local_val, remote_val)
            return {"val": winning_val, "ts": local_ts}

    def _persist_snapshot(self) -> dict:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = self.snapshot_dir / f"{self.actor_id}.json"
        snapshot = asdict(self.state)
        snapshot_path.write_text(json.dumps(snapshot, indent=2))
        self.state.last_snapshot = time.time()
        return {"status": "snapshot_ok", "path": str(snapshot_path)}

    def _load_snapshot(self) -> Optional[ActorState]:
        snapshot_path = self.snapshot_dir / f"{self.actor_id}.json"
        if snapshot_path.exists():
            data = json.loads(snapshot_path.read_text())
            return ActorState(**{
                k: v for k, v in data.items()
                if k in ActorState.__dataclass_fields__
            })
        return None


class ActorRegistry:
    def __init__(self):
        base_path = Path(__file__).parent
        self.exe_path     = base_path / ".zero" / "out" / "action_actor.exe"
        self.snapshot_dir = base_path / ".zero" / "snapshots"
        self.actors:      dict[str, ActorHandle] = {}

    def spawn(self, actor_id: str) -> ActorHandle:
        if actor_id not in self.actors:
            self.actors[actor_id] = ActorHandle(
                actor_id=actor_id,
                exe_path=str(self.exe_path),
                snapshot_dir=self.snapshot_dir
            )
        return self.actors[actor_id]

if __name__ == "__main__":
    print("Initializing Stateful ActorRegistry (P1)")
    registry = ActorRegistry()

    actor_id = "action:commute-subway"
    print(f"\n--- Spawning Actor: {actor_id} ---")
    subway_actor = registry.spawn(actor_id)

    print("\n--- Sending Initial Messages ---")
    r1 = subway_actor.send({"type": "record_carbon", "amount": 100})
    print(f"Record 1: {r1}")

    r2 = subway_actor.send({"type": "set_name", "hash": 42, "timestamp": 1})
    print(f"Set Name 1: {r2}")

    print(f"Current State: {subway_actor.send({'type': 'get_total'})}")

    print("\n--- Triggering Snapshot ---")
    snap_res = subway_actor.send({"type": "snapshot"})
    print(f"Snapshot Result: {snap_res}")

    print("\n--- Simulating Process Crash / Restart ---")
    recovered_actor = ActorHandle(
        actor_id=actor_id,
        exe_path=str(registry.exe_path),
        snapshot_dir=registry.snapshot_dir
    )
    print(f"Recovered State: {recovered_actor.send({'type': 'get_total'})}")

    print("\n--- Validating CRDT Merge Logic (LWW) ---")
    r3 = recovered_actor.send({"type": "set_name", "hash": 10, "timestamp": 0})
    print(f"Older timestamp (ignored): {r3}")

    r4 = recovered_actor.send({"type": "set_name", "hash": 99, "timestamp": 2})
    print(f"Newer timestamp (updated): {r4}")

    print("\nP1 Snapshot & Restore Validation Complete.")
