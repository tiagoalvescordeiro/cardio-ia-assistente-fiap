"""
Camada social ECO — pulso k-anônimo e heatmap agregado.

Todos os números são SINTÉTICOS (protótipo acadêmico).
Não há geolocalização, GPS, IP-to-geo nem PII. k ≥ 10.
"""

from __future__ import annotations

from typing import Any

K_MIN = 10
DISCLAIMER_GEO = (
    "Agregado sintético de região metropolitana. "
    "Este protótipo não coleta localização real."
)

# Contagens já no piso k-anônimo (nunca < 10).
SYNTHETIC_METROS: list[dict[str, Any]] = [
    {
        "id": "rm-sc-vale",
        "label": "Vale do Itajaí / Grande Blumenau",
        "intensity": 0.86,
        "count": 18,
        "queixa": "palpitações por estresse",
    },
    {
        "id": "rm-sc-fln",
        "label": "Grande Florianópolis",
        "intensity": 0.64,
        "count": 14,
        "queixa": "aperto situacional após pico de tensão",
    },
    {
        "id": "rm-sc-nort",
        "label": "Norte catarinense (Joinville–Jaraguá)",
        "intensity": 0.52,
        "count": 12,
        "queixa": "taquicardia após jornada intensa",
    },
    {
        "id": "rm-sc-oeste",
        "label": "Oeste catarinense (Chapecó–Xanxerê)",
        "intensity": 0.41,
        "count": 11,
        "queixa": "insônia e tensão muscular",
    },
    {
        "id": "rm-sc-sul",
        "label": "Sul catarinense (Criciúma–Tubarão)",
        "intensity": 0.33,
        "count": 10,
        "queixa": "nó na garganta em sobrecarga",
    },
]

NORMALIZATION_NARRATIVES: tuple[str, ...] = (
    "Composto sintético: após uma reunião tensa, alguém da mesma faixa de queixa "
    "sentiu o coração disparar. Sem irradiação nem suor frio, a descarga autonômica "
    "cedeu com 4-7-8. Isso descreve universalidade do sintoma — não é diagnóstico.",
    "Composto sintético: aperto no peito depois de um pico de estresse, sem desmaio. "
    "O rastreio de alarme veio primeiro; só então a respiração. SCA possível nunca "
    "é «só ansiedade».",
    "Composto sintético: palpitações noturnas em quem vinha dormindo mal. Sem red flag, "
    "o corpo em luta-ou-fuga é compartilhado. Avaliação presencial permanece aberta.",
)

DEFAULT_METRO = SYNTHETIC_METROS[0]


def pulse_payload(queixa: str | None = None) -> dict[str, Any]:
    """Contrato JSON para GET /api/eco-pulse e o bloco `ui.eco_social`."""
    metro = DEFAULT_METRO
    label_queixa = queixa or metro["queixa"]
    count = int(metro["count"])
    if count < K_MIN:
        count = K_MIN
    headline = (
        f"Na sua região metropolitana, {count} pessoas relataram a mesma queixa "
        f"de {label_queixa} hoje."
    )
    heatmap = [
        {
            "id": m["id"],
            "label": m["label"],
            "intensity": m["intensity"],
            "count_bucket": f"{m['count']} (k≥{K_MIN})",
            "cx": 12 + i * 21,
            "cy": 38 + (i % 2) * 18,
            "r": 10 + int(m["intensity"] * 10),
        }
        for i, m in enumerate(SYNTHETIC_METROS)
    ]
    return {
        "headline": headline,
        "metro_label": metro["label"],
        "count": count,
        "queixa": label_queixa,
        "k_anonymity": K_MIN,
        "geo_collected": False,
        "synthetic": True,
        "disclaimer": DISCLAIMER_GEO,
        "heatmap": heatmap,
        "narratives": list(NORMALIZATION_NARRATIVES),
        "narrative": NORMALIZATION_NARRATIVES[0],
    }


def eco_social_ui(show_breathing: bool) -> dict[str, Any] | None:
    """Anexa o pulso à UI somente no ramo 4-7-8 (rastreio negativo)."""
    if not show_breathing:
        return None
    return pulse_payload("palpitações por estresse")
