"""Health checks for the three services the backend depends on.

Each check returns a dict with an "ok" flag and never raises, so one failing
service cannot hide the state of the others. Run as a script:

    python -m app.health      # prints JSON, exit code 1 if anything fails
"""

import json
import sys
import uuid

import httpx

from app.config import settings
from app.graph.client import ping

OLLAMA_TIMEOUT_S = 5.0


def _model_prefix(model: str) -> str:
    """'llama3.2:latest' -> 'llama3.2' (any tag of the model counts)."""
    return model.split(":", 1)[0]


def check_falkordb() -> dict:
    return {
        "ok": ping(),
        "host": settings.falkordb_host,
        "port": settings.falkordb_port,
    }


def check_ollama() -> dict:
    required = [_model_prefix(settings.llm_model), _model_prefix(settings.embed_model)]
    result = {"ok": False, "url": settings.ollama_url, "required": required}
    try:
        resp = httpx.get(f"{settings.ollama_url.rstrip('/')}/api/tags", timeout=OLLAMA_TIMEOUT_S)
        resp.raise_for_status()
        names = [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["missing"] = required
        return result
    missing = [p for p in required if not any(n.startswith(p) for n in names)]
    result.update(ok=not missing, models=sorted(names), missing=missing)
    return result


def check_chroma() -> dict:
    path = settings.chroma_path
    result = {"ok": False, "path": str(path)}
    probe = path / f".health_{uuid.uuid4().hex}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        probe.unlink(missing_ok=True)
    return result


def check_all() -> dict:
    checks = {
        "falkordb": check_falkordb(),
        "ollama": check_ollama(),
        "chroma": check_chroma(),
    }
    return {"ok": all(c["ok"] for c in checks.values()), **checks}


def main() -> int:
    report = check_all()
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
