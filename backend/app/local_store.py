"""A tiny, file-backed stand-in for MongoDB.

MongoDB is the primary database of this project (see ``database.py``). This
module exists so the application still runs end-to-end on a machine where no
MongoDB server / Atlas cluster is available yet - which is the normal situation
on a student laptop the first time the project is cloned.

It implements only the subset of the Motor API that this codebase uses, and it
keeps the exact same call signatures, so switching to real MongoDB is a matter
of filling in ``MONGO_URI`` in ``backend/.env``. No aggregation pipelines are
used anywhere in the project precisely so that both backends behave identically.

Documents are persisted as JSON, one file per collection, under
``backend/storage/local_db/``.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

_FLUSH_RETRIES = 5
_FLUSH_RETRY_DELAY = 0.05


def new_id() -> str:
    """Identifiers are UUID strings (not ObjectIds) in both backends."""
    return uuid.uuid4().hex


# --------------------------------------------------------------------------- #
# Query matching
# --------------------------------------------------------------------------- #
def _get_path(document: dict, path: str) -> Any:
    current: Any = document
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _compare(left: Any, right: Any, operator: str) -> bool:
    try:
        if operator == "$gt":
            return left > right
        if operator == "$gte":
            return left >= right
        if operator == "$lt":
            return left < right
        if operator == "$lte":
            return left <= right
    except TypeError:
        return False
    return False


def _match_condition(value: Any, condition: Any) -> bool:
    if isinstance(condition, dict) and any(key.startswith("$") for key in condition):
        for operator, expected in condition.items():
            if operator == "$eq" and value != expected:
                return False
            elif operator == "$ne" and value == expected:
                return False
            elif operator == "$in" and value not in list(expected):
                return False
            elif operator == "$nin" and value in list(expected):
                return False
            elif operator in {"$gt", "$gte", "$lt", "$lte"}:
                if value is None or not _compare(value, expected, operator):
                    return False
            elif operator == "$exists" and (value is not None) != bool(expected):
                return False
            elif operator == "$regex":
                flags = re.IGNORECASE if "i" in condition.get("$options", "") else 0
                if not isinstance(value, str) or not re.search(expected, value, flags):
                    return False
        return True
    return value == condition


def matches(document: dict, query: dict | None) -> bool:
    if not query:
        return True
    for key, condition in query.items():
        if key == "$or":
            if not any(matches(document, sub) for sub in condition):
                return False
        elif key == "$and":
            if not all(matches(document, sub) for sub in condition):
                return False
        elif key == "$nor":
            if any(matches(document, sub) for sub in condition):
                return False
        elif not _match_condition(_get_path(document, key), condition):
            return False
    return True


def apply_update(document: dict, update: dict) -> dict:
    """Apply ``$set`` / ``$unset`` / ``$inc`` / ``$push`` to a document copy."""
    result = json.loads(json.dumps(document))
    for operator, payload in update.items():
        if operator == "$set":
            for key, value in payload.items():
                target, last = result, key
                if "." in key:
                    *parents, last = key.split(".")
                    for parent in parents:
                        target = target.setdefault(parent, {})
                target[last] = value
        elif operator == "$unset":
            for key in payload:
                result.pop(key, None)
        elif operator == "$inc":
            for key, amount in payload.items():
                result[key] = (result.get(key) or 0) + amount
        elif operator == "$push":
            for key, value in payload.items():
                result.setdefault(key, []).append(value)
        elif not operator.startswith("$"):
            result[operator] = payload
    return result


# --------------------------------------------------------------------------- #
# Result objects (mirroring pymongo's result classes)
# --------------------------------------------------------------------------- #
@dataclass
class InsertOneResult:
    inserted_id: Any


@dataclass
class InsertManyResult:
    inserted_ids: list[Any]


@dataclass
class UpdateResult:
    matched_count: int
    modified_count: int
    upserted_id: Any = None


@dataclass
class DeleteResult:
    deleted_count: int


# --------------------------------------------------------------------------- #
# Cursor
# --------------------------------------------------------------------------- #
class LocalCursor:
    def __init__(self, documents: list[dict]):
        self._documents = documents
        self._sort: list[tuple[str, int]] = []
        self._skip = 0
        self._limit = 0

    def sort(self, key_or_list: Any, direction: int = 1) -> "LocalCursor":
        if isinstance(key_or_list, str):
            self._sort.append((key_or_list, direction))
        else:
            self._sort.extend(list(key_or_list))
        return self

    def skip(self, count: int) -> "LocalCursor":
        self._skip = count or 0
        return self

    def limit(self, count: int) -> "LocalCursor":
        self._limit = count or 0
        return self

    def _resolve(self) -> list[dict]:
        documents = list(self._documents)
        for key, direction in reversed(self._sort):
            documents.sort(
                key=lambda doc: _sort_key(_get_path(doc, key)),
                reverse=direction < 0,
            )
        if self._skip:
            documents = documents[self._skip :]
        if self._limit:
            documents = documents[: self._limit]
        return documents

    async def to_list(self, length: int | None = None) -> list[dict]:
        documents = self._resolve()
        if length is not None:
            documents = documents[:length]
        return documents

    def __aiter__(self):
        async def generator():
            for document in self._resolve():
                yield document

        return generator()


def _sort_key(value: Any) -> tuple[int, Any]:
    """Order ``None`` first, then numbers, then everything else as strings."""
    if value is None:
        return (0, "")
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, (int, float)):
        return (1, value)
    return (2, str(value))


# --------------------------------------------------------------------------- #
# Collection / database
# --------------------------------------------------------------------------- #
class LocalCollection:
    def __init__(self, path: Path, lock: asyncio.Lock):
        self._path = path
        self._lock = lock
        self._documents: list[dict] | None = None

    # ---- persistence ----
    def _load(self) -> list[dict]:
        if self._documents is None:
            if self._path.exists():
                try:
                    self._documents = json.loads(self._path.read_text("utf-8"))
                except (json.JSONDecodeError, OSError):
                    self._documents = []
            else:
                self._documents = []
        return self._documents

    def _flush(self) -> None:
        payload = json.dumps(self._documents or [], indent=2, default=str)
        temporary = self._path.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
        temporary.write_text(payload, "utf-8")
        # Cloud-synced folders (OneDrive, Dropbox) and antivirus scanners keep
        # transient handles on these files, which makes the atomic replace fail
        # with PermissionError. Retry briefly, then write in place as a fallback.
        for attempt in range(_FLUSH_RETRIES):
            try:
                temporary.replace(self._path)
                return
            except PermissionError:
                if attempt < _FLUSH_RETRIES - 1:
                    time.sleep(_FLUSH_RETRY_DELAY * (attempt + 1))
        try:
            self._path.write_text(payload, "utf-8")
        finally:
            temporary.unlink(missing_ok=True)

    # ---- reads ----
    async def find_one(self, query: dict | None = None, sort: Any = None) -> dict | None:
        async with self._lock:
            cursor = LocalCursor([doc for doc in self._load() if matches(doc, query)])
            if sort:
                cursor.sort(sort)
            found = await cursor.limit(1).to_list(1)
            return json.loads(json.dumps(found[0], default=str)) if found else None

    def find(self, query: dict | None = None, *_args, **_kwargs) -> LocalCursor:
        documents = [
            json.loads(json.dumps(doc, default=str))
            for doc in self._load()
            if matches(doc, query)
        ]
        return LocalCursor(documents)

    async def count_documents(self, query: dict | None = None) -> int:
        async with self._lock:
            return sum(1 for doc in self._load() if matches(doc, query))

    async def distinct(self, key: str, query: dict | None = None) -> list[Any]:
        async with self._lock:
            values = {
                _get_path(doc, key) for doc in self._load() if matches(doc, query)
            }
            return [value for value in values if value is not None]

    # ---- writes ----
    async def insert_one(self, document: dict) -> InsertOneResult:
        async with self._lock:
            documents = self._load()
            payload = dict(document)
            payload.setdefault("_id", new_id())
            documents.append(payload)
            self._flush()
            return InsertOneResult(payload["_id"])

    async def insert_many(self, documents: Iterable[dict]) -> InsertManyResult:
        inserted: list[Any] = []
        async with self._lock:
            store = self._load()
            for document in documents:
                payload = dict(document)
                payload.setdefault("_id", new_id())
                store.append(payload)
                inserted.append(payload["_id"])
            self._flush()
        return InsertManyResult(inserted)

    async def update_one(
        self, query: dict, update: dict, upsert: bool = False
    ) -> UpdateResult:
        async with self._lock:
            documents = self._load()
            for index, document in enumerate(documents):
                if matches(document, query):
                    documents[index] = apply_update(document, update)
                    self._flush()
                    return UpdateResult(1, 1)
            if upsert:
                seed = {
                    key: value
                    for key, value in (query or {}).items()
                    if not key.startswith("$") and not isinstance(value, dict)
                }
                seed.setdefault("_id", new_id())
                created = apply_update(seed, update)
                documents.append(created)
                self._flush()
                return UpdateResult(0, 1, created["_id"])
            return UpdateResult(0, 0)

    async def update_many(self, query: dict, update: dict) -> UpdateResult:
        async with self._lock:
            documents = self._load()
            changed = 0
            for index, document in enumerate(documents):
                if matches(document, query):
                    documents[index] = apply_update(document, update)
                    changed += 1
            if changed:
                self._flush()
            return UpdateResult(changed, changed)

    async def delete_one(self, query: dict) -> DeleteResult:
        async with self._lock:
            documents = self._load()
            for index, document in enumerate(documents):
                if matches(document, query):
                    documents.pop(index)
                    self._flush()
                    return DeleteResult(1)
            return DeleteResult(0)

    async def delete_many(self, query: dict) -> DeleteResult:
        async with self._lock:
            documents = self._load()
            keep = [doc for doc in documents if not matches(doc, query)]
            removed = len(documents) - len(keep)
            self._documents = keep
            if removed:
                self._flush()
            return DeleteResult(removed)

    # ---- compatibility no-ops ----
    async def create_index(self, *_args, **_kwargs) -> str:
        return "local-index"


class LocalDatabase:
    """Mimics ``motor.motor_asyncio.AsyncIOMotorDatabase`` for our usage."""

    def __init__(self, directory: Path):
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)
        self._collections: dict[str, LocalCollection] = {}
        self._lock = asyncio.Lock()

    def get_collection(self, name: str) -> LocalCollection:
        if name not in self._collections:
            self._collections[name] = LocalCollection(
                self._directory / f"{name}.json", self._lock
            )
        return self._collections[name]

    def __getitem__(self, name: str) -> LocalCollection:
        return self.get_collection(name)

    def __getattr__(self, name: str) -> LocalCollection:  # pragma: no cover
        if name.startswith("_"):
            raise AttributeError(name)
        return self.get_collection(name)

    async def list_collection_names(self) -> list[str]:
        return sorted(path.stem for path in self._directory.glob("*.json"))
