"""
API Flask para el calculador de probabilidades de quiniela.

Endpoints
---------
POST /quiniela/calculate
    Calcula probabilidades dado un boleto con cuotas o probabilidades directas.

POST /quiniela/odds-to-probs
    Convierte cuotas de bookmaker a probabilidades reales.

GET /quiniela/health
    Health check.

Ejemplo de petición
-------------------
POST /quiniela/calculate
{
  "matches": [
    {
      "odds": {"home": 1.80, "draw": 3.50, "away": 4.20},
      "signs": ["1"]
    },
    {
      "odds": {"home": 2.10, "draw": 3.20, "away": 3.40},
      "signs": ["1", "X"]
    },
    ...
  ],
  "prizes": {
    "first": 1500000,
    "second": 30000,
    "third": 1000
  },
  "base_cost": 0.50
}
"""

from flask import Flask, request, jsonify
from calculator import (
    MatchProbabilities,
    QuinielaTicket,
    QuinielaCalculator,
    TicketSelection,
    bookmaker_margin,
    odds_to_probabilities,
)

app = Flask(__name__)


def _parse_match(match_data: dict) -> tuple[TicketSelection, MatchProbabilities]:
    """Parsea un partido del JSON: convierte odds/probs y signos."""
    signs = match_data.get("signs")
    if not signs:
        raise ValueError("Cada partido necesita 'signs' (lista de signos elegidos).")

    # Admitimos cuotas u probabilidades directas
    if "odds" in match_data:
        o = match_data["odds"]
        probs = odds_to_probabilities(
            float(o["home"]), float(o["draw"]), float(o["away"]),
            remove_margin=match_data.get("remove_margin", True),
        )
    elif "probs" in match_data:
        p = match_data["probs"]
        probs = MatchProbabilities(
            home=float(p["home"]),
            draw=float(p["draw"]),
            away=float(p["away"]),
        )
    else:
        raise ValueError("Cada partido necesita 'odds' o 'probs'.")

    selection = TicketSelection(signs=signs)
    return selection, probs


@app.route("/quiniela/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/quiniela/calculate", methods=["POST"])
def calculate():
    """
    Calcula probabilidades completas de un boleto de quiniela.

    Body JSON:
      matches  : list[{odds|probs, signs, ?remove_margin}]  (exactamente 15)
      prizes   : {first, second, third}  (opcional, premios en €)
      base_cost: float  (opcional, coste por combinación, por defecto 0.50 €)
    """
    data = request.get_json(force=True)

    matches_raw = data.get("matches", [])
    if len(matches_raw) != 15:
        return jsonify({"error": f"Se necesitan 15 partidos, recibidos: {len(matches_raw)}"}), 400

    try:
        selections = []
        probs_list = []
        for i, m in enumerate(matches_raw):
            sel, prob = _parse_match(m)
            selections.append(sel)
            probs_list.append(prob)
    except (ValueError, KeyError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

    ticket = QuinielaTicket(matches=selections)
    calc = QuinielaCalculator(ticket, probs_list)

    prizes = data.get("prizes", {})
    base_cost = float(data.get("base_cost", 0.50))

    report = calc.full_report(
        prize_1st=float(prizes.get("first", 1_500_000)),
        prize_2nd=float(prizes.get("second", 30_000)),
        prize_3rd=float(prizes.get("third", 1_000)),
        base_cost=base_cost,
    )

    return jsonify(report)


@app.route("/quiniela/odds-to-probs", methods=["POST"])
def convert_odds():
    """
    Convierte cuotas decimales a probabilidades.

    Body JSON:
      home          : float   cuota victoria local
      draw          : float   cuota empate
      away          : float   cuota visitante
      remove_margin : bool    eliminar margen bookmaker (default: true)

    Respuesta:
      p_home, p_draw, p_away, margin_pct
    """
    data = request.get_json(force=True)
    try:
        home = float(data["home"])
        draw = float(data["draw"])
        away = float(data["away"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Se necesitan 'home', 'draw' y 'away' como floats."}), 400

    remove_margin = bool(data.get("remove_margin", True))
    probs = odds_to_probabilities(home, draw, away, remove_margin)
    margin = bookmaker_margin(home, draw, away)

    return jsonify({
        "p_home": round(probs.home, 6),
        "p_draw": round(probs.draw, 6),
        "p_away": round(probs.away, 6),
        "margin_pct": margin,
        "margin_removed": remove_margin,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
