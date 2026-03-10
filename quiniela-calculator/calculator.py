"""
Quiniela Probability Calculator
================================

Calcula la probabilidad de acertar una quiniela de fútbol (15 partidos)
con soporte para:
  - Múltiples signos por partido (1, X, 2, 1X, 12, X2, 1X2)
  - Conversión de cuotas de apuestas a probabilidades reales
  - Distribución de premios (14/15, 15/15, etc.)
  - Valor esperado del boleto

Matemáticas clave
-----------------
Para cada partido i con n signos seleccionados S_i ⊆ {1, X, 2}:

    P(acierto_i) = Σ_{j ∈ S_i} p_{i,j}

Probabilidad de acertar TODO el boleto (independencia entre partidos):

    P(pleno) = Π_{i=1}^{15} P(acierto_i)

Distribución de aciertos: Poisson Binomial via programación dinámica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Sign = Literal["1", "X", "2"]
SIGNS: list[Sign] = ["1", "X", "2"]


# ---------------------------------------------------------------------------
# Modelos de datos
# ---------------------------------------------------------------------------

@dataclass
class MatchOdds:
    """Cuotas decimales de un partido (ej. 1.80 / 3.50 / 4.20)."""
    home: float    # cuota victoria local  (signo 1)
    draw: float    # cuota empate          (signo X)
    away: float    # cuota victoria visita (signo 2)

    def to_probabilities(self, remove_margin: bool = True) -> "MatchProbabilities":
        """
        Convierte cuotas decimales a probabilidades reales.

        Si remove_margin=True elimina el margen del bookmaker (overround)
        normalizando para que sumen exactamente 1.
        """
        raw_h = 1.0 / self.home
        raw_d = 1.0 / self.draw
        raw_a = 1.0 / self.away
        total = raw_h + raw_d + raw_a
        if remove_margin:
            return MatchProbabilities(
                home=raw_h / total,
                draw=raw_d / total,
                away=raw_a / total,
            )
        return MatchProbabilities(home=raw_h, draw=raw_d, away=raw_a)


@dataclass
class MatchProbabilities:
    """Probabilidades para los tres resultados de un partido."""
    home: float   # P(victoria local)
    draw: float   # P(empate)
    away: float   # P(victoria visita)

    def __post_init__(self) -> None:
        total = self.home + self.draw + self.away
        if not (0.999 <= total <= 1.001):
            raise ValueError(
                f"Las probabilidades deben sumar ~1.0, suma actual: {total:.4f}"
            )

    def p(self, sign: Sign) -> float:
        """Devuelve la probabilidad del signo indicado."""
        mapping = {"1": self.home, "X": self.draw, "2": self.away}
        return mapping[sign]

    @classmethod
    def uniform(cls) -> "MatchProbabilities":
        """Distribución uniforme (sin información previa)."""
        return cls(home=1 / 3, draw=1 / 3, away=1 / 3)


@dataclass
class TicketSelection:
    """Selección de signos para un partido del boleto."""
    signs: list[Sign]

    def __post_init__(self) -> None:
        valid = {"1", "X", "2"}
        for s in self.signs:
            if s not in valid:
                raise ValueError(f"Signo inválido: {s!r}. Usa '1', 'X' o '2'.")
        if not self.signs:
            raise ValueError("Debes seleccionar al menos un signo por partido.")
        self.signs = list(dict.fromkeys(self.signs))  # deduplica

    @property
    def multiplier(self) -> int:
        """Número de signos seleccionados (1=simple, 2=doble, 3=triple)."""
        return len(self.signs)


@dataclass
class QuinielaTicket:
    """Boleto completo de quiniela con 15 partidos."""
    matches: list[TicketSelection] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.matches) != 15:
            raise ValueError(
                f"La quiniela necesita exactamente 15 partidos, "
                f"tienes {len(self.matches)}."
            )

    @property
    def total_combinations(self) -> int:
        """Total de combinaciones del boleto (coste en 'jornadas')."""
        result = 1
        for m in self.matches:
            result *= m.multiplier
        return result


# ---------------------------------------------------------------------------
# Motor de cálculo
# ---------------------------------------------------------------------------

class QuinielaCalculator:
    """
    Calcula probabilidades y valor esperado de un boleto de quiniela.

    Parámetros
    ----------
    ticket : QuinielaTicket
        Boleto con la selección de signos para cada partido.
    probabilities : list[MatchProbabilities]
        Probabilidades reales de cada partido (15 partidos).
    """

    def __init__(
        self,
        ticket: QuinielaTicket,
        probabilities: list[MatchProbabilities],
    ) -> None:
        if len(probabilities) != 15:
            raise ValueError("Se necesitan probabilidades para los 15 partidos.")
        self.ticket = ticket
        self.probs = probabilities

        # P(acierto) por partido dada la selección del boleto
        self._p_success: list[float] = [
            sum(prob.p(sign) for sign in sel.signs)
            for sel, prob in zip(ticket.matches, probabilities)
        ]

    # ------------------------------------------------------------------
    # Probabilidad de pleno (todos los aciertos)
    # ------------------------------------------------------------------

    def p_full_correct(self) -> float:
        """P(acertar los 15 partidos)."""
        result = 1.0
        for p in self._p_success:
            result *= p
        return result

    # ------------------------------------------------------------------
    # Distribución de Poisson Binomial (exactamente k aciertos)
    # ------------------------------------------------------------------

    def prize_distribution(self) -> list[float]:
        """
        Devuelve una lista dp[k] = P(exactamente k aciertos) para k=0..15.

        Algoritmo: programación dinámica sobre la distribución de
        Poisson Binomial (suma de Bernoullis independientes con p_i distintos).

        Complejidad: O(n²) tiempo y espacio donde n=15.
        """
        n = len(self._p_success)
        # dp[k] = P(exactamente k aciertos en los primeros i partidos)
        dp = [0.0] * (n + 1)
        dp[0] = 1.0

        for p in self._p_success:
            # Recorremos de mayor a menor para actualizar in-place sin solapar
            for k in range(n, 0, -1):
                dp[k] = dp[k] * (1 - p) + dp[k - 1] * p
            dp[0] *= (1 - p)

        return dp

    # ------------------------------------------------------------------
    # Probabilidades acumuladas de premio
    # ------------------------------------------------------------------

    def p_at_least_k(self, k: int) -> float:
        """P(acertar al menos k partidos)."""
        dist = self.prize_distribution()
        return sum(dist[k:])

    def prize_summary(self) -> dict[str, float]:
        """
        Resumen de probabilidades por categoría de premio habitual.

        Categorías de La Quiniela española:
          - 1ª cat : 15 aciertos
          - 2ª cat : 14 aciertos
          - 3ª cat : 13 aciertos
          - 4ª cat : 10 aciertos (especial Joker)
        """
        dist = self.prize_distribution()
        return {
            "15/15 (1ª cat)": dist[15],
            "14/15 (2ª cat)": dist[14],
            "13/15 (3ª cat)": dist[13],
            "≥13/15 (algún premio)": sum(dist[13:]),
        }

    # ------------------------------------------------------------------
    # Valor esperado
    # ------------------------------------------------------------------

    def expected_value(
        self,
        prize_1st: float,
        prize_2nd: float,
        prize_3rd: float,
        ticket_cost: float,
    ) -> dict[str, float]:
        """
        Calcula el valor esperado (EV) del boleto.

        Parámetros
        ----------
        prize_1st  : Premio de 1ª categoría (15 aciertos) en euros.
        prize_2nd  : Premio de 2ª categoría (14 aciertos) en euros.
        prize_3rd  : Premio de 3ª categoría (13 aciertos) en euros.
        ticket_cost: Coste del boleto en euros.

        Devuelve
        --------
        dict con 'ev_total', 'ev_per_euro' y 'roi_pct'.
        """
        dist = self.prize_distribution()
        ev = (
            dist[15] * prize_1st
            + dist[14] * prize_2nd
            + dist[13] * prize_3rd
        )
        roi = (ev - ticket_cost) / ticket_cost * 100
        return {
            "ev_total": ev,
            "ev_per_euro": ev / ticket_cost if ticket_cost > 0 else 0,
            "roi_pct": roi,
        }

    # ------------------------------------------------------------------
    # Análisis por partido
    # ------------------------------------------------------------------

    def match_analysis(self) -> list[dict]:
        """
        Detalle por partido: signos elegidos, P(acierto) y aportación al boleto.
        """
        result = []
        for i, (sel, prob, p_succ) in enumerate(
            zip(self.ticket.matches, self.probs, self._p_success)
        ):
            result.append({
                "match": i + 1,
                "signs_selected": sel.signs,
                "multiplier": sel.multiplier,
                "p_home": round(prob.home, 4),
                "p_draw": round(prob.draw, 4),
                "p_away": round(prob.away, 4),
                "p_success": round(p_succ, 4),
            })
        return result

    # ------------------------------------------------------------------
    # Resumen completo
    # ------------------------------------------------------------------

    def full_report(
        self,
        prize_1st: float = 1_500_000,
        prize_2nd: float = 30_000,
        prize_3rd: float = 1_000,
        base_cost: float = 0.50,
    ) -> dict:
        """
        Informe completo del boleto.

        prize_* : premios orientativos de La Quiniela española.
        base_cost: precio de una combinación simple (0.50 €).
        """
        combinations = self.ticket.total_combinations
        ticket_cost = base_cost * combinations
        dist = self.prize_distribution()
        ev_data = self.expected_value(prize_1st, prize_2nd, prize_3rd, ticket_cost)

        return {
            "ticket_combinations": combinations,
            "ticket_cost_eur": round(ticket_cost, 2),
            "p_full_correct": self.p_full_correct(),
            "p_14_correct": dist[14],
            "p_13_correct": dist[13],
            "p_any_prize": sum(dist[13:]),
            "prize_distribution": {
                str(k): round(v, 10) for k, v in enumerate(dist)
            },
            "expected_value": ev_data,
            "match_analysis": self.match_analysis(),
        }


# ---------------------------------------------------------------------------
# Utilidades: estimación de probabilidades desde cuotas
# ---------------------------------------------------------------------------

def odds_to_probabilities(
    home_odds: float,
    draw_odds: float,
    away_odds: float,
    remove_margin: bool = True,
) -> MatchProbabilities:
    """Convierte cuotas decimales a probabilidades (elimina margen opcional)."""
    return MatchOdds(home_odds, draw_odds, away_odds).to_probabilities(remove_margin)


def bookmaker_margin(home_odds: float, draw_odds: float, away_odds: float) -> float:
    """Calcula el margen del bookmaker (overround) en porcentaje."""
    overround = 1 / home_odds + 1 / draw_odds + 1 / away_odds
    return round((overround - 1) * 100, 2)


# ---------------------------------------------------------------------------
# Ejemplo de uso
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    # 15 partidos con cuotas de ejemplo
    raw_odds = [
        (1.80, 3.50, 4.20),   # Partido 1: local favorito
        (2.10, 3.20, 3.40),   # Partido 2: igualado
        (1.50, 3.80, 6.00),   # Partido 3: local muy favorito
        (3.00, 3.10, 2.50),   # Partido 4: visitante favorito
        (2.00, 3.30, 3.80),   # Partido 5
        (1.70, 3.60, 5.00),   # Partido 6
        (2.50, 3.20, 2.80),   # Partido 7: muy igualado
        (1.40, 4.00, 8.00),   # Partido 8: local dominante
        (2.20, 3.40, 3.10),   # Partido 9
        (1.90, 3.50, 3.90),   # Partido 10
        (2.80, 3.20, 2.60),   # Partido 11: visitante ligero favorito
        (1.60, 3.70, 5.50),   # Partido 12
        (2.30, 3.30, 3.00),   # Partido 13: igualado
        (1.75, 3.55, 4.50),   # Partido 14
        (2.00, 3.20, 3.80),   # Partido 15
    ]

    # Convertir cuotas a probabilidades reales
    match_probs = [
        odds_to_probabilities(h, d, a) for h, d, a in raw_odds
    ]

    # Boleto: seleccionamos el signo más probable en cada partido
    # (con algún doble en partidos igualados)
    selections = [
        TicketSelection(["1"]),      # Partido 1: solo local
        TicketSelection(["1", "X"]), # Partido 2: doble (1X)
        TicketSelection(["1"]),      # Partido 3
        TicketSelection(["2"]),      # Partido 4
        TicketSelection(["1"]),      # Partido 5
        TicketSelection(["1"]),      # Partido 6
        TicketSelection(["1", "X"]), # Partido 7: doble
        TicketSelection(["1"]),      # Partido 8
        TicketSelection(["1"]),      # Partido 9
        TicketSelection(["1"]),      # Partido 10
        TicketSelection(["2"]),      # Partido 11
        TicketSelection(["1"]),      # Partido 12
        TicketSelection(["X", "2"]), # Partido 13: doble
        TicketSelection(["1"]),      # Partido 14
        TicketSelection(["1"]),      # Partido 15
    ]

    ticket = QuinielaTicket(matches=selections)
    calc = QuinielaCalculator(ticket, match_probs)
    report = calc.full_report()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nMargen bookmaker partido 1: {bookmaker_margin(*raw_odds[0])}%")
