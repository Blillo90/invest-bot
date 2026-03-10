"use client";

/**
 * QuinielaCalculator
 * ------------------
 * Componente React para calcular la probabilidad de acertar una quiniela.
 *
 * Lógica matemática principal (en el cliente, sin llamada al API):
 *
 *   P(acierto partido i) = Σ p_{i,j}  para j ∈ signos_seleccionados_i
 *
 *   P(pleno 15/15)       = Π P(acierto_i)
 *
 *   Distribución exacta  → Poisson Binomial via DP (O(n²))
 *
 * Las probabilidades se derivan de las cuotas del bookmaker eliminando
 * el margen (overround) mediante normalización.
 */

import { useState, useCallback } from "react";

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

type Sign = "1" | "X" | "2";

interface MatchInput {
  homeOdds: string;
  drawOdds: string;
  awayOdds: string;
  signs: Sign[];
}

interface MatchResult {
  matchIndex: number;
  pHome: number;
  pDraw: number;
  pAway: number;
  pSuccess: number;
  signs: Sign[];
  multiplier: number;
  margin: number;
}

interface CalculationResult {
  combinations: number;
  ticketCost: number;
  pFull: number;
  p14: number;
  p13: number;
  pAnyPrize: number;
  distribution: number[];
  matches: MatchResult[];
  ev: number;
  roi: number;
}

// ---------------------------------------------------------------------------
// Matemáticas del lado cliente
// ---------------------------------------------------------------------------

function oddsToProbs(
  home: number,
  draw: number,
  away: number
): [number, number, number] {
  const rawH = 1 / home;
  const rawD = 1 / draw;
  const rawA = 1 / away;
  const total = rawH + rawD + rawA;
  return [rawH / total, rawD / total, rawA / total];
}

function margin(home: number, draw: number, away: number): number {
  return ((1 / home + 1 / draw + 1 / away - 1) * 100);
}

/** Distribución de Poisson Binomial mediante DP. */
function poissonBinomialDP(ps: number[]): number[] {
  const n = ps.length;
  const dp = new Array(n + 1).fill(0);
  dp[0] = 1;
  for (const p of ps) {
    for (let k = n; k >= 1; k--) {
      dp[k] = dp[k] * (1 - p) + dp[k - 1] * p;
    }
    dp[0] *= 1 - p;
  }
  return dp;
}

// ---------------------------------------------------------------------------
// Estado inicial: 15 partidos vacíos
// ---------------------------------------------------------------------------

const DEFAULT_MATCH: MatchInput = {
  homeOdds: "2.00",
  drawOdds: "3.30",
  awayOdds: "3.80",
  signs: ["1"],
};

function makeDefaultMatches(): MatchInput[] {
  return Array.from({ length: 15 }, () => ({ ...DEFAULT_MATCH, signs: ["1"] as Sign[] }));
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function QuinielaCalculator() {
  const [matches, setMatches] = useState<MatchInput[]>(makeDefaultMatches);
  const [prizes, setPrizes] = useState({ first: 1500000, second: 30000, third: 1000 });
  const [baseCost, setBaseCost] = useState(0.5);
  const [result, setResult] = useState<CalculationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // --- Actualizar cuota de un partido ---
  const updateOdds = useCallback(
    (idx: number, field: "homeOdds" | "drawOdds" | "awayOdds", value: string) => {
      setMatches((prev) => {
        const next = [...prev];
        next[idx] = { ...next[idx], [field]: value };
        return next;
      });
    },
    []
  );

  // --- Alternar signo seleccionado ---
  const toggleSign = useCallback((idx: number, sign: Sign) => {
    setMatches((prev) => {
      const next = [...prev];
      const current = next[idx].signs;
      const has = current.includes(sign);
      let updated: Sign[];
      if (has) {
        updated = current.filter((s) => s !== sign);
        if (updated.length === 0) return prev; // mínimo 1 signo
      } else {
        updated = [...current, sign];
      }
      next[idx] = { ...next[idx], signs: updated };
      return next;
    });
  }, []);

  // --- Cálculo ---
  const calculate = useCallback(() => {
    setError(null);
    try {
      const matchResults: MatchResult[] = [];
      const pSuccessArr: number[] = [];

      for (let i = 0; i < 15; i++) {
        const m = matches[i];
        const h = parseFloat(m.homeOdds);
        const d = parseFloat(m.drawOdds);
        const a = parseFloat(m.awayOdds);

        if (isNaN(h) || isNaN(d) || isNaN(a) || h <= 1 || d <= 1 || a <= 1) {
          throw new Error(`Cuotas inválidas en partido ${i + 1}. Deben ser > 1.`);
        }
        if (m.signs.length === 0) {
          throw new Error(`Partido ${i + 1}: selecciona al menos un signo.`);
        }

        const [pH, pD, pA] = oddsToProbs(h, d, a);
        const pMap: Record<Sign, number> = { "1": pH, X: pD, "2": pA };
        const pSuccess = m.signs.reduce((acc, s) => acc + pMap[s], 0);
        pSuccessArr.push(pSuccess);

        matchResults.push({
          matchIndex: i + 1,
          pHome: pH,
          pDraw: pD,
          pAway: pA,
          pSuccess,
          signs: m.signs,
          multiplier: m.signs.length,
          margin: margin(h, d, a),
        });
      }

      const combinations = matchResults.reduce((acc, mr) => acc * mr.multiplier, 1);
      const ticketCost = baseCost * combinations;

      const pFull = pSuccessArr.reduce((acc, p) => acc * p, 1);
      const dist = poissonBinomialDP(pSuccessArr);

      const ev =
        dist[15] * prizes.first +
        dist[14] * prizes.second +
        dist[13] * prizes.third;
      const roi = ((ev - ticketCost) / ticketCost) * 100;

      setResult({
        combinations,
        ticketCost,
        pFull,
        p14: dist[14],
        p13: dist[13],
        pAnyPrize: dist[15] + dist[14] + dist[13],
        distribution: dist,
        matches: matchResults,
        ev,
        roi,
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [matches, prizes, baseCost]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="max-w-5xl mx-auto p-4 space-y-6 font-mono text-sm">
      <h1 className="text-xl font-bold text-white">Calculadora de Probabilidad — Quiniela</h1>

      {/* Premios y coste */}
      <section className="bg-gray-800 rounded-lg p-4 space-y-3">
        <h2 className="text-gray-300 font-semibold">Premios y coste del boleto</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {(
            [
              { label: "1ª cat. (15/15) €", key: "first" },
              { label: "2ª cat. (14/15) €", key: "second" },
              { label: "3ª cat. (13/15) €", key: "third" },
            ] as const
          ).map(({ label, key }) => (
            <div key={key}>
              <label className="text-gray-400 text-xs">{label}</label>
              <input
                type="number"
                className="w-full bg-gray-700 text-white rounded px-2 py-1 mt-1"
                value={prizes[key]}
                onChange={(e) =>
                  setPrizes((p) => ({ ...p, [key]: parseFloat(e.target.value) || 0 }))
                }
              />
            </div>
          ))}
          <div>
            <label className="text-gray-400 text-xs">Coste/combinación €</label>
            <input
              type="number"
              className="w-full bg-gray-700 text-white rounded px-2 py-1 mt-1"
              value={baseCost}
              step="0.10"
              onChange={(e) => setBaseCost(parseFloat(e.target.value) || 0.5)}
            />
          </div>
        </div>
      </section>

      {/* Tabla de 15 partidos */}
      <section className="bg-gray-800 rounded-lg p-4">
        <h2 className="text-gray-300 font-semibold mb-3">Partidos (cuotas decimales)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-gray-300">
            <thead>
              <tr className="text-gray-500 border-b border-gray-700">
                <th className="text-left py-1 pr-2">#</th>
                <th className="py-1 px-2">Cuota 1</th>
                <th className="py-1 px-2">Cuota X</th>
                <th className="py-1 px-2">Cuota 2</th>
                <th className="py-1 px-2">Signo(s)</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((m, i) => (
                <tr key={i} className="border-b border-gray-700/50">
                  <td className="py-1 pr-2 text-gray-500">{i + 1}</td>
                  {(
                    ["homeOdds", "drawOdds", "awayOdds"] as const
                  ).map((field) => (
                    <td key={field} className="py-1 px-2">
                      <input
                        type="number"
                        step="0.05"
                        min="1.01"
                        className="w-16 bg-gray-700 text-white rounded px-1 py-0.5 text-center"
                        value={m[field]}
                        onChange={(e) => updateOdds(i, field, e.target.value)}
                      />
                    </td>
                  ))}
                  <td className="py-1 px-2">
                    <div className="flex gap-1">
                      {(["1", "X", "2"] as Sign[]).map((sign) => (
                        <button
                          key={sign}
                          onClick={() => toggleSign(i, sign)}
                          className={`px-2 py-0.5 rounded font-bold transition-colors ${
                            m.signs.includes(sign)
                              ? "bg-blue-600 text-white"
                              : "bg-gray-600 text-gray-400 hover:bg-gray-500"
                          }`}
                        >
                          {sign}
                        </button>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Botón calcular */}
      <button
        onClick={calculate}
        className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 rounded-lg transition-colors"
      >
        Calcular probabilidades
      </button>

      {error && (
        <div className="bg-red-900/50 border border-red-500 text-red-300 rounded p-3">
          {error}
        </div>
      )}

      {/* Resultados */}
      {result && (
        <section className="space-y-4">
          {/* KPIs principales */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              {
                label: "Combinaciones",
                value: result.combinations.toLocaleString(),
                sub: `${result.ticketCost.toFixed(2)} €`,
                color: "text-yellow-400",
              },
              {
                label: "P(15/15)",
                value: result.pFull < 1e-10
                  ? result.pFull.toExponential(2)
                  : `${(result.pFull * 100).toFixed(6)}%`,
                sub: `1 de cada ${Math.round(1 / result.pFull).toLocaleString()}`,
                color: "text-green-400",
              },
              {
                label: "P(≥13/15)",
                value: result.pAnyPrize < 1e-6
                  ? result.pAnyPrize.toExponential(2)
                  : `${(result.pAnyPrize * 100).toFixed(4)}%`,
                sub: "algún premio",
                color: "text-blue-400",
              },
              {
                label: "Valor Esperado",
                value: `${result.ev.toFixed(3)} €`,
                sub: `ROI: ${result.roi.toFixed(2)}%`,
                color: result.roi >= 0 ? "text-green-400" : "text-red-400",
              },
            ].map(({ label, value, sub, color }) => (
              <div key={label} className="bg-gray-800 rounded-lg p-3">
                <div className="text-gray-400 text-xs mb-1">{label}</div>
                <div className={`text-lg font-bold ${color}`}>{value}</div>
                <div className="text-gray-500 text-xs">{sub}</div>
              </div>
            ))}
          </div>

          {/* Distribución de aciertos */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-gray-300 font-semibold mb-3">
              Distribución de probabilidad de aciertos
            </h3>
            <div className="space-y-1">
              {result.distribution
                .map((p, k) => ({ k, p }))
                .reverse()
                .filter(({ k }) => k >= 8)
                .map(({ k, p }) => {
                  const pct = p * 100;
                  const barWidth = Math.max(pct * 500, 0.5);
                  const isPrize = k >= 13;
                  return (
                    <div key={k} className="flex items-center gap-2">
                      <span
                        className={`w-12 text-right text-xs ${
                          isPrize ? "text-yellow-400 font-bold" : "text-gray-400"
                        }`}
                      >
                        {k}/15
                      </span>
                      <div className="flex-1 bg-gray-700 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${
                            isPrize ? "bg-yellow-500" : "bg-blue-600"
                          }`}
                          style={{ width: `${Math.min(barWidth, 100)}%` }}
                        />
                      </div>
                      <span className="w-24 text-xs text-gray-400">
                        {pct < 0.0001
                          ? pct.toExponential(2)
                          : pct.toFixed(4)}
                        %
                      </span>
                    </div>
                  );
                })}
            </div>
          </div>

          {/* Análisis por partido */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-gray-300 font-semibold mb-3">Análisis por partido</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-gray-300">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-700">
                    <th className="text-left py-1 pr-2">#</th>
                    <th className="py-1 px-2">P(1)</th>
                    <th className="py-1 px-2">P(X)</th>
                    <th className="py-1 px-2">P(2)</th>
                    <th className="py-1 px-2">Signos</th>
                    <th className="py-1 px-2">P(acierto)</th>
                    <th className="py-1 px-2">Margen bookie</th>
                  </tr>
                </thead>
                <tbody>
                  {result.matches.map((mr) => (
                    <tr key={mr.matchIndex} className="border-b border-gray-700/50">
                      <td className="py-1 pr-2 text-gray-500">{mr.matchIndex}</td>
                      <td className="py-1 px-2 text-center">{(mr.pHome * 100).toFixed(1)}%</td>
                      <td className="py-1 px-2 text-center">{(mr.pDraw * 100).toFixed(1)}%</td>
                      <td className="py-1 px-2 text-center">{(mr.pAway * 100).toFixed(1)}%</td>
                      <td className="py-1 px-2 text-center text-blue-400 font-bold">
                        {mr.signs.join("")}
                      </td>
                      <td
                        className={`py-1 px-2 text-center font-bold ${
                          mr.pSuccess >= 0.5 ? "text-green-400" : "text-orange-400"
                        }`}
                      >
                        {(mr.pSuccess * 100).toFixed(1)}%
                      </td>
                      <td className="py-1 px-2 text-center text-gray-500">
                        {mr.margin.toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
