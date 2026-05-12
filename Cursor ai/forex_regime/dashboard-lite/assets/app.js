/**
 * Regime Engine — static dashboard (vanilla JS).
 * Regime IDs / quadrant map mirror forex_regime/regimes52/taxonomy.py (UI only).
 */
(function () {
  "use strict";

  /** Mirrors REGIME_NAME in taxonomy.py */
  const REGIME_NAMES = {
    1: "Bull Trend",
    2: "Bear Trend",
    3: "Weak Transitional Trend",
    4: "Momentum Regime",
    5: "Momentum Crash Regime",
    6: "Range Consolidation",
    7: "Mean Reversion Regime",
    8: "Premium and Discount Regime",
    9: "Low Volatility Squeeze",
    10: "Accumulation (Wyckoff)",
    11: "Markup (Wyckoff)",
    12: "Distribution (Wyckoff)",
    13: "Markdown (Wyckoff)",
    14: "Re-accumulation (Wyckoff)",
    15: "Re-distribution (Wyckoff)",
    16: "Rate Hiking Cycle",
    17: "Rate Cutting Cycle",
    18: "Quantitative Easing",
    19: "Quantitative Tightening",
    20: "Stagflation",
    21: "Deflationary Regime",
    22: "Reflation Regime",
    23: "Yield Curve Inversion",
    24: "Risk-On",
    25: "Risk-Off",
    26: "Fear Regime",
    27: "Greed Regime",
    28: "Liquidity Crunch",
    29: "Pre-FOMC Drift",
    30: "Post-News Continuation",
    31: "Post-News Reversal",
    32: "Geopolitical Risk Regime",
    33: "Options Expiry Regime",
    34: "End of Month Rebalancing",
    35: "Manipulation Phase (ICT)",
    36: "Expansion Phase (ICT)",
    37: "Asian Range Regime",
    38: "Kill Zone Regime",
    39: "Order Block Regime",
    40: "Imbalance / FVG Regime",
    41: "Order Imbalance Regime",
    42: "Absorption Regime",
    43: "Exhaustion Regime",
    44: "Stop Cascade Regime",
    45: "Hidden Markov / Latent State",
    46: "Volatility Clustering",
    47: "Carry Trade Regime",
    48: "Factor Rotation Regime",
    49: "Dollar Bull Regime",
    50: "Dollar Bear Regime",
    51: "COT Extreme Positioning Regime",
    52: "Intermarket Divergence Regime",
  };

  /** Mirrors quadrant_for_id: Q1_IDS…Q4_IDS plus 49→Q2, 50→Q1 */
  const QUADRANT_REGIMES = {
    Q1: [1, 2, 4, 11, 13, 17, 18, 22, 24, 36, 38, 47, 50],
    Q2: [3, 5, 16, 19, 20, 25, 30, 32, 44, 46, 49],
    Q3: [6, 7, 8, 9, 10, 12, 27, 29, 33, 34, 37, 39, 40],
    Q4: [14, 15, 21, 23, 26, 28, 31, 35, 41, 42, 43, 45, 48, 51, 52],
  };

  /** Build once: regime_id → Q1|Q2|Q3|Q4 */
  const REGIME_TO_QUAD = (() => {
    const m = {};
    Object.entries(QUADRANT_REGIMES).forEach(([q, ids]) => {
      ids.forEach((id) => {
        m[id] = q;
      });
    });
    return m;
  })();

  /**
   * Mirrors _BLUEPRINTS in regimes52/strategies/registry.py (title + signal_kind + side only for UI).
   */
  const BLUEPRINTS = {
    Q1: [
      { title: "TSMOM / vol-managed pullback", kind: "pullback_with_trend", side: 1, blurb: "Structural pullbacks in trend; ease size when variance spikes." },
      { title: "Channel / Donchian breakout", kind: "breakout_with_trend", side: 1, blurb: "Range expansion in trend direction." },
      { title: "Cross-sectional momentum add-on", kind: "continuation_bar", side: 1, blurb: "Add on strong continuation closes." },
      { title: "Low-vol trend drift (defensive gross-up)", kind: "trend_drift", side: 1, blurb: "Slow pyramid; avoid crowding same tails." },
    ],
    Q2: [
      { title: "Stress mean reversion (tail hedge tilt)", kind: "fade_extreme_rsi", side: -1, blurb: "Fade extremes when liquidity premia widen." },
      { title: "Wide-stop directional breakout", kind: "squeeze_breakout_dir", side: 0, blurb: "Compression then impulse; dir from rule." },
      { title: "Crash / momentum reversal scalp", kind: "impulse_reversal", side: -1, blurb: "Reversal after sharp impulsive leg." },
      { title: "Trend-with-vol overlay (short side bias ready)", kind: "breakout_with_trend", side: -1, blurb: "Trend only after vol confirms participation." },
    ],
    Q3: [
      { title: "Range fade (upper boundary)", kind: "fade_bb_high", side: -1, blurb: "Fade premium toward mid / equilibrium." },
      { title: "Range fade (lower boundary)", kind: "fade_bb_low", side: 1, blurb: "Buy discount in stationary range." },
      { title: "Z-score oscillation", kind: "zscore_fade", side: 1, blurb: "Fade vs local standardized mean." },
      { title: "Premium/discount equilibrium trade", kind: "range_equilibrium", side: 1, blurb: "Scale toward 50% dealing range." },
    ],
    Q4: [
      { title: "Liquidity sweep fade", kind: "wick_reversal", side: 1, blurb: "Fade engineered wicks / false breaks." },
      { title: "Vol-cluster straddle / flat gamma proxy fade", kind: "vol_spike_fade", side: -1, blurb: "Fade on vol spikes; MR bias." },
      { title: "Event reversal template", kind: "narrow_range_break_fake", side: 1, blurb: "Fade crowded post-event moves." },
      { title: "Regime-switch cautious drift", kind: "tiny_drift", side: 1, blurb: "Small drift until state stabilises." },
    ],
  };

  function sideLabel(side) {
    if (side === 1) return "side +1 (long arm)";
    if (side === -1) return "side −1 (short arm)";
    return "side 0 (dir from rule)";
  }

  /** Same shape as engine: four specs per regime, keys Rxx-S01…S04. */
  function strategiesForRegime(regimeId) {
    const q = REGIME_TO_QUAD[regimeId];
    const rn = REGIME_NAMES[regimeId] || `Regime ${regimeId}`;
    const rows = BLUEPRINTS[q] || BLUEPRINTS.Q4;
    return rows.map((bp, i) => {
      const slot = String(i + 1).padStart(2, "0");
      const rid = String(regimeId).padStart(2, "0");
      const key = `R${rid}-S${slot}`;
      return {
        id: key,
        name: `${bp.title} — ${rn}`,
        desc: `${bp.kind} · ${sideLabel(bp.side)} · ${bp.blurb}`,
        signalKind: bp.kind,
        side: bp.side,
      };
    });
  }

  const state = {
    quadrant: null,
    regimeId: null,
    strategyId: null,
    charts: {},
    /** @type {{ source: string, snapshot?: any, mock?: any }|null} */
    lastPack: null,
  };

  const PAGE = new URLSearchParams(location.search);
  const API_BASE = (PAGE.get("api") || "http://127.0.0.1:8766").replace(/\/$/, "");
  const API_SYMBOL = PAGE.get("symbol") || "EURUSD";
  const API_TF = parseInt(PAGE.get("tf") || "60", 10);
  const API_BARS = parseInt(PAGE.get("bars") || "12000", 10);

  function hashSeed(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
    return Math.abs(h);
  }

  function regimeRKey(quadrant, regimeId) {
    return (quadrant || "") + "#" + String(regimeId);
  }

  /** @param {number} regimeId */
  function mockAnalytics(quadrant, regimeId) {
    const s = hashSeed(regimeRKey(quadrant, regimeId));
    const r = (a, b) => a + ((s % 1000) / 1000) * (b - a);
    return {
      bullCount: Math.round(r(1200, 8900)),
      bearCount: Math.round(r(800, 5200)),
      sidewaysCount: Math.round(r(900, 6100)),
      confidencePct: Math.round(r(62, 94) * 10) / 10,
      winRatioPct: Math.round(r(48, 72) * 10) / 10,
      histFreqPerYr: Math.round(r(18, 48) * 10) / 10,
      avgDurationBars: Math.round(r(8, 95)),
      volScore: Math.round(r(22, 88) * 10) / 10,
    };
  }

  function mockBacktest(quadrant, strategyId, regimeId) {
    const s = hashSeed(regimeRKey(quadrant, regimeId) + "|" + (strategyId || ""));
    const r = (a, b) => a + ((s % 997) / 997) * (b - a);
    const initial = 100000;
    const roi = r(-8, 22);
    const final = Math.round(initial * (1 + roi / 100));
    return {
      initialCapital: initial,
      finalCapital: final,
      pnl: final - initial,
      roiPct: Math.round(roi * 100) / 100,
      winRatePct: Math.round(r(42, 68) * 10) / 10,
      totalTrades: Math.round(r(120, 980)),
      wins: Math.round(r(55, 420)),
      losses: Math.round(r(40, 390)),
      maxDrawdownPct: Math.round(r(4.5, 22) * 10) / 10,
      sharpe: Math.round(r(0.35, 2.1) * 100) / 100,
      riskReward: Math.round(r(0.7, 2.4) * 100) / 100,
    };
  }

  /**
   * @param {string} _quadrant
   * @param {number} regimeId
   * @returns {Promise<{ source: string, snapshot?: any, mock?: any }>}
   */
  async function fetchRegimeData(_quadrant, regimeId) {
    try {
      const u = new URL(`${API_BASE}/api/snapshot`);
      u.searchParams.set("symbol", API_SYMBOL);
      u.searchParams.set("tf_minutes", String(API_TF));
      u.searchParams.set("bars", String(API_BARS));
      u.searchParams.set("regime_id", String(regimeId));
      const res = await fetch(u.toString());
      const snap = await res.json();
      if (!res.ok || snap.error) {
        throw new Error(snap.error || snap.error_type || `HTTP ${res.status}`);
      }
      return { source: "mt5", snapshot: snap };
    } catch (e) {
      console.warn("[dashboard] MT5 API unavailable, using demo data:", e);
      return {
        source: "demo",
        mock: mockAnalytics(_quadrant, regimeId),
        error: String(e),
      };
    }
  }

  function $(sel) {
    return document.querySelector(sel);
  }

  function destroyCharts() {
    Object.values(state.charts).forEach((c) => {
      try {
        c.destroy();
      } catch (_) {}
    });
    state.charts = {};
  }

  function setStepHighlight(n) {
    document.querySelectorAll(".steps__item").forEach((el) => {
      el.classList.toggle("steps__item--active", el.dataset.step === String(n));
    });
  }

  function hideBelowRegime() {
    state.lastPack = null;
    ["stepAnalytics", "stepCharts", "stepStrategy", "stepBacktest", "stepPerformance"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.hidden = true;
    });
    $("#metricCards").innerHTML = "";
    destroyCharts();
    renderPerformanceEmpty();
    $("#monthlyTable").innerHTML = "";
    $("#strategyTabs").innerHTML = "";
    $("#strategyPanels").innerHTML = "";
    if ($("#strategyContext")) $("#strategyContext").textContent = "";
    $("#backtestMetrics").innerHTML = "";
  }

  function showSectionsInitial() {
    $("#stepRegimePick").hidden = true;
    hideBelowRegime();
    setStepHighlight(1);
  }

  function openSidebar(open) {
    const sb = $("#sidebar");
    const ov = $("#overlay");
    if (!sb) return;
    sb.classList.toggle("sidebar--open", open);
    if (ov) ov.hidden = !open;
  }

  function renderRegimeGrid(quadrant) {
    const grid = $("#regimeGrid");
    if (!grid) return;
    const ids = QUADRANT_REGIMES[quadrant] || [];
    grid.innerHTML = "";
    ids.forEach((rid) => {
      const name = REGIME_NAMES[rid] || `Regime ${rid}`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "regime-card";
      btn.dataset.regimeId = String(rid);
      btn.innerHTML =
        `<span class="regime-card__id">R${String(rid).padStart(2, "0")} · regime52_id</span>` +
        `<span class="regime-card__name">${name}</span>` +
        `<span class="regime-card__hint">${quadrant} · click for analytics</span>`;
      btn.addEventListener("click", () => onRegimePick(rid));
      grid.appendChild(btn);
    });
  }

  function onQuadrantPick(quadrant) {
    state.quadrant = quadrant;
    state.regimeId = null;
    state.strategyId = null;

    document.querySelectorAll(".quad-card").forEach((b) => {
      b.classList.toggle("quad-card--active", b.dataset.quadrant === quadrant);
    });

    $("#stepRegimePick").hidden = false;
    $("#regimePickSubtitle").textContent =
      `${quadrant}: ${QUADRANT_REGIMES[quadrant].length} regimes in this quadrant (taxonomy). Choose one.`;
    renderRegimeGrid(quadrant);
    document.querySelectorAll(".regime-card").forEach((c) => c.classList.remove("regime-card--active"));

    hideBelowRegime();
    setStepHighlight(2);

    $("#pageTitle").textContent = `Regime Engine — ${quadrant}`;
  }

  async function onRegimePick(regimeId) {
    const q = state.quadrant;
    if (!q) return;
    state.regimeId = regimeId;
    state.strategyId = null;

    document.querySelectorAll(".regime-card").forEach((c) => {
      c.classList.toggle("regime-card--active", Number(c.dataset.regimeId) === regimeId);
    });

    const nm = REGIME_NAMES[regimeId] || `ID ${regimeId}`;
    $("#pageTitle").textContent = `R${String(regimeId).padStart(2, "0")} · ${nm}`;

    ["stepAnalytics", "stepCharts", "stepStrategy", "stepBacktest", "stepPerformance"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.hidden = false;
    });

    $("#analyticsSubtitle").textContent = `${q} · Regime ${regimeId} (${nm}) — loading…`;
    setStepHighlight(3);

    const pack = await fetchRegimeData(q, regimeId);
    state.lastPack = pack;
    const pill = $("#livePill");

    if (pack.source === "mt5" && pack.snapshot && pack.snapshot.regime_detail) {
      const meta = pack.snapshot.meta;
      pill.textContent = `MT5 · ${meta.symbol} ${meta.tf_minutes}m · ${meta.bars_loaded} bars`;
      $("#analyticsSubtitle").textContent =
        `${q} · R${String(regimeId).padStart(2, "0")} ${nm} — scorecard from MT5 (MFE study, not dollar P&L).`;
      renderMetricsMt5(pack.snapshot);
      renderChartsMt5(pack.snapshot.regime_detail);
      renderStrategies(q, regimeId, nm, pack.snapshot.regime_detail);
      $("#backtestSubtitle").textContent =
        "Strategy panel uses MT5 scorecard rows (trades, wr_1r…wr_4r). Equity charts below are illustrative unless you add a full backtest P&L engine.";
    } else {
      pill.textContent = "Demo — run: python dashboard_api/server.py (port 8766)";
      $("#analyticsSubtitle").textContent =
        `${q} · R${String(regimeId).padStart(2, "0")} ${nm} — demo (API offline or error).`;
      renderMetricsDemo(pack.mock, q, regimeId, nm);
      renderChartsDemo(q, pack.mock, regimeId);
      renderStrategies(q, regimeId, nm, null);
      $("#backtestSubtitle").textContent = `Mock backtest for ${nm} — pick a strategy card.`;
    }

    setStepHighlight(4);
  }

  function renderMetricsMt5(snapshot) {
    const rd = snapshot.regime_detail;
    const meta = snapshot.meta;
    if (!rd || !meta) return;
    const strats = rd.strategies || [];
    const sumTrades = strats.reduce((a, s) => a + s.trades, 0);
    let best = strats[0];
    strats.forEach((s) => {
      if (s.rank_score > (best ? best.rank_score : -1)) best = s;
    });
    const cards = [
      ["Symbol · timeframe", `${meta.symbol} · ${meta.tf_minutes}m`],
      ["Bars loaded", String(meta.bars_loaded)],
      ["Bars this regime", String(rd.bars_in_regime)],
      ["% of sample", `${rd.pct_of_sample}%`],
      ["Quadrant", rd.quadrant],
      ["Total trades (4 specs)", String(sumTrades)],
      best
        ? ["Best rank_score", `${best.rank_score} (${best.strategy_key})`]
        : ["Best rank_score", "—"],
      best ? ["Best wr_2r (MFE)", String(best.wr_2r)] : ["Best wr_2r (MFE)", "—"],
    ];
    $("#metricCards").innerHTML = cards
      .map(
        ([label, val]) =>
          `<div class="metric-card"><div class="metric-card__label">${label}</div><div class="metric-card__value">${val}</div></div>`
      )
      .join("");
  }

  function renderMetricsDemo(d, quadrant, regimeId, regimeName) {
    const cards = [
      ["Bull occurrences", d.bullCount.toLocaleString()],
      ["Bear occurrences", d.bearCount.toLocaleString()],
      ["Sideways / range", d.sidewaysCount.toLocaleString()],
      ["Regime confidence", `${d.confidencePct}%`],
      ["Win ratio (mock)", `${d.winRatioPct}%`],
      ["Hist. frequency / yr", `${d.histFreqPerYr}`],
      ["Avg duration (bars)", `${d.avgDurationBars}`],
      ["Volatility score", `${d.volScore}`],
    ];
    $("#metricCards").innerHTML = cards
      .map(
        ([label, val]) =>
          `<div class="metric-card"><div class="metric-card__label">${label}</div><div class="metric-card__value">${val}</div></div>`
      )
      .join("");
  }

  function renderChartsMt5(rd) {
    destroyCharts();
    if (typeof Chart === "undefined") {
      console.warn("Chart.js not loaded");
      return;
    }
    const pie = rd.pie_three_way;
    const pieEl = document.getElementById("chartPie");
    if (pieEl && pie && pie.labels && pie.values) {
      state.charts.pie = new Chart(pieEl.getContext("2d"), {
        type: "doughnut",
        data: {
          labels: pie.labels,
          datasets: [
            {
              data: pie.values,
              backgroundColor: ["#3fb950", "#58a6ff", "#8b949e"],
              borderWidth: 0,
            },
          ],
        },
        options: { plugins: { legend: { labels: { color: "#8b949e" } } }, animation: { duration: 400 } },
      });
    }

    const lineEl = document.getElementById("chartLine");
    const ls = rd.line_series;
    if (lineEl && ls && ls.x && ls.y && ls.x.length) {
      state.charts.line = new Chart(lineEl.getContext("2d"), {
        type: "line",
        data: {
          labels: ls.x.map(String),
          datasets: [
            {
              label: ls.label || "% this regime",
              data: ls.y,
              borderColor: "#58a6ff",
              backgroundColor: "rgba(88,166,255,0.1)",
              fill: true,
              tension: 0.35,
            },
          ],
        },
        options: {
          scales: {
            x: { ticks: { color: "#8b949e", maxRotation: 0 }, grid: { color: "#30363d" } },
            y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          },
          plugins: { legend: { labels: { color: "#8b949e" } } },
        },
      });
    }

    const barEl = document.getElementById("chartBar");
    const mo = rd.monthly || [];
    const tail = mo.slice(-18);
    if (barEl && tail.length) {
      state.charts.bar = new Chart(barEl.getContext("2d"), {
        type: "bar",
        data: {
          labels: tail.map((m) => m.period),
          datasets: [
            {
              label: "Bars per month",
              data: tail.map((m) => m.count),
              backgroundColor: "rgba(63,185,80,0.55)",
              borderRadius: 4,
            },
          ],
        },
        options: {
          scales: {
            x: { ticks: { color: "#8b949e", maxRotation: 45 }, grid: { display: false } },
            y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          },
          plugins: { legend: { display: false } },
        },
      });
    }

    const hm = $("#heatmap");
    if (hm && tail.length) {
      hm.innerHTML = "";
      const maxC = Math.max(...tail.map((m) => m.count), 1);
      const cells = 12 * 6;
      for (let i = 0; i < cells; i++) {
        const mi = tail[Math.min(tail.length - 1, Math.floor((i / cells) * tail.length))];
        const inten = mi ? mi.count / maxC : 0;
        const cell = document.createElement("div");
        cell.className = "heatmap__cell";
        cell.style.background = `rgba(88, 166, 255, ${0.15 + inten * 0.85})`;
        cell.title = mi ? `${mi.period}: ${mi.count} bars` : "";
        hm.appendChild(cell);
      }
    }
  }

  function renderChartsDemo(quadrant, d, regimeId) {
    destroyCharts();
    if (typeof Chart === "undefined") {
      console.warn("Chart.js not loaded — check CDN or use local chart.umd.min.js");
      return;
    }

    const rk = regimeRKey(quadrant, regimeId);
    const bull = d.bullCount;
    const bear = d.bearCount;
    const side = d.sidewaysCount;
    const pieEl = document.getElementById("chartPie");
    if (pieEl) {
      state.charts.pie = new Chart(pieEl.getContext("2d"), {
        type: "doughnut",
        data: {
          labels: ["Bull", "Bear", "Sideways"],
          datasets: [
            {
              data: [bull, bear, side],
              backgroundColor: ["#3fb950", "#f85149", "#8b949e"],
              borderWidth: 0,
            },
          ],
        },
        options: { plugins: { legend: { labels: { color: "#8b949e" } } }, animation: { duration: 400 } },
      });
    }

    const lineEl = document.getElementById("chartLine");
    if (lineEl) {
      const labels = Array.from({ length: 24 }, (_, i) => `T${i + 1}`);
      const seed = hashSeed(rk + "line");
      const mix = labels.map((_, i) => 30 + ((seed >> (i % 8)) & 15) + (i % 7) * 2);
      state.charts.line = new Chart(lineEl.getContext("2d"), {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Regime stress index (mock)",
              data: mix,
              borderColor: "#58a6ff",
              backgroundColor: "rgba(88,166,255,0.1)",
              fill: true,
              tension: 0.35,
            },
          ],
        },
        options: {
          scales: {
            x: { ticks: { color: "#8b949e", maxRotation: 0 }, grid: { color: "#30363d" } },
            y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          },
          plugins: { legend: { labels: { color: "#8b949e" } } },
        },
      });
    }

    const barEl = document.getElementById("chartBar");
    if (barEl) {
      const months = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
      const seed = hashSeed(rk + "bar");
      const vals = months.map((_, i) => 40 + ((seed >> i) & 31));
      state.charts.bar = new Chart(barEl.getContext("2d"), {
        type: "bar",
        data: {
          labels: months,
          datasets: [{ label: "Monthly (mock)", data: vals, backgroundColor: "rgba(63,185,80,0.55)", borderRadius: 4 }],
        },
        options: {
          scales: {
            x: { ticks: { color: "#8b949e" }, grid: { display: false } },
            y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          },
          plugins: { legend: { display: false } },
        },
      });
    }

    const hm = $("#heatmap");
    if (hm) {
      hm.innerHTML = "";
      const seed = hashSeed(rk + "heat");
      for (let i = 0; i < 12 * 8; i++) {
        const cell = document.createElement("div");
        cell.className = "heatmap__cell";
        const inten = ((seed + i * 17) % 100) / 100;
        cell.style.background = `rgba(88, 166, 255, ${0.15 + inten * 0.85})`;
        cell.title = `Intensity ${(inten * 100).toFixed(0)}%`;
        hm.appendChild(cell);
      }
    }
  }

  function renderStrategies(quadrant, regimeId, regimeName, regimeDetail) {
    const base = strategiesForRegime(regimeId);
    const list = base.map((st) => {
      if (!regimeDetail || !regimeDetail.strategies) return st;
      const row = regimeDetail.strategies.find((s) => s.strategy_key === st.id);
      if (!row) return st;
      const extra = `MT5: trades ${row.trades} · wr₂ ${(row.wr_2r * 100).toFixed(1)}% · rank ${row.rank_score}`;
      return { ...st, desc: `${st.desc}\n${extra}` };
    });
    const tabs = $("#strategyTabs");
    const panels = $("#strategyPanels");
    const ctx = $("#strategyContext");
    if (ctx) {
      ctx.textContent =
        `${quadrant} · R${String(regimeId).padStart(2, "0")} ${regimeName} — four engine strategies (R${String(regimeId).padStart(2, "0")}-S01…S04, same blueprint set as all regimes in ${quadrant}).`;
    }
    tabs.innerHTML = "";
    panels.innerHTML = "";

    list.forEach((st, idx) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "tab" + (idx === 0 ? " tab--active" : "");
      tab.textContent = st.id;
      tab.title = st.name;
      tab.dataset.strategyId = st.id;
      tab.role = "tab";
      tab.addEventListener("click", () => {
        tabs.querySelectorAll(".tab").forEach((t) => t.classList.remove("tab--active"));
        tab.classList.add("tab--active");
        panels.querySelectorAll(".strategy-card").forEach((c) => {
          c.classList.toggle("strategy-card--selected", c.dataset.strategyId === st.id);
        });
        selectStrategy(st.id);
      });
      tabs.appendChild(tab);
    });

    list.forEach((st, idx) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "strategy-card" + (idx === 0 ? " strategy-card--selected" : "");
      card.dataset.strategyId = st.id;
      card.innerHTML =
        `<div class="strategy-card__key">${st.id}</div>` +
        `<div class="strategy-card__name">${st.name}</div>` +
        `<div class="strategy-card__desc">${st.desc}</div>`;
      card.addEventListener("click", () => {
        panels.querySelectorAll(".strategy-card").forEach((c) => c.classList.remove("strategy-card--selected"));
        card.classList.add("strategy-card--selected");
        tabs.querySelectorAll(".tab").forEach((t) => {
          t.classList.toggle("tab--active", t.dataset.strategyId === st.id);
        });
        selectStrategy(st.id);
      });
      panels.appendChild(card);
    });

    if (list.length) selectStrategy(list[0].id);
    setStepHighlight(5);
  }

  function selectStrategy(strategyId) {
    state.strategyId = strategyId;
    if (!state.quadrant || state.regimeId == null) return;
    const pack = state.lastPack;
    if (pack && pack.source === "mt5" && pack.snapshot && pack.snapshot.regime_detail) {
      const row = pack.snapshot.regime_detail.strategies.find((s) => s.strategy_key === strategyId);
      if (row) {
        renderBacktestScorecard(row);
        renderPerformanceMt5(row, pack.snapshot.regime_detail);
        setStepHighlight(7);
        return;
      }
    }
    const bt = mockBacktest(state.quadrant, strategyId, state.regimeId);
    renderBacktest(bt);
    renderPerformance(state.quadrant, strategyId, state.regimeId, bt);
    setStepHighlight(6);
  }

  function renderBacktestScorecard(row) {
    const rows = [
      ["Strategy key", row.strategy_key],
      ["signal_kind", row.signal_kind],
      ["side_rule", String(row.side_rule)],
      ["Trades (regime ∩ signal)", String(row.trades)],
      ["wr_1r (MFE)", String(row.wr_1r)],
      ["wr_2r (MFE)", String(row.wr_2r)],
      ["wr_3r (MFE)", String(row.wr_3r)],
      ["wr_4r (MFE)", String(row.wr_4r)],
      ["rank_score", String(row.rank_score)],
      ["score_wr_blend", String(row.score_wr_blend)],
      ["Note", "MFE before ATR stop — not $ P&L"],
    ];
    $("#backtestMetrics").innerHTML = rows
      .map(
        ([k, v]) =>
          `<div class="bt-metric"><div class="bt-metric__v">${v}</div><div class="bt-metric__k">${k}</div></div>`
      )
      .join("");
    setStepHighlight(7);
  }

  function renderPerformanceMt5(row, rd) {
    if (typeof Chart === "undefined") return;
    renderPerformanceEmpty();

    const eq = document.getElementById("chartEquity");
    if (eq) {
      state.charts.chartEquity = new Chart(eq.getContext("2d"), {
        type: "bar",
        data: {
          labels: ["wr_1r", "wr_2r", "wr_3r", "wr_4r"],
          datasets: [
            {
              label: "MFE win rate",
              data: [row.wr_1r, row.wr_2r, row.wr_3r, row.wr_4r],
              backgroundColor: "rgba(88,166,255,0.55)",
              borderRadius: 4,
            },
          ],
        },
        options: {
          plugins: {
            legend: { display: false },
            title: { display: true, text: "MT5 scorecard — selected strategy", color: "#8b949e", font: { size: 12 } },
          },
          scales: {
            y: { max: 1, min: 0, ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
            x: { ticks: { color: "#8b949e" } },
          },
        },
      });
    }

    const tr = document.getElementById("chartTrades");
    if (tr) {
      const v = [row.wr_1r, row.wr_2r, row.wr_3r, row.wr_4r];
      state.charts.chartTrades = new Chart(tr.getContext("2d"), {
        type: "radar",
        data: {
          labels: ["1R", "2R", "3R", "4R"],
          datasets: [
            {
              label: "MFE hit rate",
              data: v,
              backgroundColor: "rgba(63,185,80,0.25)",
              borderColor: "#3fb950",
              borderWidth: 1,
            },
          ],
        },
        options: {
          scales: {
            r: { min: 0, max: 1, ticks: { color: "#8b949e", showLabelBackdrop: false }, grid: { color: "#30363d" } },
          },
          plugins: { legend: { labels: { color: "#8b949e" } } },
        },
      });
    }

    const hi = document.getElementById("chartHist");
    if (hi) {
      state.charts.chartHist = new Chart(hi.getContext("2d"), {
        type: "bar",
        data: {
          labels: ["blend", "rank×0.5"],
          datasets: [
            {
              label: "scaled",
              data: [row.score_wr_blend, row.rank_score * 0.5],
              backgroundColor: "rgba(210,153,34,0.6)",
            },
          ],
        },
        options: {
          scales: {
            x: { ticks: { color: "#8b949e" } },
            y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          },
          plugins: { legend: { display: false } },
        },
      });
    }

    const mo = (rd && rd.monthly) || [];
    const tail = mo.slice(-12);
    $("#monthlyTable").innerHTML =
      `<thead><tr><th>Month</th><th>Bars (this regime)</th></tr></thead><tbody>` +
      (tail.length
        ? tail.map((m) => `<tr><td>${m.period}</td><td>${m.count}</td></tr>`).join("")
        : `<tr><td colspan="2">No monthly breakdown</td></tr>`) +
      `</tbody>`;
  }

  function renderBacktest(bt) {
    const rows = [
      ["Initial capital", `$${bt.initialCapital.toLocaleString()}`],
      ["Final capital", `$${bt.finalCapital.toLocaleString()}`],
      ["Total P/L", `$${bt.pnl.toLocaleString()}`],
      ["ROI", `${bt.roiPct}%`],
      ["Win rate", `${bt.winRatePct}%`],
      ["Total trades", String(bt.totalTrades)],
      ["Winning trades", String(bt.wins)],
      ["Losing trades", String(bt.losses)],
      ["Max drawdown", `${bt.maxDrawdownPct}%`],
      ["Sharpe (mock)", String(bt.sharpe)],
      ["Risk/reward", String(bt.riskReward)],
    ];
    $("#backtestMetrics").innerHTML = rows
      .map(
        ([k, v]) =>
          `<div class="bt-metric"><div class="bt-metric__v">${v}</div><div class="bt-metric__k">${k}</div></div>`
      )
      .join("");
  }

  function renderPerformanceEmpty() {
    ["chartEquity", "chartTrades", "chartHist"].forEach((k) => {
      const c = state.charts[k];
      if (c) {
        try {
          c.destroy();
        } catch (_) {}
        delete state.charts[k];
      }
    });
  }

  function renderPerformance(quadrant, strategyId, regimeId, bt) {
    if (typeof Chart === "undefined") return;
    renderPerformanceEmpty();

    const rk = regimeRKey(quadrant, regimeId);
    const eq = document.getElementById("chartEquity");
    if (eq) {
      const n = 60;
      const seed = hashSeed(rk + strategyId + "eq");
      let v = 100;
      const data = [v];
      for (let i = 0; i < n; i++) {
        v += (((seed >> (i % 16)) & 7) - 3) * 0.35 + (bt.roiPct / n) * 0.15;
        data.push(Math.max(85, v));
      }
      state.charts.chartEquity = new Chart(eq.getContext("2d"), {
        type: "line",
        data: {
          labels: data.map((_, i) => i),
          datasets: [
            { label: "Equity index (mock)", data, borderColor: "#3fb950", backgroundColor: "rgba(63,185,80,0.08)", fill: true },
          ],
        },
        options: {
          scales: {
            x: { display: false },
            y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          },
          plugins: { legend: { labels: { color: "#8b949e" } } },
        },
      });
    }

    const tr = document.getElementById("chartTrades");
    if (tr) {
      state.charts.chartTrades = new Chart(tr.getContext("2d"), {
        type: "polarArea",
        data: {
          labels: ["Win", "Loss", "BE"],
          datasets: [
            {
              data: [bt.wins, bt.losses, Math.max(0, bt.totalTrades - bt.wins - bt.losses)],
              backgroundColor: ["rgba(63,185,80,0.6)", "rgba(248,81,73,0.6)", "rgba(139,148,158,0.5)"],
            },
          ],
        },
        options: { plugins: { legend: { position: "bottom", labels: { color: "#8b949e" } } } },
      });
    }

    const hi = document.getElementById("chartHist");
    if (hi) {
      const bins = ["<-2R", "-2:-1R", "-1:0", "0:1R", "1:2R", ">2R"];
      const seed = hashSeed(rk + strategyId + "hist");
      const vals = bins.map((_, i) => 5 + ((seed >> i) & 25));
      state.charts.chartHist = new Chart(hi.getContext("2d"), {
        type: "bar",
        data: {
          labels: bins,
          datasets: [{ label: "# trades", data: vals, backgroundColor: "rgba(210,153,34,0.6)" }],
        },
        options: {
          scales: {
            x: { ticks: { color: "#8b949e" } },
            y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          },
          plugins: { legend: { display: false } },
        },
      });
    }

    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"];
    const seed = hashSeed(rk + strategyId + "mon");
    const rets = months.map((_, i) => ((((seed >> i) & 7) - 3) * 0.4).toFixed(2));
    $("#monthlyTable").innerHTML =
      `<thead><tr><th>Month</th><th>Return %</th></tr></thead><tbody>` +
      months.map((m, i) => `<tr><td>${m}</td><td>${rets[i]}%</td></tr>`).join("") +
      `</tbody>`;
  }

  function init() {
    showSectionsInitial();
    $("#menuToggle")?.addEventListener("click", () => openSidebar(true));
    $("#sidebarClose")?.addEventListener("click", () => openSidebar(false));
    $("#overlay")?.addEventListener("click", () => openSidebar(false));

    document.querySelectorAll(".quad-card").forEach((btn) => {
      btn.addEventListener("click", () => onQuadrantPick(btn.dataset.quadrant));
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
