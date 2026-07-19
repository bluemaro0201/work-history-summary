import json
import uuid
from pathlib import Path

PROVIDERS_FILE = Path("providers.json")

SOURCES = ("git", "slack", "jira", "confluence")


def _load() -> dict:
    if not PROVIDERS_FILE.exists():
        return {s: [] for s in SOURCES}
    data = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    for s in SOURCES:
        data.setdefault(s, [])
    return data


def _save(data: dict) -> None:
    PROVIDERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_all() -> dict:
    return _load()


def has_any() -> bool:
    return any(len(v) > 0 for v in _load().values())


def add(source: str, data: dict) -> dict:
    all_data = _load()
    provider = {**data, "id": str(uuid.uuid4())}
    all_data[source].append(provider)
    _save(all_data)
    return provider


def update(source: str, provider_id: str, data: dict) -> dict | None:
    all_data = _load()
    for i, p in enumerate(all_data.get(source, [])):
        if p["id"] == provider_id:
            all_data[source][i] = {**p, **data, "id": provider_id}
            _save(all_data)
            return all_data[source][i]
    return None


def delete(source: str, provider_id: str) -> bool:
    all_data = _load()
    before = len(all_data.get(source, []))
    all_data[source] = [p for p in all_data[source] if p["id"] != provider_id]
    if len(all_data[source]) == before:
        return False
    _save(all_data)
    return True
