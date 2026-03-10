"""
API Flask para el calculador de probabilidades de quiniela.

Endpoints
---------
POST /quiniela/calculate
    Calcula probabilidades dado un boleto con cuotas o probabilidades directas.
    Acepta contexto opcional por partido (forma reciente y lesiones).

POST /quiniela/odds-to-probs
    Convierte cuotas de bookmaker a probabilidades reales.

POST /quiniela/adjust
    Ajusta las probabilidades de un partido con forma reciente y/o lesiones.

GET /quiniela/health
    Health check.

Ejemplo de petición con contexto (forma + lesiones)
----------------------------------------------------
POST /quiniela/calculate
{
  "matches": [
    {
      "odds": {"home": 1.80, "draw": 3.50, "away": 4.20},
      "signs": ["1"],
      "context": {
        "home_form": {"team": "Real Madrid", "results": ["W","W","D","W","L"]},
        "away_form": {"team": "Barcelona",   "results": ["W","W","W","D","W"]},
        "injuries": [
          {"name": "Bellingham", "team_role": "home", "importance": 5, "reason": "lesión muscular"}
        ]
      }
    },
    {
      "odds": {"home": 2.10, "draw": 3.20, "away": 3.40},
      "signs": ["1", "X"]
    }
  ],
  "prizes": {"first": 1500000, "second": 30000, "third": 1000},
  "base_cost": 0.50
}

Escala de importancia de lesiones (campo "importance")
-------------------------------------------------------
  1 = Rotación (suplente habitual)
  2 = Titular habitual
  3 = Titular importante (internacional A)
  4 = Jugador clave (capitán, referencia del equipo)
  5 = Imprescindible (Mbappe, Haaland, etc.)
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
from form_adjuster import adjust_probabilities, context_from_dict

app = Flask(__name__)


def _parse_match(match_data: dict) -> tuple[TicketSelection, MatchProbabilities, dict | None]:
    """
    Parsea un partido del JSON: convierte odds/probs, signos y contexto opcional.

    Retorna (TicketSelection, MatchProbabilities ajustadas, adjustment_summary | None)
    """
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

    # Ajuste opcional por forma y lesiones
    adjustment_info = None
    if "context" in match_data:
        context = context_from_dict(match_data["context"])
        if not context.is_empty:
            probs, adjustment_info = adjust_probabilities(probs, context)

    selection = TicketSelection(signs=signs)
    return selection, probs, adjustment_info


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
        adjustments = []
        for i, m in enumerate(matches_raw):
            sel, prob, adj = _parse_match(m)
            selections.append(sel)
            probs_list.append(prob)
            adjustments.append(adj)
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

    # Incluir resumen de ajustes aplicados (sólo los no nulos)
    applied = {str(i + 1): adj for i, adj in enumerate(adjustments) if adj is not None}
    if applied:
        report["context_adjustments"] = applied

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


@app.route("/quiniela/adjust", methods=["POST"])
def adjust_match():
    """
    Ajusta las probabilidades de UN partido con forma reciente y/o lesiones.

    Body JSON::

        {
          "odds":  {"home": 1.80, "draw": 3.50, "away": 4.20},   // o "probs"
          "context": {
            "home_form": {"team": "Atlético", "results": ["W","W","D","W","W"]},
            "away_form": {"team": "Tottenham", "results": ["L","L","D","L","L"]},
            "injuries": [
              {"name": "Son Heung-min", "team_role": "away", "importance": 4, "reason": "sanción"}
            ]
          }
        }

    Respuesta: probabilidades originales, ajustadas y desglose de cada ajuste.
    """
    data = request.get_json(force=True)

    try:
        if "odds" in data:
            o = data["odds"]
            base_probs = odds_to_probabilities(
                float(o["home"]), float(o["draw"]), float(o["away"]),
                remove_margin=data.get("remove_margin", True),
            )
            margin = bookmaker_margin(float(o["home"]), float(o["draw"]), float(o["away"]))
        elif "probs" in data:
            p = data["probs"]
            base_probs = MatchProbabilities(
                home=float(p["home"]), draw=float(p["draw"]), away=float(p["away"])
            )
            margin = None
        else:
            return jsonify({"error": "Se necesita 'odds' o 'probs'."}), 400

        if "context" not in data:
            return jsonify({"error": "Se necesita 'context' con home_form, away_form y/o injuries."}), 400

        context = context_from_dict(data["context"])
        if context.is_empty:
            return jsonify({"error": "El contexto está vacío. Añade forma o lesiones."}), 400

        _, summary = adjust_probabilities(base_probs, context)

    except (ValueError, KeyError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

    if margin is not None:
        summary["bookmaker_margin_pct"] = margin

    return jsonify(summary)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
