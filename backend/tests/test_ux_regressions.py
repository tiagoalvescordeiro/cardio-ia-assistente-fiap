"""Regressões de UX (P0 greeting sticky, extração, caminho do avaliador)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT / "ir_alem_1_genai") not in sys.path:
    sys.path.insert(0, str(ROOT / "ir_alem_1_genai"))

from services.llm_extractor import extract_clinical_payload  # noqa: E402
from services.watson_service import INTENT_AVALIADOR, INTENT_FALLBACK, WatsonService  # noqa: E402


class GreetingEmergencyTests(unittest.TestCase):
    def test_greeting_does_not_stick_emergency(self) -> None:
        w = WatsonService()
        sid = w.create_session()
        greet = w.send_message("Oi", sid)
        memory = w._memory(sid)
        self.assertFalse(memory.emergencia_ativa)
        self.assertNotEqual(greet.to_dict()["ui"].get("emergency_dial"), "192")
        self.assertIn("CardioIA", greet.reply)

    def test_anxiety_after_greeting_follows_eco(self) -> None:
        w = WatsonService()
        sid = w.create_session()
        w.send_message("Oi", sid)
        eco = w.send_message("Estou com ansiedade e tensão muscular", sid)
        memory = w._memory(sid)
        self.assertFalse(memory.emergencia_ativa)
        self.assertNotEqual(memory.risco, "A")
        lowered = eco.reply.lower()
        self.assertNotIn("ligue agora para o samu", lowered)
        self.assertTrue(
            "suor frio" in lowered or "estou aqui" in lowered or "corpo em alerta" in lowered
        )

    def test_true_emergency_after_greeting_still_samu(self) -> None:
        w = WatsonService()
        sid = w.create_session()
        w.send_message("Oi", sid)
        red = w.send_message("Dor no peito irradiando para o braço com suor frio", sid)
        self.assertIn("192", red.reply)
        self.assertTrue(w._memory(sid).emergencia_ativa)
        self.assertEqual(w._memory(sid).risco, "A")

    def test_new_session_clears_sticky_emergency(self) -> None:
        w = WatsonService()
        sid = w.create_session()
        w.send_message("Dor no peito irradiando para o braço com suor frio", sid)
        self.assertTrue(w._memory(sid).emergencia_ativa)
        sid2 = w.create_session()
        breath = w.send_message("Quero fazer a respiração 4-7-8", sid2)
        self.assertIn("4-7-8", breath.reply)
        self.assertFalse(w._memory(sid2).emergencia_ativa)


class EvaluatorPathTests(unittest.TestCase):
    def test_physician_does_not_fall_to_anything_else(self) -> None:
        w = WatsonService()
        result = w.send_message("sou médico, estou avaliando", w.create_session())
        intents = [str(i.get("intent") or "") for i in result.intents]
        self.assertNotIn(INTENT_FALLBACK, intents)
        self.assertIn(INTENT_AVALIADOR, intents)
        self.assertIn("protótipo", result.reply.lower())


class ExtractionPayloadTests(unittest.TestCase):
    SAMPLE = (
        "PAC-SYN-007, 59 anos. Dor no peito irradiando para a mandíbula, "
        "sudorese fria e falta de ar. PA 148/92 mmHg, FC 110 bpm, SpO2 93%. "
        "AAS 100 mg 1x/dia."
    )

    def test_canonical_medication_field_and_symptom_dedupe(self) -> None:
        data = extract_clinical_payload(self.SAMPLE)
        self.assertIn("medicamentos_em_uso", data)
        self.assertNotIn("medicacoes_em_uso", data)
        names = [s.casefold() for s in data["sintomas_atuais"]]
        self.assertEqual(len(names), len(set(names)))

    def test_impossible_pa_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            extract_clinical_payload(
                "PAC-SYN-X, 50 anos. PA 900/800 mmHg, FC 80 bpm, SpO2 98%."
            )
        self.assertIn("fisiologicamente", str(ctx.exception).lower())

    def test_negative_hr_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            extract_clinical_payload("PAC-SYN-X, 40 anos. PA 120/80 mmHg, FC -10 bpm.")
        self.assertIn("fisiologicamente", str(ctx.exception).lower())

    def test_spo2_over_100_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            extract_clinical_payload("PAC-SYN-X, 40 anos. PA 120/80 mmHg, FC 70 bpm, SpO2 105%.")
        self.assertIn("fisiologicamente", str(ctx.exception).lower())

    def test_absurd_age_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            extract_clinical_payload("PAC-SYN-X, 200 anos. PA 120/80 mmHg, FC 70 bpm, SpO2 98%.")
        self.assertIn("idade", str(ctx.exception).lower())

    def test_missing_pa_is_friendly(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            extract_clinical_payload("PAC-SYN-X, 40 anos. Relato sem números de pressão. FC 70 bpm.")
        self.assertIn("pressão arterial", str(ctx.exception).lower())

    def test_crisis_pa_still_emergency(self) -> None:
        data = extract_clinical_payload(
            "PAC-SYN-008, 74 anos. PA 192/124 mmHg, FC 88 bpm, SpO2 96%."
        )
        self.assertEqual(data["classificacao_risco"], "EMERGENCIA")


if __name__ == "__main__":
    unittest.main()
