"""Application settings, loaded once from backend/.env.

Real environment variables win over values in .env, so a deployment can
override any setting without editing the file. Relative paths are resolved
against backend/, never the current working directory, so the server writes
to the same place whether it is started from the repo root or from backend/.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]

load_dotenv(BACKEND_DIR / ".env", override=False)


def _str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


def _path(name: str, default: str) -> Path:
    p = Path(os.getenv(name, default))
    return p if p.is_absolute() else (BACKEND_DIR / p).resolve()


@dataclass(frozen=True)
class Settings:
    falkordb_host: str = field(default_factory=lambda: _str("FALKORDB_HOST", "localhost"))
    falkordb_port: int = field(default_factory=lambda: _int("FALKORDB_PORT", 6379))
    default_workspace: str = field(default_factory=lambda: _str("DEFAULT_WORKSPACE", "demo"))
    ollama_url: str = field(default_factory=lambda: _str("OLLAMA_URL", "http://localhost:11434"))
    llm_model: str = field(default_factory=lambda: _str("LLM_MODEL", "llama3.2:latest"))
    embed_model: str = field(default_factory=lambda: _str("EMBED_MODEL", "nomic-embed-text"))
    chroma_path: Path = field(default_factory=lambda: _path("CHROMA_PATH", "./chroma_data"))
    upload_dir: Path = field(default_factory=lambda: _path("UPLOAD_DIR", "./uploads"))
    workers_per_stage: int = field(default_factory=lambda: _int("WORKERS_PER_STAGE", 1))

    def __post_init__(self) -> None:
        if not 1 <= self.falkordb_port <= 65535:
            raise ValueError(f"FALKORDB_PORT out of range: {self.falkordb_port}")
        if self.workers_per_stage < 1:
            raise ValueError(f"WORKERS_PER_STAGE must be >= 1, got {self.workers_per_stage}")


settings = Settings()
