"""
Configuração central do CardioIA Assistente.

Carrega variáveis de ambiente a partir de `.env` na raiz do projeto.
Credenciais IBM e LLM são opcionais: a ausência delas ativa modos
de fallback locais (regra + heurística), adequados à demonstração.
O host padrão ``0.0.0.0`` permite acesso via LAN ou túnel (cloudflared/ngrok).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DISCLAIMER = (
    "Este assistente não substitui atendimento médico e não é dispositivo médico. "
    "Em emergências cardíacas, ligue 192 (SAMU). "
    "Em crise emocional com ideação, ligue 188 (CVV)."
)

# Limiares clínicos alinhados à Fase 1/3 (HR) e à triagem de crise hipertensiva (PA).
SBP_CRISIS_MMHG = 180
DBP_CRISIS_MMHG = 120
HR_TACHYCARDIA_BPM = 120  # herdado de cardio-ia-fase1 / telemetria (BPM > 120)
HR_BRADYCARDIA_BPM = 50  # herdado de cardio-ia-fase1 / telemetria (BPM < 50)
SPO2_CRITICAL_PCT = 90
SPO2_LOW_PCT = 94


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


class Settings:
    """Snapshot imutável das configurações de runtime."""

    def __init__(self) -> None:
        self.project_root: Path = PROJECT_ROOT
        self.frontend_dir: Path = PROJECT_ROOT / "frontend"
        self.data_dir: Path = PROJECT_ROOT / "data"

        self.flask_host: str = os.getenv("FLASK_HOST", "0.0.0.0")
        self.flask_port: int = _as_int(os.getenv("FLASK_PORT"), 5000)
        self.flask_debug: bool = _as_bool(os.getenv("FLASK_DEBUG"), False)
        cors_raw = os.getenv("CORS_ORIGINS", "*")
        self.cors_origins: list[str] = (
            ["*"] if cors_raw.strip() == "*" else [o.strip() for o in cors_raw.split(",") if o.strip()]
        )

        self.watson_api_key: str = os.getenv("WATSON_API_KEY", "").strip()
        # WATSON_SERVICE_URL é alias acadêmico de WATSON_URL (mesmo endpoint Assistant v2).
        self.watson_url: str = (
            os.getenv("WATSON_URL")
            or os.getenv("WATSON_SERVICE_URL")
            or "https://api.us-south.assistant.watson.cloud.ibm.com"
        ).strip()
        self.watson_assistant_id: str = os.getenv("WATSON_ASSISTANT_ID", "").strip()
        self.watson_environment_id: str = os.getenv("WATSON_ENVIRONMENT_ID", "").strip()
        self.watson_version: str = os.getenv("WATSON_VERSION", "2024-08-25").strip()

        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/cardioia.db")
        self.nosql_json_path: Path = PROJECT_ROOT / os.getenv(
            "NOSQL_JSON_PATH", "./data/rpa_audit_store.json"
        ).lstrip("./")
        self.mongo_uri: str = os.getenv("MONGO_URI", "").strip()
        self.mongo_db: str = os.getenv("MONGO_DB", "cardioia")
        self.mongo_collection: str = os.getenv("MONGO_COLLECTION", "rpa_audit_logs")

        self.rpa_poll_interval: int = _as_int(os.getenv("RPA_POLL_INTERVAL_SECONDS"), 15)
        sqlite_path = os.getenv("RPA_SQLITE_PATH", "./data/cardioia.db")
        self.rpa_sqlite_path: Path = (PROJECT_ROOT / sqlite_path.lstrip("./")).resolve()

        self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def watson_enabled(self) -> bool:
        """True somente quando há chave e ID do assistente."""
        return bool(self.watson_api_key and self.watson_assistant_id)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def disclaimer(self) -> str:
        return DISCLAIMER


settings = Settings()
