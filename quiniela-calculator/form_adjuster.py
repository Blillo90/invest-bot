"""
Ajuste de probabilidades por forma reciente y lesiones
=======================================================

Premisa: las cuotas del mercado ya incorporan la mayor parte de la información
disponible. Este módulo aplica **correcciones marginales** basadas en:

  1. Forma reciente (últimos N partidos): shift máximo ±MAX_FORM_SHIFT
  2. Lesiones / sanciones: reducción proporcional a la importancia del jugador

Principio de diseño
-------------------
Los ajustes son pequeños (±3-8% típicamente) para no sobreescribir la señal del
mercado. Son más útiles cuando:
  - Se dispone de noticias de lesiones más recientes que las cuotas
  - Hay una racha de forma llamativa en los últimos 5 partidos

Escala de importancia de lesiones (1-5)
---------------------------------------
  1 — Rotación (suplente habitual)            → ~0.5% impacto en P(ganar)
  2 — Titular habitual                        → ~1.5%
  3 — Titular importante (internacional A)    → ~3.0%
  4 — Jugador clave (capitán, referencia)     → ~5.0%
  5 — Imprescindible (Mbappe, Haaland, etc.)  → ~7.5%
"""

from __future__ import annotations

from dataclasses import dataclass, field

from calculator import MatchProbabilities


# ── Constantes de calibración ──────────────────────────────────────────────

# Shift máximo aplicable por diferencia de forma (home_score - away_score = 1.0)
MAX_FORM_SHIFT = 0.08

# Impacto por lesionado sobre la P(ganar) del equipo afectado
IMPORTANCE_IMPACT: dict[int, float] = {
    1: 0.005,   # rotación
    2: 0.015,   # titular habitual
    3: 0.030,   # titular importante
    4: 0.050,   # jugador clave
    5: 0.075,   # imprescindible
}

IMPORTANCE_LABELS: dict[int, str] = {
    1: "Rotación",
    2: "Titular habitual",
    3: "Titular importante",
    4: "Jugador clave",
    5: "Imprescindible",
}

# Probabilidad mínima permitida para cualquier resultado (evita p=0)
MIN_PROB = 0.03


# ── Modelos de datos ────────────────────────────────────────────────────────

@dataclass
class TeamForm:
    """
    Forma reciente de un equipo.

    Parámetros
    ----------
    team    : Nombre del equipo (informativo).
    results : Lista de resultados ['W', 'D', 'L'] — el más reciente primero.
              Usar los últimos 5 como referencia, hasta 10 como máximo útil.
    """
    team: str
    results: list[str]

    def __post_init__(self) -> None:
        valid = {"W", "D", "L"}
        for r in self.results:
            if r not in valid:
                raise ValueError(f"Resultado inválido: {r!r}. Usa 'W', 'D' o 'L'.")

    def form_score(self) -> float:
        """Puntos obtenidos / máximo posible → [0.0, 1.0]."""
        if not self.results:
            return 0.5  # sin datos: neutral
        pts = sum(3 if r == "W" else 1 if r == "D" else 0 for r in self.results)
        return pts / (3 * len(self.results))

    def recent_summary(self) -> str:
        """Cadena resumen, ej: 'W W D L W (3-1-1)'."""
        w = self.results.count("W")
        d = self.results.count("D")
        l = self.results.count("L")
        return f"{''.join(self.results)} ({w}V-{d}E-{l}D)"


@dataclass
class InjuredPlayer:
    """
    Jugador lesionado o sancionado que impacta al equipo.

    Parámetros
    ----------
    name      : Nombre del jugador.
    team_role : 'home' o 'away'.
    importance: Nivel 1-5 (ver escala en la cabecera del módulo).
    reason    : Motivo (lesión, sanción, selección, etc.) — sólo informativo.
    """
    name: str
    team_role: str        # 'home' o 'away'
    importance: int       # 1-5
    reason: str = "lesión"

    def __post_init__(self) -> None:
        if self.importance not in IMPORTANCE_IMPACT:
            raise ValueError(
                f"importance debe ser 1-5, recibido: {self.importance}. "
                f"1=rotación, 2=titular, 3=importante, 4=clave, 5=imprescindible."
            )
        if self.team_role not in ("home", "away"):
            raise ValueError("team_role debe ser 'home' o 'away'.")

    @property
    def impact(self) -> float:
        """Fracción de reducción sobre P(ganar) del equipo afectado."""
        return IMPORTANCE_IMPACT[self.importance]

    @property
    def importance_label(self) -> str:
        return IMPORTANCE_LABELS[self.importance]


@dataclass
class MatchContext:
    """
    Contexto adicional para ajustar las probabilidades de un partido.

    Todos los campos son opcionales; si no se proporcionan no se aplica
    ese ajuste.
    """
    home_form: TeamForm | None = None
    away_form: TeamForm | None = None
    injuries: list[InjuredPlayer] = field(default_factory=list)

    @property
    def has_form_data(self) -> bool:
        return self.home_form is not None or self.away_form is not None

    @property
    def has_injury_data(self) -> bool:
        return len(self.injuries) > 0

    @property
    def is_empty(self) -> bool:
        return not self.has_form_data and not self.has_injury_data


# ── Motor de ajuste ─────────────────────────────────────────────────────────

def adjust_probabilities(
    base: MatchProbabilities,
    context: MatchContext,
) -> tuple[MatchProbabilities, dict]:
    """
    Ajusta probabilidades de mercado con forma reciente y lesiones.

    El ajuste es siempre pequeño y acotado para no sobreescribir la señal
    del mercado. Retorna las probabilidades ajustadas y un resumen detallado.

    Parámetros
    ----------
    base    : Probabilidades originales (del mercado, sin margen).
    context : Contexto de forma y lesiones.

    Retorna
    -------
    (MatchProbabilities ajustadas, dict con desglose del ajuste)
    """
    p_home = base.home
    p_draw = base.draw
    p_away = base.away

    deltas: list[dict] = []

    # ── 1. Ajuste por forma reciente ─────────────────────────────────────
    form_shift_applied = 0.0
    if context.has_form_data:
        home_score = context.home_form.form_score() if context.home_form else 0.5
        away_score = context.away_form.form_score() if context.away_form else 0.5

        # balance ∈ [-1, 1]: positivo → local en mejor forma
        balance = home_score - away_score
        shift = balance * MAX_FORM_SHIFT
        form_shift_applied = shift

        # 75% del shift va directo de away→home (o al revés)
        # 5% extra: leve reducción del empate cuando hay desnivel claro de forma
        p_home += shift * 0.75
        p_away -= shift * 0.75
        p_draw -= abs(shift) * 0.05

        deltas.append({
            "tipo": "forma",
            "home_score": round(home_score, 3),
            "away_score": round(away_score, 3),
            "balance": round(balance, 3),
            "delta_1": round(shift * 0.75, 4),
            "delta_X": round(-abs(shift) * 0.05, 4),
            "delta_2": round(-shift * 0.75, 4),
        })

    # ── 2. Ajuste por lesiones / sanciones ───────────────────────────────
    for player in context.injuries:
        if player.team_role == "home":
            # Reducir P(home win), distribuir 50/50 a draw y away
            raw_reduction = p_home * player.impact
            p_home -= raw_reduction
            p_draw += raw_reduction * 0.5
            p_away += raw_reduction * 0.5
            deltas.append({
                "tipo": "lesión",
                "jugador": player.name,
                "equipo": "local",
                "importancia": f"{player.importance} ({player.importance_label})",
                "motivo": player.reason,
                "delta_1": round(-raw_reduction, 4),
                "delta_X": round(raw_reduction * 0.5, 4),
                "delta_2": round(raw_reduction * 0.5, 4),
            })
        else:
            raw_reduction = p_away * player.impact
            p_away -= raw_reduction
            p_home += raw_reduction * 0.5
            p_draw += raw_reduction * 0.5
            deltas.append({
                "tipo": "lesión",
                "jugador": player.name,
                "equipo": "visitante",
                "importancia": f"{player.importance} ({player.importance_label})",
                "motivo": player.reason,
                "delta_1": round(raw_reduction * 0.5, 4),
                "delta_X": round(raw_reduction * 0.5, 4),
                "delta_2": round(-raw_reduction, 4),
            })

    # ── 3. Clip + renormalizar ────────────────────────────────────────────
    p_home = max(p_home, MIN_PROB)
    p_draw = max(p_draw, MIN_PROB)
    p_away = max(p_away, MIN_PROB)
    total = p_home + p_draw + p_away

    adjusted = MatchProbabilities(
        home=p_home / total,
        draw=p_draw / total,
        away=p_away / total,
    )

    summary = {
        "original":   {"1": round(base.home, 4),     "X": round(base.draw, 4),     "2": round(base.away, 4)},
        "adjusted":   {"1": round(adjusted.home, 4), "X": round(adjusted.draw, 4), "2": round(adjusted.away, 4)},
        "delta_total":{"1": round(adjusted.home - base.home, 4),
                       "X": round(adjusted.draw - base.draw, 4),
                       "2": round(adjusted.away - base.away, 4)},
        "adjustments": deltas,
    }

    return adjusted, summary


# ── Parseo desde dict (para la API) ─────────────────────────────────────────

def context_from_dict(data: dict) -> MatchContext:
    """
    Construye un MatchContext desde un diccionario JSON.

    Formato esperado (todos los campos opcionales)::

        {
          "home_form": {"team": "Real Madrid", "results": ["W","W","D","W","L"]},
          "away_form": {"team": "Barcelona",   "results": ["W","W","W","D","W"]},
          "injuries": [
            {"name": "Bellingham", "team_role": "home", "importance": 5, "reason": "lesión muscular"},
            {"name": "Lewandowski", "team_role": "away", "importance": 4}
          ]
        }
    """
    home_form = None
    away_form = None
    injuries: list[InjuredPlayer] = []

    if "home_form" in data:
        hf = data["home_form"]
        home_form = TeamForm(team=hf.get("team", "local"), results=hf["results"])

    if "away_form" in data:
        af = data["away_form"]
        away_form = TeamForm(team=af.get("team", "visitante"), results=af["results"])

    for inj in data.get("injuries", []):
        injuries.append(InjuredPlayer(
            name=inj["name"],
            team_role=inj["team_role"],
            importance=int(inj["importance"]),
            reason=inj.get("reason", "lesión"),
        ))

    return MatchContext(home_form=home_form, away_form=away_form, injuries=injuries)
