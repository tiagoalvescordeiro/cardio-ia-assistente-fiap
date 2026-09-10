"""
Ir Além 1 — extração clínica por IA generativa (com fallback heurístico).

Converte narrativas livres (prontuário sintético) em JSON estrito validado
por Pydantic v2. Sem chave de LLM, o extrator por regras/regex ainda cobre
os casos de `dataset_casos_teste.json`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import unicodedata
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Este assistente não substitui atendimento médico. "
    "Em emergências, ligue 192 (SAMU)."
)

# Limiares alinhados à Fase 1/3 (FC) e à crise hipertensiva usada no RPA (PA, SpO2).
SBP_CRISIS = 180
DBP_CRISIS = 120
HR_TACHYCARDIA = 120
HR_BRADYCARDIA = 50
SPO2_CRITICAL = 90
SPO2_LOW = 94
SBP_STAGE2 = 160
DBP_STAGE2 = 100
SBP_HIGH = 140
DBP_HIGH = 90


class ClassificacaoRisco(str, Enum):
    """Estratificação de risco do protótipo (não é escore clínico validado)."""

    BAIXO = "BAIXO"
    MODERADO = "MODERADO"
    ALTO = "ALTO"
    EMERGENCIA = "EMERGENCIA"


class Paciente(BaseModel):
    identificador: str = Field(..., min_length=1)
    idade: int = Field(..., ge=0, le=120)


class SinaisVitais(BaseModel):
    pressao_sistolica: float = Field(..., ge=50, le=300, description="PAS mmHg")
    pressao_diastolica: float = Field(..., ge=30, le=200, description="PAD mmHg")
    frequencia_cardiaca: float = Field(..., ge=20, le=250, description="FC bpm")
    spo2: float | None = Field(default=None, ge=40, le=100, description="SpO2 % (Fase 1/3)")

    @field_validator("pressao_sistolica", "pressao_diastolica", "frequencia_cardiaca", "spo2", mode="before")
    @classmethod
    def _coerce_number(cls, value: Any) -> Any:
        if value in (None, "", "null"):
            return None
        if isinstance(value, str):
            return float(value.replace(",", ".").strip())
        return value


class MedicamentoUso(BaseModel):
    nome: str
    posologia: str


class RegistroClinico(BaseModel):
    """Contrato JSON estrito da extração (Fase 5).

    Aliases da rubrica FIAP: medicacoes_em_uso, risco_estratificado,
    historico_cardiovascular, sintomas_atuais, necessidade_encaminhamento.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    paciente: Paciente
    queixa_principal: str = ""
    historico_cardiovascular: str = ""
    sintomas_atuais: list[str] = Field(default_factory=list)
    sinais_vitais: SinaisVitais
    medicamentos_em_uso: list[MedicamentoUso] = Field(default_factory=list)
    classificacao_risco: ClassificacaoRisco
    conduta_sugerida: str
    necessidade_encaminhamento: bool = False

    @model_validator(mode="before")
    @classmethod
    def _accept_rubric_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if "medicacoes_em_uso" in payload and "medicamentos_em_uso" not in payload:
            payload["medicamentos_em_uso"] = payload["medicacoes_em_uso"]
        if "risco_estratificado" in payload and "classificacao_risco" not in payload:
            payload["classificacao_risco"] = payload["risco_estratificado"]
        if payload.get("sintomas_atuais") and not payload.get("queixa_principal"):
            sintomas = payload["sintomas_atuais"]
            payload["queixa_principal"] = ", ".join(sintomas) if isinstance(sintomas, list) else str(sintomas)
        return payload

    @model_validator(mode="after")
    def _sbp_ge_dbp(self) -> "RegistroClinico":
        if self.sinais_vitais.pressao_sistolica < self.sinais_vitais.pressao_diastolica:
            raise ValueError("PAS deve ser maior ou igual à PAD.")
        self.sintomas_atuais = _dedupe_casefold(self.sintomas_atuais)
        seen_meds: set[str] = set()
        unique_meds: list[MedicamentoUso] = []
        for med in self.medicamentos_em_uso:
            key = (med.nome or "").strip().casefold()
            if not key or key in seen_meds:
                continue
            seen_meds.add(key)
            unique_meds.append(med)
        self.medicamentos_em_uso = unique_meds
        if not self.necessidade_encaminhamento:
            self.necessidade_encaminhamento = self.classificacao_risco in {
                ClassificacaoRisco.ALTO,
                ClassificacaoRisco.EMERGENCIA,
            }
        return self


FEW_SHOT_SYSTEM = f"""Você é um extrator clínico acadêmico do CardioIA (FIAP).
Extraia APENAS JSON válido no schema:
{{
  "paciente": {{"identificador": "string", "idade": integer}},
  "historico_cardiovascular": "string",
  "sintomas_atuais": ["string"],
  "queixa_principal": "string",
  "sinais_vitais": {{
    "pressao_sistolica": number,
    "pressao_diastolica": number,
    "frequencia_cardiaca": number,
    "spo2": number | null
  }},
  "medicamentos_em_uso": [{{"nome": "string", "posologia": "string"}}],
  "classificacao_risco": "BAIXO | MODERADO | ALTO | EMERGENCIA",
  "necessidade_encaminhamento": true,
  "conduta_sugerida": "string"
}}

Regras de risco (protótipo):
- EMERGENCIA: dor irradiada + sudorese + dispneia; OU PAS>={SBP_CRISIS}; OU PAD>={DBP_CRISIS};
  OU FC>{HR_TACHYCARDIA} em repouso com sintomas isquêmicos; OU SpO2<{SPO2_CRITICAL}.
- ALTO: angina típica, PAS>={SBP_STAGE2}, PAD>={DBP_STAGE2}, SpO2<{SPO2_LOW}, síncope.
- MODERADO: palpitação isolada, PA 140-159/90-99, dor atípica sem red flags.
- BAIXO: vitais estáveis e queixa não cardiológica aguda.

Dados são sintéticos. Sempre recorde: {DISCLAIMER}
Não invente identificador se o texto trouxer PAC-...; copie-o.
Responda somente JSON, sem markdown.
"""

FEW_SHOT_USER = (
    "Paciente PAC-DEMO-00, 70 anos. Queixa de cansaço leve após caminhada. "
    "PA 128/78 mmHg, FC 72 bpm, SpO2 98%. Medicações: losartana 50 mg 1x/dia."
)

FEW_SHOT_ASSISTANT = json.dumps(
    {
        "paciente": {"identificador": "PAC-DEMO-00", "idade": 70},
        "queixa_principal": "Cansaço leve após caminhada",
        "sinais_vitais": {
            "pressao_sistolica": 128,
            "pressao_diastolica": 78,
            "frequencia_cardiaca": 72,
            "spo2": 98,
        },
        "medicamentos_em_uso": [{"nome": "losartana", "posologia": "50 mg 1x/dia"}],
        "classificacao_risco": "BAIXO",
        "conduta_sugerida": "Manter acompanhamento ambulatorial e medidas de PA domiciliar.",
    },
    ensure_ascii=False,
)


def _dedupe_casefold(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = (item or "").strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _positive_mention(text_norm: str, needles: tuple[str, ...]) -> bool:
    """Detecta menção afirmativa, ignorando negações do tipo 'sem/nega'."""
    clauses = re.split(r"[.\n;]", text_norm)
    neg_prefix = re.compile(
        r"(sem|nega(?:ndo)?|nao\s+(?:ha|apresenta|refere|relata)|ausencia\s+de)\s+[\w,\s]{0,48}$"
    )
    for clause in clauses:
        clause = clause.strip()
        clause_negated = clause.startswith("nega")
        for needle in needles:
            start = 0
            while True:
                pos = clause.find(needle, start)
                if pos < 0:
                    break
                prefix = clause[max(0, pos - 40) : pos]
                local_neg = clause_negated or bool(neg_prefix.search(prefix))
                if re.search(rf"\bsem\s+{re.escape(needle)}", clause):
                    local_neg = True
                if not local_neg:
                    return True
                start = pos + max(len(needle), 1)
    return False


def classify_risk(
    texto: str,
    sbp: float,
    dbp: float,
    hr: float,
    spo2: float | None,
) -> ClassificacaoRisco:
    """Classificação determinística (red flags + limiares Fase 1/RPA)."""
    n = _norm(texto)
    irradiacao = _positive_mention(
        n, ("irradia", "braco esquerdo", "mandibula", "pescoco", "ombro esquerdo")
    )
    sudorese = _positive_mention(n, ("sudorese", "suor frio", "diaforese", "suando frio"))
    dispneia = _positive_mention(
        n, ("falta de ar", "dispneia", "ofegante", "nao consegue respirar", "ortopneia")
    )
    dor_peito = _positive_mention(
        n, ("dor no peito", "dor torac", "aperto no peito", "opressao", "precordial", "retroesternal")
    )
    sincopa = _positive_mention(n, ("desmaio", "sincop", "perdeu a consciencia"))
    instavel = _positive_mention(n, ("em repouso", "nao alivia", "mais de 20 min", "vinte minutos"))

    if irradiacao and sudorese and dispneia:
        return ClassificacaoRisco.EMERGENCIA
    if sbp >= SBP_CRISIS or dbp >= DBP_CRISIS:
        return ClassificacaoRisco.EMERGENCIA
    if hr > HR_TACHYCARDIA and (dor_peito or dispneia or sudorese):
        return ClassificacaoRisco.EMERGENCIA
    if spo2 is not None and spo2 < SPO2_CRITICAL:
        return ClassificacaoRisco.EMERGENCIA
    if sincopa and (dor_peito or dispneia or hr > 110):
        return ClassificacaoRisco.EMERGENCIA

    if dor_peito and (irradiacao or sudorese or dispneia or instavel):
        return ClassificacaoRisco.ALTO
    if sbp >= SBP_STAGE2 or dbp >= DBP_STAGE2:
        return ClassificacaoRisco.ALTO
    if hr > HR_TACHYCARDIA or (hr < HR_BRADYCARDIA and (sincopa or dispneia)):
        return ClassificacaoRisco.ALTO
    if spo2 is not None and spo2 < SPO2_LOW:
        return ClassificacaoRisco.ALTO
    if sincopa:
        return ClassificacaoRisco.ALTO

    if dor_peito or _positive_mention(n, ("palpit", "taquicardia", "extrasistole")):
        return ClassificacaoRisco.MODERADO
    if sbp >= SBP_HIGH or dbp >= DBP_HIGH:
        return ClassificacaoRisco.MODERADO
    if hr >= 100:
        return ClassificacaoRisco.MODERADO
    return ClassificacaoRisco.BAIXO


def conduta_para(risco: ClassificacaoRisco) -> str:
    mapping = {
        ClassificacaoRisco.EMERGENCIA: (
            "Acionar SAMU 192 imediatamente. Não conduzir veículos. "
            "Monitorizar PA, FC e SpO2. Protótipo acadêmico — não substitui o médico. "
            + DISCLAIMER
        ),
        ClassificacaoRisco.ALTO: (
            "Encaminhar para avaliação médica urgente (pronto-atendimento/cardiologia). "
            "Repetir sinais vitais e ECG se disponível. " + DISCLAIMER
        ),
        ClassificacaoRisco.MODERADO: (
            "Consulta cardiológica em janela curta; registro de PA e sintomas. "
            "Retornar imediatamente se surgir dor irradiada, suor frio ou dispneia. "
            + DISCLAIMER
        ),
        ClassificacaoRisco.BAIXO: (
            "Seguimento ambulatorial e medidas preventivas. Manter medicações prescritas. "
            + DISCLAIMER
        ),
    }
    return mapping[risco]


MED_CATALOG: tuple[str, ...] = (
    "aas",
    "acido acetilsalicilico",
    "aspirina",
    "atenolol",
    "propranolol",
    "carvedilol",
    "metoprolol",
    "bisoprolol",
    "enalapril",
    "captopril",
    "losartana",
    "valsartana",
    "amlodipino",
    "nifedipino",
    "hidroclorotiazida",
    "clortalidona",
    "furosemida",
    "espironolactona",
    "sinvastatina",
    "atorvastatina",
    "rosuvastatina",
    "clopidogrel",
    "rivaroxabana",
    "varfarina",
    "metformina",
    "insulina",
    "omeprazol",
    "levotiroxina",
    "dinitrato de isossorbida",
    "mononitrato de isossorbida",
    "anlodipino",
)


def _extract_historico(texto: str) -> str:
    n = _norm(texto)
    bits: list[str] = []
    if _positive_mention(n, ("hipertens", "pressao alta", "diagnostico de has")):
        bits.append("hipertensão")
    if _positive_mention(n, ("infarto previo", "infarto previo", "iam previo", "avc previo")):
        bits.append("evento cardiovascular prévio")
    if _positive_mention(n, ("diabetes", "dm2")):
        bits.append("diabetes")
    if _positive_mention(n, ("tabag", "fumante")):
        bits.append("tabagismo")
    if _positive_mention(n, ("dislipidem", "colesterol alto")):
        bits.append("dislipidemia")
    return "; ".join(bits) if bits else "não informado no texto"


def _extract_sintomas_atuais(texto: str, queixa: str) -> list[str]:
    n = _norm(texto)
    found: list[str] = []
    mapping = (
        ("dor/aperto no peito", ("dor no peito", "aperto no peito", "opressao")),
        ("irradiação", ("irradia", "braco esquerdo", "mandibula")),
        ("sudorese fria", ("suor frio", "sudorese", "diaforese")),
        ("dispneia", ("falta de ar", "dispneia")),
        ("palpitações", ("palpit", "taquicardia")),
        ("síncope", ("desmaio", "sincop")),
        ("cansaço", ("cansaco", "fadiga")),
    )
    for label, needles in mapping:
        if _positive_mention(n, needles):
            found.append(label)
    if queixa and queixa.strip().casefold() not in {s.casefold() for s in found}:
        found.insert(0, queixa)
    return _dedupe_casefold(found) or ([queixa] if queixa else ["Não especificada"])


def extract_heuristic(texto: str) -> RegistroClinico:
    """Extrator offline de alta cobertura para os casos sintéticos."""
    ident = _extract_id(texto)
    idade = _extract_idade(texto)
    sbp, dbp = _extract_pa(texto)
    hr = _extract_fc(texto)
    spo2 = _extract_spo2(texto)
    _assert_vitals_physiology(idade, sbp, dbp, hr, spo2)
    meds = _extract_meds(texto)
    queixa = _extract_queixa(texto)
    risco = classify_risk(texto, sbp, dbp, hr, spo2)
    return RegistroClinico(
        paciente=Paciente(identificador=ident, idade=idade),
        queixa_principal=queixa,
        historico_cardiovascular=_extract_historico(texto),
        sintomas_atuais=_extract_sintomas_atuais(texto, queixa),
        sinais_vitais=SinaisVitais(
            pressao_sistolica=sbp,
            pressao_diastolica=dbp,
            frequencia_cardiaca=hr,
            spo2=spo2,
        ),
        medicamentos_em_uso=meds,
        classificacao_risco=risco,
        conduta_sugerida=conduta_para(risco),
        necessidade_encaminhamento=risco in {ClassificacaoRisco.ALTO, ClassificacaoRisco.EMERGENCIA},
    )


def _extract_id(texto: str) -> str:
    match = re.search(r"\b(PAC[-_][A-Z0-9]+(?:[-_]\d+)*)\b", texto, flags=re.I)
    if match:
        return match.group(1).upper().replace("_", "-")
    match = re.search(r"identificador[:\s]+([A-Z0-9\-]+)", texto, flags=re.I)
    if match:
        return match.group(1).upper()
    return "PAC-NAO-INFORMADO"


def _extract_idade(texto: str) -> int:
    match = re.search(r"(-?\d{1,4})\s*anos", texto, flags=re.I)
    if match:
        return int(match.group(1))
    match = re.search(r"idade[:\s]+(-?\d{1,4})", texto, flags=re.I)
    if match:
        return int(match.group(1))
    return 0


def _extract_pa(texto: str) -> tuple[float, float]:
    patterns = (
        r"(?:PA|P\.?A\.?|press[aã]o(?:\s+arterial)?)\s*[:=]?\s*(-?\d{2,4})\s*[xX/]\s*(-?\d{2,4})",
        r"\b(-?\d{2,4})\s*/\s*(-?\d{2,4})\s*(?:mm\s*hg|mmhg)?",
        r"sist[oó]lica\s*[:=]?\s*(-?\d{2,4}).{0,40}diast[oó]lica\s*[:=]?\s*(-?\d{2,4})",
    )
    for pat in patterns:
        match = re.search(pat, texto, flags=re.I | re.S)
        if match:
            return float(match.group(1)), float(match.group(2))
    raise ValueError(
        "Não encontrei pressão arterial no relato. Inclua PAS e PAD, por exemplo: PA 120/80 mmHg."
    )


def _extract_fc(texto: str) -> float:
    patterns = (
        r"(?:FC|F\.?C\.?|frequ[eê]ncia\s+card[ií]aca|freq\.?\s*card[ií]aca|pulso)\s*[:=]?\s*(-?\d{1,4})",
        r"(-?\d{1,4})\s*(?:bpm|batimentos)",
    )
    for pat in patterns:
        match = re.search(pat, texto, flags=re.I)
        if match:
            return float(match.group(1))
    raise ValueError(
        "Não encontrei frequência cardíaca no relato. Inclua a FC, por exemplo: FC 72 bpm."
    )


def _extract_spo2(texto: str) -> float | None:
    match = re.search(
        r"(?:spo2|satura[cç][aã]o|sat\.?\s*o2)\s*[:=]?\s*(-?\d{1,4}(?:[.,]\d+)?)\s*%?",
        texto,
        flags=re.I,
    )
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def _assert_vitals_physiology(
    idade: int,
    sbp: float,
    dbp: float,
    hr: float,
    spo2: float | None,
) -> None:
    """Rejeita vitais impossíveis em vez de tratá-los como alerta clínico."""
    if idade < 0 or idade > 120:
        raise ValueError(
            f"A idade informada ({idade} anos) não é fisiologicamente possível. "
            "Use um valor entre 0 e 120 anos."
        )
    if sbp < 50 or sbp > 300 or dbp < 30 or dbp > 200 or sbp < dbp:
        raise ValueError(
            f"Os valores de pressão ({int(sbp)}/{int(dbp)} mmHg) não são fisiologicamente possíveis. "
            "Informe PAS/PAD usuais (ex.: 120/80). Não trato leituras absurdas como crise."
        )
    if hr < 20 or hr > 250:
        raise ValueError(
            f"A frequência cardíaca ({int(hr)} bpm) não é fisiologicamente possível. "
            "Informe um valor entre 20 e 250 bpm."
        )
    if spo2 is not None and (spo2 < 40 or spo2 > 100):
        raise ValueError(
            f"A saturação (SpO2 {spo2:g}%) não é fisiologicamente possível. "
            "Use um valor entre 40 e 100%."
        )


def _extract_meds(texto: str) -> list[MedicamentoUso]:
    n = _norm(texto)
    found: list[MedicamentoUso] = []
    seen: set[str] = set()
    for nome in MED_CATALOG:
        if nome in n and nome not in seen:
            seen.add(nome)
            poso = _posologia_proxima(texto, nome)
            found.append(MedicamentoUso(nome=nome, posologia=poso))
    return found


def _posologia_proxima(texto: str, nome: str) -> str:
    pattern = re.compile(
        rf"{re.escape(nome)}\s*[,:]?\s*(\d+(?:[.,]\d+)?\s*mg(?:\s*(?:1x|2x|3x|/)?/?dia)?)?",
        flags=re.I,
    )
    match = pattern.search(_norm(texto))
    if match and match.group(1):
        return match.group(1).strip()
    # busca no texto original após o nome
    orig = re.search(rf"{re.escape(nome)}[^.\n;]{{0,48}}", texto, flags=re.I)
    if orig:
        chunk = orig.group(0)
        dose = re.search(r"\d+(?:[.,]\d+)?\s*mg[^.\n;]*", chunk, flags=re.I)
        if dose:
            return dose.group(0).strip()
    return "não informada"


def _extract_queixa(texto: str) -> str:
    match = re.search(
        r"(?:queixa(?:\s+principal)?|qp|hda|relato)[:\s]+(.{10,180})",
        texto,
        flags=re.I,
    )
    if match:
        return match.group(1).split(".")[0].strip()
    n = _norm(texto)
    if "dor no peito" in n or "aperto no peito" in n:
        return "Dor/aperto no peito"
    if "falta de ar" in n or "dispneia" in n:
        return "Dispneia"
    if "palpit" in n:
        return "Palpitações"
    if "pressao alta" in n or "hipertens" in n:
        return "Hipertensão / medida elevada de PA"
    if "cansaco" in n or "fadiga" in n:
        return "Cansaço"
    first = texto.strip().split(".")[0]
    return first[:180] if first else "Não especificada"


def _call_llm(texto: str) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import requests
    except ImportError:
        logger.warning("Pacote requests ausente; extração LLM ignorada.")
        return None

    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": FEW_SHOT_SYSTEM},
            {"role": "user", "content": FEW_SHOT_USER},
            {"role": "assistant", "content": FEW_SHOT_ASSISTANT},
            {"role": "user", "content": texto},
        ],
    }
    try:
        response = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM indisponível (%s); usando heurística.", exc)
        return None


def extract_clinical_record(texto: str, prefer_llm: bool = True) -> RegistroClinico:
    """
    Pipeline principal: tenta LLM (se houver chave) e valida em Pydantic;
    se falhar, aplica o extrator heurístico e reclassifica o risco.
    """
    if not texto or not texto.strip():
        raise ValueError("Texto clínico vazio.")

    heuristic = extract_heuristic(texto)
    if prefer_llm:
        llm_payload = _call_llm(texto)
        if llm_payload:
            try:
                llm_payload.setdefault("conduta_sugerida", conduta_para(heuristic.classificacao_risco))
                model = RegistroClinico.model_validate(llm_payload)
                _assert_vitals_physiology(
                    model.paciente.idade,
                    model.sinais_vitais.pressao_sistolica,
                    model.sinais_vitais.pressao_diastolica,
                    model.sinais_vitais.frequencia_cardiaca,
                    model.sinais_vitais.spo2,
                )
                # Recalcula risco pelos limiares locais (segurança do protótipo).
                risco = classify_risk(
                    texto,
                    model.sinais_vitais.pressao_sistolica,
                    model.sinais_vitais.pressao_diastolica,
                    model.sinais_vitais.frequencia_cardiaca,
                    model.sinais_vitais.spo2,
                )
                if risco.value != model.classificacao_risco.value:
                    model = model.model_copy(
                        update={
                            "classificacao_risco": risco,
                            "conduta_sugerida": conduta_para(risco),
                        }
                    )
                return model
            except Exception as exc:  # noqa: BLE001
                logger.warning("JSON do LLM inválido (%s); heurística prevalece.", exc)
    return heuristic


def extract_to_dict(texto: str) -> dict[str, Any]:
    """Serializa o registro extraído (uso pela API Flask)."""
    model = extract_clinical_record(texto)
    payload = model.model_dump()
    payload["classificacao_risco"] = model.classificacao_risco.value
    payload["risco_estratificado"] = model.classificacao_risco.value
    payload["necessidade_encaminhamento"] = bool(model.necessidade_encaminhamento)
    payload.pop("medicacoes_em_uso", None)
    payload["disclaimer"] = DISCLAIMER
    payload["fonte_extracao"] = "heuristica_ou_llm"
    return payload


def run_dataset(dataset_path: Path) -> list[dict[str, Any]]:
    """Processa o JSON de casos sintéticos e devolve resultados + checagem de risco."""
    casos = json.loads(dataset_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for caso in casos:
        texto = caso["narrativa"]
        esperado = caso.get("risco_esperado")
        extraido = extract_clinical_record(texto, prefer_llm=False)
        item = extraido.model_dump()
        item["classificacao_risco"] = extraido.classificacao_risco.value
        item["id_caso"] = caso.get("id")
        item["risco_esperado"] = esperado
        item["bate_esperado"] = esperado == extraido.classificacao_risco.value if esperado else None
        results.append(item)
    return results


def _cli() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Extração clínica CardioIA (Ir Além 1).")
    parser.add_argument("--text", type=str, help="Narrativa única.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).with_name("dataset_casos_teste.json"),
        help="Arquivo JSON de casos sintéticos.",
    )
    args = parser.parse_args()
    if args.text:
        print(json.dumps(extract_to_dict(args.text), ensure_ascii=False, indent=2))
        return 0
    rows = run_dataset(args.dataset)
    ok = all(r.get("bate_esperado") in (True, None) for r in rows)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    mismatches = [r["id_caso"] for r in rows if r.get("bate_esperado") is False]
    if mismatches:
        logger.error("Risco divergente nos casos: %s", mismatches)
        return 1
    logger.info("Todos os %s casos sintéticos extraídos e classificados.", len(rows))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_cli())
