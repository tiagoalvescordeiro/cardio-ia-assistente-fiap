"""
API Flask do CardioIA Assistente (Fase 5 — CardioIA + ECO).

Endpoints
---------
GET    /api/health
GET    /api/eco-pulse  pulso k-anônimo sintético (sem geolocalização)
POST   /api/chat      {message, session_id?}
POST   /api/message   alias de /api/chat
POST   /api/extract   {text}
POST   /api/session   cria sessão Watson v2 / local
DELETE /api/session/<id>

Interceptor: ideação/automutilação → CVV 188 + SAMU 192 **sem** chamar Watson.
O frontend estático em ``../frontend`` é servido na raiz.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Garante import de `config` e `services` ao executar `python app.py`.
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from config import DISCLAIMER, settings  # noqa: E402
from services.eco_social import pulse_payload  # noqa: E402
from services.llm_extractor import extract_clinical_payload  # noqa: E402
from services.safety_filter import evaluate_safety  # noqa: E402
from services.watson_service import WatsonService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("cardioia")

app = Flask(
    __name__,
    static_folder=str(settings.frontend_dir),
    static_url_path="",
)
CORS(app, resources={r"/api/*": {"origins": settings.cors_origins}})

watson = WatsonService()


@app.get("/")
def index():
    """Serve o widget conversacional."""
    return send_from_directory(settings.frontend_dir, "index.html")


@app.get("/api/eco-pulse")
def eco_pulse():
    """Pulso k-anônimo sintético (sem GPS, sem PII)."""
    return jsonify(pulse_payload())


@app.get("/api/health")
def health():
    """Liveness + capacidade do runtime (Watson/LLM opcionais)."""
    return jsonify(
        {
            "status": "ok",
            "service": "cardio-ia-assistente",
            "watson_mode": "cloud" if settings.watson_enabled else "fallback",
            "llm_mode": "openai" if settings.llm_enabled else "heuristic",
            "disclaimer": DISCLAIMER,
        }
    )


def _parse_chat_payload() -> tuple[str | None, str | None]:
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or payload.get("text") or "").strip()
    session_id = payload.get("session_id")
    if session_id is not None:
        session_id = str(session_id).strip() or None
    return (message or None), session_id


@app.post("/api/chat")
def chat():
    """Mensagem do usuário → filtro de segurança → Watson ou regras."""
    message, session_id = _parse_chat_payload()
    if not message:
        return jsonify({"error": "Campo 'message' é obrigatório.", "disclaimer": DISCLAIMER}), 400
    sid = session_id or watson.create_session()
    blocked = evaluate_safety(message)
    if blocked is not None and blocked.block_watson:
        logger.info("Interceptor de segurança: %s (Watson não chamado).", blocked.route)
        return jsonify(blocked.to_chat_payload(sid))
    try:
        result = watson.send_message(message, sid)
        return jsonify(result.to_dict())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha em /api/chat (conexão/runtime)")
        # Erro de conexão não deve silenciar a orientação de emergência.
        return jsonify(
            {
                "error": "Falha temporária ao falar com o assistente. Se for emergência cardíaca, ligue 192. Em crise com ideação, 188.",
                "detail": str(exc),
                "disclaimer": DISCLAIMER,
            }
        ), 500


@app.post("/api/message")
def message_alias():
    """Alias acadêmico de POST /api/chat (contrato FIAP Cap. 1)."""
    return chat()


@app.post("/api/extract")
def extract():
    """Extração estruturada de prontuário sintético (Ir Além 1)."""
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or payload.get("narrativa") or "").strip()
    if not text:
        return jsonify({"error": "Campo 'text' é obrigatório.", "disclaimer": DISCLAIMER}), 400
    try:
        data = extract_clinical_payload(text)
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"error": str(exc), "disclaimer": DISCLAIMER}), 422
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha em /api/extract")
        return jsonify({"error": str(exc), "disclaimer": DISCLAIMER}), 500


@app.post("/api/session")
def new_session():
    """Cria uma nova sessão conversacional."""
    return jsonify({"session_id": watson.create_session(), "disclaimer": DISCLAIMER})


@app.delete("/api/session/<session_id>")
def drop_session(session_id: str):
    watson.delete_session(session_id)
    return jsonify({"ok": True})


def main() -> None:
    logger.info(
        "CardioIA em http://%s:%s (Watson=%s, LLM=%s)",
        settings.flask_host,
        settings.flask_port,
        "cloud" if settings.watson_enabled else "fallback",
        "openai" if settings.llm_enabled else "heuristic",
    )
    app.run(host=settings.flask_host, port=settings.flask_port, debug=settings.flask_debug)


if __name__ == "__main__":
    main()
