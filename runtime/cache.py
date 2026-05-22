import json
import os
import time
import hashlib
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: float
    ttl_sec: int
    graph_version: int
    meta: dict

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_sec


class InsightTTLCache:
    """
    Thread-safe TTL cache for expensive discover/insight results.

    Key strategy:
      user_id + graph_version + params_hash

    Storage:
      - in-memory dict
      - disk persistence as JSON files in .mim_cache/insights
    """

    def __init__(
        self,
        cache_dir: str = ".mim_cache/insights",
        default_ttl_sec: int = 300,
        enable_disk: bool = True,
    ):
        # 确保路径是相对于项目根目录的
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cache_dir = Path(os.path.join(base_dir, cache_dir))

        self.default_ttl_sec = default_ttl_sec
        self.enable_disk = enable_disk
        self._lock = threading.RLock()
        self._store: dict[str, CacheEntry] = {}

        if self.enable_disk:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def make_key(
        self,
        user_id: str,
        graph_version: int,
        params: Optional[dict] = None,
    ) -> str:
        params = params or {}
        raw = json.dumps(
            {
                "user_id": user_id,
                "graph_version": graph_version,
                "params": params,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)

            if entry is None and self.enable_disk:
                entry = self._load_one_from_disk(key)

            if entry is None:
                return None

            if entry.is_expired():
                self.delete(key)
                return None

            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        graph_version: int,
        ttl_sec: Optional[int] = None,
        meta: Optional[dict] = None,
    ) -> None:
        ttl_sec = ttl_sec or self.default_ttl_sec
        meta = meta or {}

        with self._lock:
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                ttl_sec=ttl_sec,
                graph_version=graph_version,
                meta=meta,
            )
            self._store[key] = entry

            if self.enable_disk:
                self._save_one_to_disk(entry)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

            if self.enable_disk:
                path = self._path_for_key(key)
                if path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

            if self.enable_disk and self.cache_dir.exists():
                for path in self.cache_dir.glob("*.json"):
                    try:
                        path.unlink()
                    except OSError:
                        pass

    def stats(self) -> dict:
        with self._lock:
            live = 0
            expired = 0

            for entry in self._store.values():
                if entry.is_expired():
                    expired += 1
                else:
                    live += 1

            return {
                "entries": len(self._store),
                "live": live,
                "expired": expired,
                "disk_enabled": self.enable_disk,
                "cache_dir": str(self.cache_dir),
                "default_ttl_sec": self.default_ttl_sec,
            }

    def _path_for_key(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _save_one_to_disk(self, entry: CacheEntry) -> None:
        path = self._path_for_key(entry.key)
        tmp_path = path.with_suffix(".tmp")

        payload = asdict(entry)

        try:
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)
        except Exception:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    def _load_one_from_disk(self, key: str) -> Optional[CacheEntry]:
        path = self._path_for_key(key)

        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entry = CacheEntry(**data)

            if entry.is_expired():
                try:
                    path.unlink()
                except OSError:
                    pass
                return None

            self._store[key] = entry
            return entry
        except Exception:
            return None

    def _load_from_disk(self) -> None:
        if not self.cache_dir.exists():
            return

        for path in self.cache_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                entry = CacheEntry(**data)

                if entry.is_expired():
                    path.unlink()
                    continue

                self._store[entry.key] = entry
            except Exception:
                continue
