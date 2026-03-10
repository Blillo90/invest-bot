"""
Cálculo Quiniela Jornada 47 — 10-12 marzo 2026
Partidos: UCL (octavos ida), UEL (octavos ida), UECL (octavos ida)

Cuotas obtenidas de Stake / SBGGlobal / Sportsgambler (09-10/03/2026)
Lesiones/sanciones aplicadas según noticias confirmadas.
"""

import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from calculator import (
    MatchProbabilities,
    QuinielaTicket,
    QuinielaCalculator,
    TicketSelection,
    odds_to_probabilities,
)
from form_adjuster import adjust_probabilities, context_from_dict

# ─────────────────────────────────────────────────────────────────────────────
# 1. CUOTAS DECIMALES  (home / draw / away)
# ─────────────────────────────────────────────────────────────────────────────
# Americana → decimal: positivo=(x/100)+1 ; negativo=(100/|x|)+1

raw_odds = [
    # UCL — Martes 10 mar
    (4.80,  4.60,  1.64),   # 1  Atalanta        vs Bayern Múnich
    (1.66,  3.75,  5.40),   # 2  Atlético Madrid  vs Tottenham
    (2.90,  3.90,  2.28),   # 3  Newcastle        vs Barcelona
    # UCL — Miércoles 11 mar (18:45)
    (5.80,  4.20,  1.59),   # 4  Bayer Leverkusen vs Arsenal
    (2.60,  3.70,  2.60),   # 5  Bodø/Glimt       vs Sporting CP
    # UCL — Miércoles 11 mar (21:00)
    (1.81,  3.90,  4.52),   # 6  PSG              vs Chelsea
    # UEL — Jueves 12 mar (18:45)
    (2.05,  3.45,  3.45),   # 7  Stuttgart        vs Oporto
    (3.60,  3.20,  2.11),   # 8  Panathinaikos    vs Betis
    # UEL — Jueves 12 mar (21:00)
    (3.10,  2.95,  2.47),   # 9  Bologna          vs Roma
    (2.95,  3.25,  2.39),   # 10 Lille            vs Aston Villa
    (2.08,  3.40,  3.45),   # 11 Celta            vs Lyon
    (2.95,  3.30,  2.35),   # 12 Ferencváros      vs Braga
    (2.58,  3.35,  2.65),   # 13 Racing Genk      vs Friburgo
    # UECL — Jueves 12 mar (18:45)
    (3.20,  3.45,  2.29),   # 14 Samsunspor       vs Rayo Vallecano
    # UCL — Miércoles 11 mar (21:00)
    (3.10,  3.65,  2.27),   # 15 Real Madrid      vs Manchester City
]

# ─────────────────────────────────────────────────────────────────────────────
# 2. CONTEXTO DE LESIONES / SANCIONES
# ─────────────────────────────────────────────────────────────────────────────
# Importancia: 1=rotación, 2=titular, 3=titular importante, 4=clave, 5=imprescindible

contexts_raw = [
    # 1 — Atalanta vs Bayern Múnich
    # Neuer (GK) baja + Ito baja para Bayern; Atalanta: Ederson, De Ketelaere, Scalvini baja
    {
        "home_form": {"team": "Atalanta",      "results": ["W","W","D","W","W"]},
        "away_form": {"team": "Bayern Múnich", "results": ["W","W","W","L","W"]},
        "injuries": [
            {"name": "Ederson",           "team_role": "home", "importance": 3, "reason": "lesión"},
            {"name": "De Ketelaere",      "team_role": "home", "importance": 4, "reason": "rodilla"},
            {"name": "Giorgio Scalvini",  "team_role": "home", "importance": 3, "reason": "sanción"},
            {"name": "Manuel Neuer",      "team_role": "away", "importance": 4, "reason": "pantorrilla"},
            {"name": "Hiroki Ito",        "team_role": "away", "importance": 3, "reason": "muslo"},
        ],
    },
    # 2 — Atlético Madrid vs Tottenham
    # Tottenham: CRISIS (9 bajas). Atleti: solo Rodrigo Mendoza (nuevo fichaje)
    {
        "home_form": {"team": "Atlético",   "results": ["W","W","W","D","W"]},
        "away_form": {"team": "Tottenham",  "results": ["L","L","L","L","L"]},
        "injuries": [
            {"name": "Rodrigo Mendoza",    "team_role": "home", "importance": 2, "reason": "esguince tobillo"},
            {"name": "James Maddison",     "team_role": "away", "importance": 4, "reason": "rodilla (hasta verano)"},
            {"name": "Wilson Odobert",     "team_role": "away", "importance": 3, "reason": "LCA"},
            {"name": "Lucas Bergvall",     "team_role": "away", "importance": 3, "reason": "tobillo"},
            {"name": "Destiny Udogie",     "team_role": "away", "importance": 3, "reason": "isquiotibial"},
            {"name": "Dejan Kulusevski",   "team_role": "away", "importance": 3, "reason": "lesión"},
            {"name": "Rodrigo Bentancur",  "team_role": "away", "importance": 3, "reason": "lesión"},
            {"name": "Ben Davies",         "team_role": "away", "importance": 2, "reason": "lesión"},
            {"name": "Radu Dragusin",      "team_role": "away", "importance": 2, "reason": "lesión"},
            {"name": "Mohammed Kudus",     "team_role": "away", "importance": 3, "reason": "lesión"},
        ],
    },
    # 3 — Newcastle vs Barcelona
    # Barça: De Jong (5), Koundé (4), Balde (3), Christensen (3)
    # Newcastle: Bruno Guimarães (5), Schär (3), Miley (2), Krafth (2)
    {
        "home_form": {"team": "Newcastle",  "results": ["W","W","D","W","D"]},
        "away_form": {"team": "Barcelona",  "results": ["W","W","W","W","D"]},
        "injuries": [
            {"name": "Bruno Guimarães",   "team_role": "home", "importance": 5, "reason": "muslo"},
            {"name": "Fabian Schär",      "team_role": "home", "importance": 3, "reason": "tobillo"},
            {"name": "Lewis Miley",       "team_role": "home", "importance": 2, "reason": "muslo"},
            {"name": "Emil Krafth",       "team_role": "home", "importance": 2, "reason": "rodilla"},
            {"name": "Frenkie de Jong",   "team_role": "away", "importance": 5, "reason": "bíceps femoral"},
            {"name": "Jules Koundé",      "team_role": "away", "importance": 4, "reason": "bíceps femoral"},
            {"name": "Alejandro Balde",   "team_role": "away", "importance": 3, "reason": "bíceps femoral"},
            {"name": "Andreas Christensen","team_role":"away", "importance": 3, "reason": "lesión"},
        ],
    },
    # 4 — Bayer Leverkusen vs Arsenal
    # Leverkusen: Flekken (GK, 4), Badé (3), Vázquez (2), Ben Seghir (3)
    # Arsenal: Ødegaard (5), Merino (3), Ben White (3)
    {
        "home_form": {"team": "Leverkusen", "results": ["W","D","W","W","D"]},
        "away_form": {"team": "Arsenal",    "results": ["W","W","W","D","W"]},
        "injuries": [
            {"name": "Mark Flekken",       "team_role": "home", "importance": 4, "reason": "rodilla"},
            {"name": "Loïc Badé",          "team_role": "home", "importance": 3, "reason": "muslo"},
            {"name": "Eliesse Ben Seghir", "team_role": "home", "importance": 3, "reason": "tobillo"},
            {"name": "Lucas Vázquez",      "team_role": "home", "importance": 2, "reason": "gemelo"},
            {"name": "Martin Ødegaard",    "team_role": "away", "importance": 5, "reason": "lesión"},
            {"name": "Mikel Merino",       "team_role": "away", "importance": 3, "reason": "lesión"},
            {"name": "Ben White",          "team_role": "away", "importance": 3, "reason": "lesión"},
        ],
    },
    # 5 — Bodø/Glimt vs Sporting CP
    # Sporting: Pedro Gonçalves (5 - sanción), Maxi Araújo (3 - sanción), Quenda (4), Mangas (2)
    {
        "home_form": {"team": "Bodø/Glimt", "results": ["W","W","W","D","W"]},
        "away_form": {"team": "Sporting",   "results": ["W","D","W","W","L"]},
        "injuries": [
            {"name": "Pedro Gonçalves",    "team_role": "away", "importance": 5, "reason": "sanción"},
            {"name": "Maxi Araújo",        "team_role": "away", "importance": 3, "reason": "sanción"},
            {"name": "Geovany Quenda",     "team_role": "away", "importance": 4, "reason": "pie roto"},
            {"name": "Ricardo Mangas",     "team_role": "away", "importance": 2, "reason": "lesión"},
        ],
    },
    # 6 — PSG vs Chelsea
    # PSG: Fabian Ruiz (3), Ndjantou (2). Chelsea: Colwill (4), Estevao (3), Gittens (3)
    {
        "home_form": {"team": "PSG",     "results": ["W","W","L","W","W"]},
        "away_form": {"team": "Chelsea", "results": ["W","W","W","W","W"]},
        "injuries": [
            {"name": "Fabian Ruiz",    "team_role": "home", "importance": 3, "reason": "rodilla"},
            {"name": "Ndjantou",       "team_role": "home", "importance": 2, "reason": "isquio"},
            {"name": "Levi Colwill",   "team_role": "away", "importance": 4, "reason": "lesión"},
            {"name": "Estevao Willian","team_role": "away", "importance": 3, "reason": "lesión"},
            {"name": "Jamie Gittens",  "team_role": "away", "importance": 3, "reason": "lesión"},
        ],
    },
    # 7 — Stuttgart vs Oporto
    # Porto: De Jong (4), Aghehowa (4), Fernandes (2), Pérez (3)
    {
        "home_form": {"team": "Stuttgart", "results": ["W","D","W","W","D"]},
        "away_form": {"team": "Oporto",    "results": ["W","W","D","L","W"]},
        "injuries": [
            {"name": "Luuk de Jong",       "team_role": "away", "importance": 4, "reason": "lesión"},
            {"name": "Samu Aghehowa",      "team_role": "away", "importance": 4, "reason": "lesión"},
            {"name": "Nehuén Pérez",       "team_role": "away", "importance": 3, "reason": "lesión"},
            {"name": "Martim Fernandes",   "team_role": "away", "importance": 2, "reason": "lesión"},
        ],
    },
    # 8 — Panathinaikos vs Betis
    # Panathinaikos: 8 bajas (5 lesiones + 3 sanciones)
    # Betis: Isco (4), Lo Celso (3)
    {
        "home_form": {"team": "Panathinaikos", "results": ["W","D","L","W","D"]},
        "away_form": {"team": "Betis",         "results": ["W","W","D","W","L"]},
        "injuries": [
            {"name": "Cyriel Dessers",        "team_role": "home", "importance": 4, "reason": "lesión"},
            {"name": "G. Kyriopoulos",        "team_role": "home", "importance": 3, "reason": "lesión"},
            {"name": "Manolis Siopis",        "team_role": "home", "importance": 3, "reason": "lesión"},
            {"name": "E. Palmer-Brown",       "team_role": "home", "importance": 3, "reason": "lesión"},
            {"name": "G. Kotsiras",           "team_role": "home", "importance": 2, "reason": "lesión"},
            {"name": "Ahmed Touba",           "team_role": "home", "importance": 3, "reason": "sanción"},
            {"name": "Javi Hernández",        "team_role": "home", "importance": 2, "reason": "sanción"},
            {"name": "A. Bakasetas",          "team_role": "home", "importance": 4, "reason": "sanción"},
            {"name": "Isco",                  "team_role": "away", "importance": 4, "reason": "tobillo"},
            {"name": "Giovani Lo Celso",      "team_role": "away", "importance": 3, "reason": "muscular"},
        ],
    },
    # 9 — Bologna vs Roma
    # Roma: Dybala dudoso (5). Bologna: Miranda (2)
    {
        "home_form": {"team": "Bologna", "results": ["W","D","W","W","D"]},
        "away_form": {"team": "Roma",    "results": ["W","W","D","L","W"]},
        "injuries": [
            {"name": "Juan Miranda",    "team_role": "home", "importance": 2, "reason": "psoas"},
            {"name": "Paulo Dybala",    "team_role": "away", "importance": 5, "reason": "rodilla (dudoso)"},
        ],
    },
    # 10 — Lille vs Aston Villa
    # Villa: McGinn (4), Kamara (4), Elliott (3), Tielemans (3)
    {
        "home_form": {"team": "Lille",       "results": ["D","L","D","W","L"]},
        "away_form": {"team": "Aston Villa", "results": ["W","L","L","L","W"]},
        "injuries": [
            {"name": "John McGinn",         "team_role": "away", "importance": 4, "reason": "rodilla"},
            {"name": "Boubacar Kamara",     "team_role": "away", "importance": 4, "reason": "rodilla"},
            {"name": "Harvey Elliott",      "team_role": "away", "importance": 3, "reason": "lesión"},
            {"name": "Youri Tielemans",     "team_role": "away", "importance": 3, "reason": "lesión"},
        ],
    },
    # 11 — Celta vs Olympique Lyon
    # Lyon: Nuamah (4-LCA), Fofana (3), Kluivert (4), Maitland-Niles (3), Moreira (2), Sulc (2)
    {
        "home_form": {"team": "Celta", "results": ["W","D","W","D","W"]},
        "away_form": {"team": "Lyon",  "results": ["W","W","D","L","W"]},
        "injuries": [
            {"name": "Ernest Nuamah",        "team_role": "away", "importance": 4, "reason": "LCA"},
            {"name": "Ruben Kluivert",       "team_role": "away", "importance": 4, "reason": "muscular"},
            {"name": "Malick Fofana",        "team_role": "away", "importance": 3, "reason": "tobillo"},
            {"name": "A. Maitland-Niles",   "team_role": "away", "importance": 3, "reason": "aductor"},
            {"name": "Afonso Moreira",       "team_role": "away", "importance": 2, "reason": "isquio"},
            {"name": "Pavel Sulc",           "team_role": "away", "importance": 2, "reason": "isquio"},
        ],
    },
    # 12 — Ferencváros vs Braga  (sin bajas significativas)
    {
        "home_form": {"team": "Ferencváros", "results": ["W","D","W","W","W"]},
        "away_form": {"team": "Braga",       "results": ["W","W","W","D","W"]},
        "injuries": [],
    },
    # 13 — Racing Genk vs Friburgo
    # Friburgo: Eggestein (3-sanción), Kübler (2), Kyereh (3), Rosenfelder (2)
    {
        "home_form": {"team": "Genk",    "results": ["L","L","W","D","L"]},
        "away_form": {"team": "Friburgo","results": ["D","D","W","L","L"]},
        "injuries": [
            {"name": "Maximilian Eggestein", "team_role": "away", "importance": 3, "reason": "sanción"},
            {"name": "Lukas Kübler",         "team_role": "away", "importance": 2, "reason": "isquio"},
            {"name": "Daniel-Kofi Kyereh",   "team_role": "away", "importance": 3, "reason": "rodilla"},
            {"name": "Max Rosenfelder",      "team_role": "away", "importance": 2, "reason": "lesión"},
        ],
    },
    # 14 — Samsunspor vs Rayo Vallecano  (sin bajas relevantes)
    {
        "home_form": {"team": "Samsunspor",      "results": ["L","W","D","W","L"]},
        "away_form": {"team": "Rayo Vallecano",  "results": ["D","W","W","D","W"]},
        "injuries": [],
    },
    # 15 — Real Madrid vs Manchester City
    # Real Madrid: Mbappé (5), Bellingham (5), Rodrygo (4-LCA), Militão (4), Ceballos (3), Carreras (3)
    # Man City: Gvardiol (4), Kovacic (3)
    {
        "home_form": {"team": "Real Madrid",      "results": ["D","L","W","W","D"]},
        "away_form": {"team": "Manchester City",  "results": ["W","W","W","W","W"]},
        "injuries": [
            {"name": "Kylian Mbappé",       "team_role": "home", "importance": 5, "reason": "rodilla"},
            {"name": "Jude Bellingham",     "team_role": "home", "importance": 5, "reason": "semimembranoso"},
            {"name": "Rodrygo",             "team_role": "home", "importance": 4, "reason": "LCA + menisco"},
            {"name": "Éder Militão",        "team_role": "home", "importance": 4, "reason": "isquio"},
            {"name": "Dani Ceballos",       "team_role": "home", "importance": 3, "reason": "gemelo"},
            {"name": "Álvaro Carreras",     "team_role": "home", "importance": 3, "reason": "gemelo"},
            {"name": "Joško Gvardiol",      "team_role": "away", "importance": 4, "reason": "lesión"},
            {"name": "Mateo Kovacic",       "team_role": "away", "importance": 3, "reason": "lesión"},
        ],
    },
]

MATCH_NAMES = [
    "Atalanta vs Bayern Múnich",
    "Atlético Madrid vs Tottenham",
    "Newcastle vs Barcelona",
    "Bayer Leverkusen vs Arsenal",
    "Bodø/Glimt vs Sporting CP",
    "PSG vs Chelsea",
    "Stuttgart vs Oporto",
    "Panathinaikos vs Betis",
    "Bologna vs Roma",
    "Lille vs Aston Villa",
    "Celta vs Lyon",
    "Ferencváros vs Braga",
    "Racing Genk vs Friburgo",
    "Samsunspor vs Rayo Vallecano",
    "Real Madrid vs Manchester City",
]

COMPETITION = [
    "UCL","UCL","UCL","UCL","UCL","UCL",
    "UEL","UEL","UEL","UEL","UEL","UEL","UEL",
    "UECL",
    "UCL",
]

# ─────────────────────────────────────────────────────────────────────────────
# 3. CÁLCULO
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 70)
print("QUINIELA JORNADA 47 — Cálculo de probabilidades ajustadas")
print("Cuotas: Stake/SBGGlobal  |  Lesiones: prensa deportiva 10/03/2026")
print("=" * 70)

probs_list = []
adjustments = []

for i, (odds, ctx_raw) in enumerate(zip(raw_odds, contexts_raw)):
    base = odds_to_probabilities(*odds)
    ctx = context_from_dict(ctx_raw)
    if not ctx.is_empty:
        adj_probs, summary = adjust_probabilities(base, ctx)
    else:
        adj_probs = base
        summary = None
    probs_list.append(adj_probs)
    adjustments.append(summary)

# Determinar signos óptimos (signo con mayor P ajustada, con doble si hay empate técnico <5%)
def best_signs(prob: MatchProbabilities) -> list[str]:
    vals = {"1": prob.home, "X": prob.draw, "2": prob.away}
    sorted_signs = sorted(vals, key=lambda s: vals[s], reverse=True)
    best = sorted_signs[0]
    second = sorted_signs[1]
    # Doble si la diferencia entre 1º y 2º es < 0.06
    if vals[best] - vals[second] < 0.06:
        return [best, second]
    return [best]

print()
print(f"{'#':>2}  {'PARTIDO':<32} {'COMP':>4}  {'P(1)':>6} {'P(X)':>6} {'P(2)':>6}  {'SIGNO':>8}  {'CUOTAS'}")
print("-" * 90)

selections = []
for i, (prob, name, comp, odds) in enumerate(zip(probs_list, MATCH_NAMES, COMPETITION, raw_odds)):
    signs = best_signs(prob)
    selections.append(TicketSelection(signs))
    sign_str = "/".join(signs)
    # Indicar si hubo ajuste
    adj_flag = " *" if adjustments[i] else "  "
    print(f"{i+1:>2}{adj_flag} {name:<32} {comp:>4}  {prob.home:>6.3f} {prob.draw:>6.3f} {prob.away:>6.3f}  {sign_str:>8}  ({odds[0]:.2f}/{odds[1]:.2f}/{odds[2]:.2f})")

# ─────────────────────────────────────────────────────────────────────────────
# 4. ANÁLISIS DETALLADO DE AJUSTES
# ─────────────────────────────────────────────────────────────────────────────

print()
print("=" * 70)
print("DETALLE DE AJUSTES POR LESIONES/FORMA")
print("=" * 70)

for i, (adj, name) in enumerate(zip(adjustments, MATCH_NAMES)):
    if adj is None:
        continue
    base = odds_to_probabilities(*raw_odds[i])
    adj_probs = probs_list[i]
    d1 = adj_probs.home - base.home
    dx = adj_probs.draw - base.draw
    d2 = adj_probs.away - base.away
    print(f"\n  Partido {i+1}: {name}")
    print(f"    Original:  1={base.home:.4f}  X={base.draw:.4f}  2={base.away:.4f}")
    print(f"    Ajustado:  1={adj_probs.home:.4f}  X={adj_probs.draw:.4f}  2={adj_probs.away:.4f}")
    print(f"    Delta:     1={d1:+.4f}  X={dx:+.4f}  2={d2:+.4f}")

# ─────────────────────────────────────────────────────────────────────────────
# 5. INFORME FINAL DEL BOLETO
# ─────────────────────────────────────────────────────────────────────────────

ticket = QuinielaTicket(matches=selections)
calc = QuinielaCalculator(ticket, probs_list)
report = calc.full_report(
    prize_1st=1_500_000,
    prize_2nd=30_000,
    prize_3rd=1_000,
    base_cost=0.50,
)

print()
print("=" * 70)
print("RESUMEN DEL BOLETO")
print("=" * 70)
print(f"  Combinaciones totales : {report['ticket_combinations']}")
print(f"  Coste del boleto      : {report['ticket_cost_eur']:.2f} €")
print()
print(f"  P(15/15 — 1ª cat)     : {report['p_full_correct']:.6e}")
print(f"  P(14/15 — 2ª cat)     : {report['p_14_correct']:.6e}")
print(f"  P(13/15 — 3ª cat)     : {report['p_13_correct']:.6e}")
print(f"  P(algún premio ≥13)   : {report['p_any_prize']:.6e}")
print()
ev = report["expected_value"]
print(f"  Valor esperado (EV)   : {ev['ev_total']:.4f} €")
print(f"  EV por euro apostado  : {ev['ev_per_euro']:.4f}")
print(f"  ROI estimado          : {ev['roi_pct']:.2f}%")
print()
print("  Análisis por partido:")
print(f"  {'#':>2}  {'Partido':<32} {'Signos':>8}  {'P(acierto)':>10}")
print("  " + "-" * 60)
for m in report["match_analysis"]:
    name = MATCH_NAMES[m["match"]-1]
    signs_str = "/".join(m["signs_selected"])
    print(f"  {m['match']:>2}  {name:<32} {signs_str:>8}  {m['p_success']:>10.4f}")
