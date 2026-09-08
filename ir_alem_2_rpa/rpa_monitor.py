"""
Ir Além 2 — worker RPA de monitoramento de sinais vitais.

Fluxo
-----
1. Lê registros ainda não processados na base relacional (SQLite padrão).
2. Aplica detecção heurística de anomalia (limiares Fase 1/3 + crise hipertensiva).
3. Grava alerta estruturado em ``alertas_emitidos``.
4. Grava trilha de auditoria em store NoSQL (arquivo JSON; Mongo opcional).

Uso
---
    python rpa_monitor.py --once
    python rpa_monitor.py --interval 15
    python rpa_monitor.py --init-only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

LOGGER = logging.getLogger("cardioia.rpa")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

SCHEMA_SQL = Path(__file__).with_name("schema_relational.sql")
DISCLAIMER = (
    "Este assistente não substitui atendimento médico. "
    "Em emergências, ligue 192 (SAMU)."
)

# Limiares — herança cardio-ia-fase1 (BPM > 120 / < 50) + crise hipertensiva / SpO2.
SBP_CRISIS = 180
DBP_CRISIS = 120
HR_TACHYCARDIA = 120
HR_BRADYCARDIA = 50
SPO2_CRITICAL = 90
SPO2_LOW = 94
TEMP_FEVER = 38.0  # Fase 3 Ir Além 1


@dataclass(frozen=True)
class Anomaly:
    tipo: str
    severidade: str
    mensagem: str
    limiar_aplicado: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sqlite_path() -> Path:
    raw = os.getenv("RPA_SQLITE_PATH", "./data/cardioia.db")
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _nosql_path() -> Path:
    raw = os.getenv("NOSQL_JSON_PATH", "./data/rpa_audit_store.json")
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class JsonAuditStore:
    """Persistência NoSQL em arquivo (fallback sem Docker/Mongo)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if not self.path.exists():
            self._write({"rpa_audit_logs": []})

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"rpa_audit_logs": []}

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append(self, document: dict[str, Any]) -> None:
        data = self._read()
        logs = data.setdefault("rpa_audit_logs", [])
        logs.append(document)
        self._write(data)


class MongoAuditStore:
    """Store MongoDB opcional (ativado por MONGO_URI)."""

    def __init__(self) -> None:
        from pymongo import MongoClient  # type: ignore

        uri = os.getenv("MONGO_URI", "")
        db_name = os.getenv("MONGO_DB", "cardioia")
        coll = os.getenv("MONGO_COLLECTION", "rpa_audit_logs")
        self._col = MongoClient(uri)[db_name][coll]

    def append(self, document: dict[str, Any]) -> None:
        self._col.insert_one(document)


def build_audit_store() -> JsonAuditStore | MongoAuditStore:
    if os.getenv("MONGO_URI", "").strip():
        try:
            return MongoAuditStore()
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Mongo indisponível (%s); usando JSON file.", exc)
    return JsonAuditStore(_nosql_path())


def init_database(conn: sqlite3.Connection, force: bool = False) -> None:
    """Aplica o DDL e a carga sintético se o banco estiver vazio."""
    count = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='pacientes'").fetchone()[0]
    n_pac = 0
    if count:
        n_pac = conn.execute("SELECT COUNT(*) FROM pacientes").fetchone()[0]
    if count and n_pac > 0 and not force:
        LOGGER.info("Banco já inicializado (%s pacientes).", n_pac)
        return
    if force:
        conn.executescript(
            "PRAGMA foreign_keys = OFF;"
            "DROP TABLE IF EXISTS alertas_emitidos;"
            "DROP TABLE IF EXISTS adesao_medicamentosa;"
            "DROP TABLE IF EXISTS leituras_sinais_vitais;"
            "DROP TABLE IF EXISTS pacientes;"
            "PRAGMA foreign_keys = ON;"
        )
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()
    LOGGER.info("Schema relacional aplicado a partir de %s.", SCHEMA_SQL.name)


def detect_anomalies(row: sqlite3.Row) -> list[Anomaly]:
    """Regras clínicas de demonstração (não validação assistencial)."""
    sbp = float(row["pressao_sistolica"])
    dbp = float(row["pressao_diastolica"])
    hr = float(row["frequencia_cardiaca"])
    spo2 = row["spo2"]
    temp = row["temperatura"]
    found: list[Anomaly] = []

    if sbp >= SBP_CRISIS:
        found.append(
            Anomaly(
                "CRISE_HIPERTENSIVA_SISTOLICA",
                "EMERGENCIA",
                f"PAS {sbp:.0f} mmHg ≥ {SBP_CRISIS} mmHg (crise hipertensiva de protótipo).",
                f"PAS >= {SBP_CRISIS} mmHg",
            )
        )
    if dbp >= DBP_CRISIS:
        found.append(
            Anomaly(
                "CRISE_HIPERTENSIVA_DIASTOLICA",
                "EMERGENCIA",
                f"PAD {dbp:.0f} mmHg ≥ {DBP_CRISIS} mmHg.",
                f"PAD >= {DBP_CRISIS} mmHg",
            )
        )
    if hr > HR_TACHYCARDIA:
        found.append(
            Anomaly(
                "TAQUICARDIA_REPOUSO",
                "CRITICO",
                f"FC {hr:.0f} bpm > {HR_TACHYCARDIA} bpm (limiar Fase 3).",
                f"FC > {HR_TACHYCARDIA} bpm",
            )
        )
    if hr < HR_BRADYCARDIA:
        found.append(
            Anomaly(
                "BRADICARDIA",
                "CRITICO",
                f"FC {hr:.0f} bpm < {HR_BRADYCARDIA} bpm (limiar Fase 3).",
                f"FC < {HR_BRADYCARDIA} bpm",
            )
        )
    if spo2 is not None and float(spo2) < SPO2_CRITICAL:
        found.append(
            Anomaly(
                "HIPOXEMIA_CRITICA",
                "EMERGENCIA",
                f"SpO2 {float(spo2):.0f}% < {SPO2_CRITICAL}%.",
                f"SpO2 < {SPO2_CRITICAL}%",
            )
        )
    elif spo2 is not None and float(spo2) < SPO2_LOW:
        found.append(
            Anomaly(
                "HIPOXEMIA",
                "ATENCAO",
                f"SpO2 {float(spo2):.0f}% < {SPO2_LOW}%.",
                f"SpO2 < {SPO2_LOW}%",
            )
        )
    if temp is not None and float(temp) >= TEMP_FEVER:
        found.append(
            Anomaly(
                "FEBRE",
                "ATENCAO",
                f"Temperatura {float(temp):.1f} °C ≥ {TEMP_FEVER} °C (Fase 3).",
                f"Temp >= {TEMP_FEVER} C",
            )
        )
    return found


def fetch_unprocessed(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT l.*, p.identificador, p.nome_sintetico, p.idade
        FROM leituras_sinais_vitais l
        JOIN pacientes p ON p.id = l.paciente_id
        WHERE l.processado = 0
        ORDER BY l.coletado_em ASC, l.id ASC
        """
    )
    return list(cur.fetchall())


def persist_alerts(conn: sqlite3.Connection, row: sqlite3.Row, anomalies: list[Anomaly]) -> None:
    for item in anomalies:
        conn.execute(
            """
            INSERT INTO alertas_emitidos (
                leitura_id, paciente_id, tipo, severidade, mensagem, limiar_aplicado, emitido_em
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (row["id"], row["paciente_id"], item.tipo, item.severidade, item.mensagem, item.limiar_aplicado),
        )
    conn.execute(
        "UPDATE leituras_sinais_vitais SET processado = 1, processado_em = datetime('now') WHERE id = ?",
        (row["id"],),
    )


def audit(
    store: JsonAuditStore | MongoAuditStore,
    run_id: str,
    event_type: str,
    status: str,
    payload_textual: str,
    row: sqlite3.Row | None = None,
    anomalies: list[Anomaly] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    doc: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": _utc_now(),
        "event_type": event_type,
        "status": status,
        "paciente_identificador": None if row is None else row["identificador"],
        "leitura_id": None if row is None else int(row["id"]),
        "alertas": []
        if not anomalies
        else [
            {"tipo": a.tipo, "severidade": a.severidade, "limiar": a.limiar_aplicado, "mensagem": a.mensagem}
            for a in anomalies
        ],
        "payload_textual": payload_textual,
        "metadata": {
            "disclaimer": DISCLAIMER,
            "sql_engine": "sqlite",
            **(extra or {}),
        },
    }
    if row is not None:
        doc["metadata"].update(
            {
                "pressao_sistolica": row["pressao_sistolica"],
                "pressao_diastolica": row["pressao_diastolica"],
                "frequencia_cardiaca": row["frequencia_cardiaca"],
                "spo2": row["spo2"],
            }
        )
    store.append(doc)


def process_once(conn: sqlite3.Connection, store: JsonAuditStore | MongoAuditStore, run_id: str) -> dict[str, int]:
    rows = fetch_unprocessed(conn)
    audit(
        store,
        run_id,
        "FETCH_UNPROCESSED",
        "ok",
        f"Encontradas {len(rows)} leituras sintéticas não processadas.",
        extra={"count": len(rows)},
    )
    alerts = 0
    for row in rows:
        anomalies = detect_anomalies(row)
        if anomalies:
            audit(
                store,
                run_id,
                "ANOMALY_DETECTED",
                "warn",
                f"Anomalia em {row['identificador']}: " + "; ".join(a.tipo for a in anomalies),
                row=row,
                anomalies=anomalies,
            )
            persist_alerts(conn, row, anomalies)
            alerts += len(anomalies)
            audit(
                store,
                run_id,
                "ALERT_WRITTEN",
                "ok",
                f"{len(anomalies)} alerta(s) gravados em SQL para {row['identificador']}.",
                row=row,
                anomalies=anomalies,
            )
        else:
            persist_alerts(conn, row, [])
        audit(
            store,
            run_id,
            "READING_MARKED",
            "ok",
            f"Leitura id={row['id']} marcada como processada.",
            row=row,
            anomalies=anomalies,
        )
        LOGGER.info(
            "Leitura %s (%s): %s",
            row["id"],
            row["identificador"],
            "ALERTA " + ",".join(a.tipo for a in anomalies) if anomalies else "estável",
        )
    adherence = process_adherence(conn, store, run_id)
    conn.commit()
    return {"leituras": len(rows), "alertas": alerts, "adesao": adherence}


def process_adherence(conn: sqlite3.Connection, store: JsonAuditStore | MongoAuditStore, run_id: str) -> int:
    """Loop de adesão: doses_registradas/esperadas < 80% → alerta com timestamp."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS adesao_medicamentosa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            medicamento TEXT NOT NULL,
            doses_esperadas_7d INTEGER NOT NULL,
            doses_registradas_7d INTEGER NOT NULL,
            coletado_em TEXT NOT NULL,
            processado INTEGER NOT NULL DEFAULT 0,
            processado_em TEXT
        )
        """
    )
    conn.row_factory = sqlite3.Row
    try:
        rows = list(
            conn.execute(
                """
                SELECT a.*, p.identificador
                FROM adesao_medicamentosa a
                JOIN pacientes p ON p.id = a.paciente_id
                WHERE a.processado = 0
                ORDER BY a.id ASC
                """
            )
        )
    except sqlite3.OperationalError:
        return 0
    emitted = 0
    for row in rows:
        expected = int(row["doses_esperadas_7d"]) or 1
        taken = int(row["doses_registradas_7d"])
        ratio = taken / expected
        if ratio < 0.8:
            anomaly = Anomaly(
                "BAIXA_ADESAO",
                "ATENCAO",
                f"Adesão {taken}/{expected} ({ratio:.0%}) em {row['medicamento']} — abaixo de 80%.",
                "adesao < 80% em 7d",
            )
            leitura_id = conn.execute(
                "SELECT id FROM leituras_sinais_vitais WHERE paciente_id = ? ORDER BY id DESC LIMIT 1",
                (row["paciente_id"],),
            ).fetchone()
            if leitura_id is not None:
                conn.execute(
                    """
                    INSERT INTO alertas_emitidos (
                        leitura_id, paciente_id, tipo, severidade, mensagem, limiar_aplicado, emitido_em
                    ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        int(leitura_id[0]),
                        row["paciente_id"],
                        anomaly.tipo,
                        anomaly.severidade,
                        anomaly.mensagem,
                        anomaly.limiar_aplicado,
                    ),
                )
            audit(
                store,
                run_id,
                "ADHERENCE_ALERT",
                "warn",
                anomaly.mensagem,
                extra={"paciente_identificador": row["identificador"], "ratio": round(ratio, 3)},
            )
            emitted += 1
        conn.execute(
            "UPDATE adesao_medicamentosa SET processado = 1, processado_em = datetime('now') WHERE id = ?",
            (row["id"],),
        )
    return emitted


def connect() -> sqlite3.Connection:
    path = _sqlite_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def run(once: bool, interval: int, init_only: bool, reinit: bool) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = build_audit_store()
    conn = connect()
    try:
        init_database(conn, force=reinit)
        if init_only:
            LOGGER.info("Inicialização concluída em %s", _sqlite_path())
            return 0
        while True:
            run_id = "rpa-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
            audit(store, run_id, "WORKER_START", "ok", f"Ciclo RPA iniciado (once={once}).", extra={"interval": interval})
            try:
                stats = process_once(conn, store, run_id)
                LOGGER.info("Ciclo %s: %s", run_id, stats)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Falha no ciclo RPA")
                audit(store, run_id, "ERROR", "error", str(exc))
                if once:
                    return 1
            audit(store, run_id, "WORKER_STOP", "ok", "Ciclo RPA finalizado.")
            if once:
                return 0
            time.sleep(max(1, interval))
    finally:
        conn.close()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPA CardioIA — monitoramento híbrido SQL+NoSQL.")
    parser.add_argument("--once", action="store_true", help="Processa um único ciclo e encerra (teste/smoke).")
    parser.add_argument("--interval", type=int, default=int(os.getenv("RPA_POLL_INTERVAL_SECONDS", "15")))
    parser.add_argument("--init-only", action="store_true", help="Só aplica o schema/carga sintético.")
    parser.add_argument("--reinit", action="store_true", help="Reaplica o schema (pode duplicar inserts se já houver dados).")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(run(once=args.once, interval=args.interval, init_only=args.init_only, reinit=args.reinit))
