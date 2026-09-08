"""
Fachada de extração clínica para a API Flask.

Importa o pipeline de `ir_alem_1_genai/clinical_extraction.py` sem exigir
instalação do módulo como pacote.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_GENAI_DIR = Path(__file__).resolve().parents[2] / "ir_alem_1_genai"
if str(_GENAI_DIR) not in sys.path:
    sys.path.insert(0, str(_GENAI_DIR))

from clinical_extraction import (  # noqa: E402
    DISCLAIMER,
    RegistroClinico,
    extract_clinical_record,
    extract_to_dict,
)


def extract_clinical_payload(texto: str) -> dict[str, Any]:
    """
    Executa a extração e devolve dict JSON-serializável para POST /api/extract.

    Parameters
    ----------
    texto:
        Narrativa livre (prontuário sintético ou relato do paciente).
    """
    if not texto or not str(texto).strip():
        raise ValueError("Campo 'text' é obrigatório.")
    logger.info("Extração clínica iniciada (len=%s).", len(texto))
    return extract_to_dict(str(texto))


__all__ = [
    "DISCLAIMER",
    "RegistroClinico",
    "extract_clinical_payload",
    "extract_clinical_record",
]
