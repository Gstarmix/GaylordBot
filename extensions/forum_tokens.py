import json
import secrets
from pathlib import Path
_STORE_PATH = Path(__file__).resolve().parent.parent / "forum_tokens.json"
def _load() -> dict:
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("by_token", {})
    data.setdefault("by_thread", {})
    return data
def _save(data: dict) -> None:
    try:
        _STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"[forum_tokens] échec sauvegarde : {exc!r}", flush=True)
def create(thread_id: int, author_id: int) -> str:
    data = _load()
    existing = data["by_thread"].get(str(thread_id))
    if existing:
        return existing
    token = secrets.token_urlsafe(16)
    data["by_token"][token] = {"thread_id": int(thread_id), "author_id": int(author_id)}
    data["by_thread"][str(thread_id)] = token
    _save(data)
    return token
def resolve(token: str) -> dict | None:
    if not token:
        return None
    return _load()["by_token"].get(token)