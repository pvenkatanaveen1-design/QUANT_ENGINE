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

  /** Timeframe catalog for Research panel (minutes, UI label, default bars). Edit this array to change the grid — no other literals. */
  const RESEARCH_TF_CATALOG = [
    { tf_minutes: 1, label: "1m", defaultBars: 30000 },
    { tf_minutes: 2, label: "2m", defaultBars: 25000 },
    { tf_minutes: 5, label: "5m", defaultBars: 20000 },
    { tf_minutes: 10, label: "10m", defaultBars: 15000 },
    { tf_minutes: 15, label: "15m", defaultBars: 12000 },
    { tf_minutes: 30, label: "30m", defaultBars: 10000 },
    { tf_minutes: 60, label: "1H", defaultBars: 8000 },
    { tf_minutes: 120, label: "2H", defaultBars: 6000 },
    { tf_minutes: 180, label: "3H", defaultBars: 5000 },
    { tf_minutes: 240, label: "4H", defaultBars: 4000 },
  ];

  /** @type {{ strategy_key: string, strategy_title: string, signal_kind: string, side_rule: number, trades: number, wr_1r: number, wr_2r: number, wr_3r: number, wr_4r: number, rank_score: number, score_wr_blend: number, risk_pct: string, rr_ratio: string, atr_multiplier: string, position_size: string, enabled: boolean, _source?: string }[]} */
  let researchStrategiesDraft = [];

  let researchPreviewScheduled = false;
  let researchSymbolSync = false;
  let researchStrategiesRefreshTimer = null;

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
    /** Chart.js instances for Practical regime view only */
    practicalCharts: {},
    /** @type {{ source: string, snapshot?: any, error?: string }|null} */
    lastPack: null,
  };

  /** sessionStorage key for Δ panel between consecutive successful snapshot responses */
  const PRACTICAL_PREV_SNAPSHOT_KEY = "practicalSnapshotPrevJsonV1";

  /** @type {ReturnType<typeof setInterval>|null} */
  let livePollTimer = null;
  /** @type {ReturnType<typeof setInterval>|null} */
  let liveStripTimer = null;
  /** @type {ReturnType<typeof setInterval>|null} */
  let practicalPollTimer = null;
  let practicalPollInFlight = false;

  const PAGE = new URLSearchParams(location.search);
  const API_BASE = (PAGE.get("api") || "http://127.0.0.1:8766").replace(/\/$/, "");
  let API_SYMBOL = (PAGE.get("symbol") || "EURUSD").trim().toUpperCase() || "EURUSD";
  const API_TF = parseInt(PAGE.get("tf") || "60", 10);
  const API_BARS = parseInt(PAGE.get("bars") || "12000", 10);
  const API_ATR_SL = (() => {
    const v = parseFloat(PAGE.get("atr_sl_mult") || "1.5");
    return Number.isFinite(v) ? v : 1.5;
  })();
  const API_MAX_BARS_RR = (() => {
    const v = parseInt(PAGE.get("max_bars") || "40", 10);
    return Number.isFinite(v) && v > 0 ? v : 40;
  })();
  const API_REGIME_URL = parseInt(PAGE.get("regime_id") || "0", 10);

  function getActiveSymbol() {
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("symbolSelect"));
    const cust = /** @type {HTMLInputElement|null} */ (document.getElementById("symbolCustom"));
    if (sel && sel.value === "__custom__" && cust) {
      const raw = (cust.value || "").trim().toUpperCase();
      return raw || API_SYMBOL;
    }
    if (sel && sel.value && sel.value !== "__custom__") return sel.value;
    return API_SYMBOL;
  }

  function stopLivePoll() {
    if (livePollTimer) {
      clearInterval(livePollTimer);
      livePollTimer = null;
    }
  }

  /** @param {string|undefined|null} lastUpdateIso */
  function liveDataFreshness(lastUpdateIso) {
    if (!lastUpdateIso) return " 🔴";
    const t = Date.parse(String(lastUpdateIso));
    if (Number.isNaN(t)) return " 🔴";
    const ageSec = (Date.now() - t) / 1000;
    return ageSec < 30 ? " 🟢" : " 🔴";
  }

  function formatLiveScalar(v) {
    if (v === null || v === undefined) return "—";
    return String(v);
  }

  /** @param {any} snapshot */
  function updateLivePill(snapshot) {
    const pill = $("#livePill");
    if (!pill || !snapshot || !snapshot.meta) return;
    const meta = snapshot.meta;
    const fresh = liveDataFreshness(snapshot.last_update);
    const price = formatLiveScalar(snapshot.last_price);
    const sp = formatLiveScalar(snapshot.spread);
    const lq = formatLiveScalar(snapshot.quadrant);
    pill.textContent = `MT5 · ${meta.symbol} · px ${price} · spr ${sp} · live ${lq}${fresh}`;
  }

  async function fetchLiveStrip(symbol) {
    try {
      const sym = symbol != null && String(symbol).trim() !== "" ? String(symbol).trim() : getActiveSymbol();
      const url = `${API_BASE}/api/snapshot?symbol=${encodeURIComponent(sym)}&tf_minutes=60&bars=5`;
      const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const snap = await res.json();
      if (snap.error) throw new Error(snap.error || snap.error_type || "snapshot error");
      updateLiveStrip(snap);
    } catch (e) {
      console.warn("[live-strip] failed:", e);
      updateLiveStrip(null);
    }
  }

  function updateLiveStrip(snap) {
    if (!snap || !snap.mt5_connected) {
      const pill = document.getElementById("livePill");
      if (pill) pill.textContent = "MT5 disconnected 🔴";
      return;
    }
    updateLivePill(snap);
    liveDataFreshness(snap.last_update);
  }

  function escHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
  }

  function fmtSignalLine(sig) {
    if (!sig) return "—";
    return `${sig.direction} ${sig.strategy} @ ${sig.entry_price} · SL ${sig.stop_loss} · TP ${sig.take_profit} · R:R ${sig.rr_ratio}`;
  }

  /** Live signal, selector, risk — Step 6 */
  function renderSignalExecute(snapshot) {
    const panel = $("#signalExecutePanel");
    const btn = $("#btnExecute");
    const st = $("#executeStatus");
    if (!panel) return;
    if (!snapshot || !snapshot.meta) {
      panel.innerHTML = "";
      if (btn) btn.disabled = true;
      if (st) st.textContent = "";
      return;
    }
    if (!snapshot.mt5_connected) {
      panel.innerHTML = `<div class="metric-card metric-card--wide"><div class="metric-card__label">MT5</div><div class="metric-card__value">Offline — start terminal and <code>dashboard_api/server.py</code>.</div></div>`;
      if (btn) btn.disabled = true;
      if (st) st.textContent = "";
      return;
    }

    const sess = snapshot.session || "—";
    const sel = snapshot.strategy_selection || {};
    const stratLines = (snapshot.strategy_scores || [])
      .slice(0, 6)
      .map((r) => `${r.name}: ${r.score}`)
      .join(" · ");
    const sig = snapshot.current_signal;
    const chk = snapshot.signal_checks || {};
    const risk = snapshot.risk_gate || {};
    const lot = snapshot.lot_size;

    const stratUi = (sel.strategies || []).map((x) => `${x.name}=${x.status}`).join(", ");

    const chkRows = Object.keys(chk).map((k) => [`Check · ${k}`, chk[k] ? "ok" : "no"]);
    const riskRows = risk.checks ? Object.keys(risk.checks).map((k) => [`Risk · ${k}`, risk.checks[k] ? "ok" : "no"]) : [];

    const cards = [
      ["Session (UTC)", sess],
      ["Selector · trade_allowed", `${sel.trade_allowed ? "yes" : "no"} · ${escHtml(sel.reason || "—")}`],
      ["Selector · strategies", escHtml(stratUi || "—")],
      ["Strategy scores (top)", escHtml(stratLines || "—")],
      ["Suggested signal", escHtml(fmtSignalLine(sig))],
      ...chkRows,
      ...riskRows,
      ["Risk · approved", risk.approved ? "yes" : "no"],
      ["Risk · blocked_reason", escHtml(risk.blocked_reason || "—")],
      ["Lot (risk sized)", lot != null ? String(lot) : "—"],
    ];

    panel.innerHTML = cards
      .map(
        ([label, val]) =>
          `<div class="metric-card"><div class="metric-card__label">${escHtml(label)}</div><div class="metric-card__value">${val}</div></div>`
      )
      .join("");

    const canExec = !!sig && !!risk.approved && !!snapshot.mt5_connected;
    if (btn) btn.disabled = !canExec;
  }

  async function postExecute() {
    const pack = state.lastPack;
    const st = $("#executeStatus");
    const snap = pack && pack.snapshot;
    const inp = $("#approvedByInput");
    const ab = (inp && inp.value.trim()) || "operator";
    if (!snap || !snap.current_signal) {
      if (st) st.textContent = "No signal on snapshot.";
      return;
    }
    if (st) st.textContent = "Sending…";
    try {
      const res = await fetch(`${API_BASE}/api/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: getActiveSymbol(), signal: snap.current_signal, approved_by: ab }),
      });
      const j = await res.json().catch(() => ({}));
      if (res.ok && j.success) {
        const tk = j.execution && j.execution.ticket != null ? j.execution.ticket : "—";
        if (st) st.textContent = "OK · ticket " + tk;
      } else {
        const msg = j.error || (j.execution && j.execution.comment) || res.statusText || "?";
        if (st) st.textContent = "HTTP " + res.status + ": " + msg;
      }
    } catch (e) {
      if (st) st.textContent = "Network error: " + e;
    }
  }

  function startLivePoll() {
    stopLivePoll();
    livePollTimer = setInterval(async () => {
      const q = state.quadrant;
      const rid = state.regimeId;
      if (!q || rid == null || !state.lastPack || state.lastPack.source !== "mt5") return;
      const pack = await fetchRegimeData(q, rid);
      if (pack.source !== "mt5" || !pack.snapshot || !pack.snapshot.regime_detail) {
        stopLivePoll();
        return;
      }
      state.lastPack = pack;
      const nm = REGIME_NAMES[rid] || `ID ${rid}`;
      renderMetricsMt5(pack.snapshot);
      renderSignalExecute(pack.snapshot);
      renderChartsMt5(pack.snapshot.regime_detail);
      renderStrategies(q, rid, nm, pack.snapshot.regime_detail, state.strategyId);
      if (state.strategyId) selectStrategy(state.strategyId, { scroll: false });
    }, 10000);
  }

  async function fetchRegimeData(_quadrant, regimeId) {
    try {
      const u = new URL(`${API_BASE}/api/snapshot`);
      u.searchParams.set("symbol", getActiveSymbol());
      u.searchParams.set("tf_minutes", String(API_TF));
      u.searchParams.set("bars", String(API_BARS));
      u.searchParams.set("regime_id", String(regimeId));
      u.searchParams.set("atr_sl_mult", String(API_ATR_SL));
      u.searchParams.set("max_bars", String(API_MAX_BARS_RR));
      if (state.strategyId) u.searchParams.set("strategy_key", String(state.strategyId));
      const opts = {};
      if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
        opts.signal = AbortSignal.timeout(180000);
      }
      const res = await fetch(u.toString(), opts);
      let snap = null;
      try {
        snap = await res.json();
      } catch (_) {
        throw new Error(`Bad JSON from API (HTTP ${res.status}) — is ${API_BASE} the dashboard server?`);
      }
      if (!snap || typeof snap !== "object") {
        throw new Error("Invalid snapshot response");
      }
      if (!res.ok) {
        throw new Error(
          [snap.error, snap.error_type, `HTTP ${res.status}`].filter(Boolean).join(" · ") || `HTTP ${res.status}`
        );
      }
      if (typeof snap.error === "string" && snap.error.trim().length > 0) {
        throw new Error(snap.error.trim());
      }
      return { source: "mt5", snapshot: snap };
    } catch (e) {
      const msg = String(e && e.message ? e.message : e);
      console.warn("[dashboard] snapshot fetch failed:", e);
      return {
        source: "error",
        error: msg,
        snapshot: null,
      };
    }
  }

  /**
   * Apply MT5 snapshot to dashboard after fetch. preferredStrategyId keeps strategy tab when re-running analysis.
   */
  function applyRegimeSnapshotPack(pack, q, regimeId, nm, preferredStrategyId) {
    if (pack.source === "mt5" && pack.snapshot && pack.snapshot.regime_detail) {
      $("#analyticsSubtitle").textContent =
        `${q} · R${String(regimeId).padStart(2, "0")} ${nm} — scorecard from MT5 (MFE study, not dollar P&L).`;
      renderMetricsMt5(pack.snapshot);
      renderChartsMt5(pack.snapshot.regime_detail);
      renderStrategies(q, regimeId, nm, pack.snapshot.regime_detail, preferredStrategyId);
      renderSignalExecute(pack.snapshot);
      $("#backtestSubtitle").textContent =
        "Pick a strategy below — Steps 7–8 show its MT5 scorecard (MFE). Step 3–4 stay on regime-wide stats. Re-run analysis refreshes all.";
      startLivePoll();
    } else {
      stopLivePoll();
      const err = (pack && pack.error) || "MT5 snapshot failed";
      $("#analyticsSubtitle").textContent =
        `${q} · R${String(regimeId).padStart(2, "0")} ${nm} — MT5 data unavailable.`;
      $("#metricCards").innerHTML = `<div class="metric-card"><div class="metric-card__label">Dashboard server</div><div class="metric-card__value">${escHtml(err)}</div></div>`;
      destroyCharts();
      const hm = $("#heatmap");
      if (hm) hm.innerHTML = "";
      renderStrategies(q, regimeId, nm, null, null);
      renderSignalExecute(null);
      $("#backtestSubtitle").textContent =
        "Scorecard needs the Python dashboard server (MT5 in the same session). Start server.py, then reload.";
      renderPerformanceEmpty();
      $("#monthlyTable").innerHTML = "";
      $("#backtestMetrics").innerHTML = "";
      setStepHighlight(3);
      return;
    }
  }

  async function runAnalysis() {
    const q = state.quadrant;
    const rid = state.regimeId;
    const st = $("#analysisStatus");
    const btn = $("#btnAnalysis");
    if (!q || rid == null) {
      if (st) st.textContent = "Select quadrant + regime first.";
      return;
    }
    const nm = REGIME_NAMES[rid] || `ID ${rid}`;
    const keepSid = state.strategyId;
    if (btn) btn.disabled = true;
    if (st) st.textContent = "Fetching MT5 snapshot…";
    $("#analyticsSubtitle").textContent = `${q} · Regime ${rid} (${nm}) — refreshing…`;
    try {
      const pack = await fetchRegimeData(q, rid);
      state.lastPack = pack;
      applyRegimeSnapshotPack(pack, q, rid, nm, keepSid);
      setSnapshotStatusMessage(pack);
    } catch (e) {
      if (st) st.textContent = "Error: " + e;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function $(sel) {
    return document.querySelector(sel);
  }

  /** Update Step 3 status pill after snapshot fetch (regime pick or Run analysis). */
  function setSnapshotStatusMessage(pack) {
    const st = $("#analysisStatus");
    if (!st) return;
    if (pack.source === "mt5" && pack.snapshot && pack.snapshot.regime_detail) {
      st.textContent = "Regime data ready · " + new Date().toLocaleTimeString();
    } else if (pack.source === "error") {
      st.textContent = "Failed: " + (pack.error || "Unknown error").slice(0, 160);
    } else if (pack.source === "mt5" && pack.snapshot && !pack.snapshot.regime_detail) {
      st.textContent = "Failed: response has no regime_detail (check regime_id / server).";
    } else {
      st.textContent = "Failed: unexpected response from API.";
    }
  }

  function scrollPanelIntoView(id) {
    const el = document.getElementById(id);
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function destroyCharts() {
    Object.values(state.charts).forEach((c) => {
      try {
        c.destroy();
      } catch (_) {}
    });
    state.charts = {};
  }

  function destroyPracticalCharts() {
    Object.values(state.practicalCharts).forEach((c) => {
      try {
        c.destroy();
      } catch (_) {}
    });
    state.practicalCharts = {};
  }

  /** @param {number|null|undefined} x */
  function fmtPct01(x) {
    if (x == null || !Number.isFinite(Number(x))) return "—";
    return `${(Number(x) * 100).toFixed(2)}%`;
  }

  /** @param {number|null|undefined} x */
  function fmtNum(x, d = 4) {
    if (x == null || !Number.isFinite(Number(x))) return "—";
    return Number(x).toFixed(d);
  }

  /** Narrow wire snapshot to one regime + one strategy row (+ live/risk). No fabricated fields. */
  function practicalFocusedPayload(data, strategyKey) {
    if (!data || typeof data !== "object") return { _error: "no data" };
    if (data.error != null && data.error !== "") {
      return {
        _scope: "API returned an error — no regime_detail in this payload.",
        error: data.error,
        error_type: data.error_type != null ? data.error_type : null,
      };
    }
    const rd = data.regime_detail;
    const sk = (strategyKey || "").trim();
    let row = null;
    if (rd && Array.isArray(rd.strategies)) {
      row = sk ? rd.strategies.find((s) => s.strategy_key === sk) : null;
      if (!row && rd.strategies.length === 1) row = rd.strategies[0];
    }
    const livePick = [
      "last_price",
      "spread",
      "adx_14",
      "atr_14",
      "atr_pct",
      "ema50",
      "ema200",
      "quadrant",
      "confidence",
      "label",
      "direction",
      "mt5_connected",
      "last_update",
    ];
    const live = {};
    livePick.forEach((k) => {
      if (Object.prototype.hasOwnProperty.call(data, k)) live[k] = data[k];
    });
    const rowCopy = row ? JSON.parse(JSON.stringify(row)) : null;
    const rdOut = rd
      ? {
          ...rd,
          strategies: rowCopy ? [rowCopy] : [],
        }
      : null;
    return {
      _scope:
        "Focused view: same numbers as /api/snapshot, reorganized to one regime_detail strategies[] row + live strip + risk/signal.",
      meta: data.meta !== undefined ? data.meta : null,
      regime_detail: rdOut,
      selected_strategy_key: sk || null,
      selected_strategy_row: rowCopy,
      live,
      current_signal: data.current_signal !== undefined ? data.current_signal : null,
      signal_checks: data.signal_checks !== undefined ? data.signal_checks : null,
      account: data.account !== undefined ? data.account : null,
      risk_gate: data.risk_gate !== undefined ? data.risk_gate : null,
      lot_size: data.lot_size !== undefined ? data.lot_size : null,
      session: data.session !== undefined ? data.session : null,
    };
  }

  /** @type {Record<string, string>} */
  const PRACTICAL_RISK_CHECK_LABELS = {
    score: "Score gate",
    spread: "Spread gate",
    session: "Session gate",
    rr: "R:R gate",
    regime: "Regime gate",
    news: "News gate",
    daily_dd: "Daily drawdown gate",
    trade_count: "Trade count gate",
    kill_switch: "Kill switch gate",
  };

  function practicalSafeNum(x) {
    const n = Number(x);
    return Number.isFinite(n) ? n : null;
  }

  function practicalFmtDelta(cur, prev, digits = 4) {
    if (!Number.isFinite(cur) || !Number.isFinite(prev)) return "—";
    const d = cur - prev;
    const sign = d > 0 ? "+" : "";
    return `${sign}${d.toFixed(digits)} (prev ${prev.toFixed(digits)})`;
  }

  /** @param {any} data @param {any} rd */
  function practicalRegimeReasonBullets(data, rd) {
    const out = [];
    const adx = practicalSafeNum(data.adx_14);
    if (adx != null) {
      let tag = "moderate";
      if (adx >= 25) tag = "elevated (often read as stronger trend pressure)";
      else if (adx < 20) tag = "subdued";
      out.push(`Trend strength (ADX 14) looks ${tag} at ${adx.toFixed(2)}.`);
    }
    const e50 = practicalSafeNum(data.ema50);
    const e200 = practicalSafeNum(data.ema200);
    const px = practicalSafeNum(data.last_price);
    if (e50 != null && e200 != null) {
      out.push(`EMA structure: EMA50 is ${e50 > e200 ? "above" : "below"} EMA200 (${e50.toFixed(5)} vs ${e200.toFixed(5)}).`);
    }
    if (px != null && e50 != null && e200 != null) {
      if (px >= e50 && px >= e200) out.push("Price is above both EMAs vs this bar’s snapshot.");
      else if (px <= e50 && px <= e200) out.push("Price is below both EMAs vs this bar’s snapshot.");
      else out.push("Price lies between EMA50 and EMA200 — mixed vs averages.");
    }
    const atr = practicalSafeNum(data.atr_14);
    const atp = practicalSafeNum(data.atr_pct);
    if (atr != null) {
      out.push(
        `Volatility: ATR(14) = ${atr.toFixed(6)}${atp != null ? ` · ATR percentile (20-bar) = ${atp.toFixed(1)}` : ""}.`
      );
    }
    if (data.direction) out.push(`Direction field: ${String(data.direction)}.`);
    if (data.label) out.push(`Label field: ${String(data.label)}.`);
    if (data.total_bars != null && rd && rd.bars_in_regime != null) {
      out.push(
        `Taxonomy regime ${rd.regime_id}: ${rd.bars_in_regime} bars in loaded sample of ${data.total_bars} (${rd.pct_of_sample != null ? fmtNum(rd.pct_of_sample, 2) + "%" : "—"}).`
      );
    }
    const qb = data.quadrant_bars;
    if (qb && typeof qb === "object") {
      out.push(
        `Quadrant bar totals in sample: Q1=${qb.Q1 ?? "—"} Q2=${qb.Q2 ?? "—"} Q3=${qb.Q3 ?? "—"} Q4=${qb.Q4 ?? "—"}.`
      );
    }
    return out;
  }

  /** @param {any} rg @param {any} sc */
  function practicalGateChecklistHtml(rg, sc) {
    const keys = ["score", "spread", "session", "rr", "regime", "news", "daily_dd", "trade_count", "kill_switch"];
    let html =
      '<table class="data-table practical-gate-table"><thead><tr><th>Gate</th><th>risk_gate.checks</th><th>signal_checks</th></tr></thead><tbody>';
    keys.forEach((k) => {
      const label = PRACTICAL_RISK_CHECK_LABELS[k] || k;
      const rv = rg && rg.checks && k in rg.checks ? (rg.checks[k] ? "Pass" : "Fail") : "—";
      let sv = "—";
      if (sc && typeof sc === "object") {
        if (k === "score" && "score_ok" in sc) sv = sc.score_ok ? "Pass" : "Fail";
        if (k === "spread" && "spread_ok" in sc) sv = sc.spread_ok ? "Pass" : "Fail";
        if (k === "session" && "session_ok" in sc) sv = sc.session_ok ? "Pass" : "Fail";
        if (k === "rr" && "rr_ok" in sc) sv = sc.rr_ok ? "Pass" : "Fail";
        if (k === "regime" && "regime_ok" in sc) sv = sc.regime_ok ? "Pass" : "Fail";
      }
      html += `<tr><td>${escHtml(label)}</td><td>${escHtml(rv)}</td><td>${escHtml(sv)}</td></tr>`;
    });
    html += "</tbody></table>";
    return html;
  }

  /** One-line verdict from snapshot fields only (no fabricated execution state). */
  function practicalTradeVerdictBlock(data) {
    if (!data || typeof data !== "object") {
      return `<p class="practical__trade-verdict practical__trade-verdict--bad"><strong>Trade blocked</strong> — no data.</p>`;
    }
    if (data.error) {
      return `<p class="practical__trade-verdict practical__trade-verdict--bad"><strong>Trade blocked</strong> — ${escHtml(String(data.error))}</p>`;
    }
    if (data.mt5_connected === false) {
      return `<p class="practical__trade-verdict practical__trade-verdict--bad"><strong>Trade blocked</strong> — MT5 disconnected.</p>`;
    }
    const rg = data.risk_gate;
    if (rg == null || typeof rg !== "object") {
      return `<p class="practical__trade-verdict practical__trade-verdict--warn"><strong>Gate state unclear</strong> — no <code>risk_gate</code> in payload.</p>`;
    }
    const sel = data.strategy_selection;
    const cs = data.current_signal;
    if (rg.approved === false) {
      return `<p class="practical__trade-verdict practical__trade-verdict--bad"><strong>Trade blocked</strong>${rg.blocked_reason ? ` — ${escHtml(String(rg.blocked_reason))}` : " — risk_gate"}</p>`;
    }
    if (sel && sel.trade_allowed === false) {
      return `<p class="practical__trade-verdict practical__trade-verdict--bad"><strong>Trade blocked</strong>${sel.reason ? ` — ${escHtml(String(sel.reason))}` : " — strategy_selection"}</p>`;
    }
    const sz = practicalSafeNum(sel?.size_multiplier);
    if (sz != null && sz > 0 && sz < 1) {
      return `<p class="practical__trade-verdict practical__trade-verdict--warn"><strong>Reduced size</strong> — size_multiplier ${escHtml(String(sz))}.</p>`;
    }
    if (!cs) {
      return `<p class="practical__trade-verdict practical__trade-verdict--warn"><strong>No signal</strong> — <code>current_signal</code> missing.</p>`;
    }
    const st = String(cs.status || "");
    if (st === "WATCHING") {
      return `<p class="practical__trade-verdict practical__trade-verdict--warn"><strong>Signal watching</strong> — gates OK; waiting on trigger.</p>`;
    }
    if (st === "NOT_READY") {
      return `<p class="practical__trade-verdict practical__trade-verdict--warn"><strong>No signal / not ready</strong> — ${escHtml(st)}.</p>`;
    }
    if (st === "ARMED") {
      return `<p class="practical__trade-verdict practical__trade-verdict--ok"><strong>Trade allowed</strong> — signal ARMED and gates passed (verify broker).</p>`;
    }
    if (rg.approved && (sel == null || sel.trade_allowed !== false)) {
      return `<p class="practical__trade-verdict practical__trade-verdict--ok"><strong>Trade allowed</strong> — gates passed; signal status ${escHtml(st || "—")}.</p>`;
    }
    return `<p class="practical__trade-verdict practical__trade-verdict--warn"><strong>Gate state unclear</strong> — check checklist below.</p>`;
  }

  function practicalStrategyMatchHtml(data) {
    const scores = Array.isArray(data.strategy_scores) ? data.strategy_scores : [];
    let h = "";
    if (scores.length === 0) {
      h += "<p class=\"practical__hint\">No <code>strategy_scores</code> in payload.</p>";
    } else {
      const head =
        "<thead><tr><th>Name</th><th>Score</th><th>reg</th><th>conf</th><th>sess</th><th>sprd</th><th>min</th><th>sz</th></tr></thead>";
      const body = scores
        .map(
          (s) =>
            `<tr><td>${escHtml(s.name || "")}</td><td>${escHtml(String(s.score ?? ""))}</td><td>${escHtml(String(s.regime_points ?? ""))}</td><td>${escHtml(String(s.confidence_points ?? ""))}</td><td>${escHtml(String(s.session_points ?? ""))}</td><td>${escHtml(String(s.spread_points ?? ""))}</td><td>${escHtml(String(s.min_score ?? ""))}</td><td>${escHtml(String(s.size_mult ?? ""))}</td></tr>`
        )
        .join("");
      h += `<h5 class="practical__inline-h">strategy_scores</h5><table class="data-table">${head}<tbody>${body}</tbody></table>`;
    }
    const sel = data.strategy_selection;
    if (!sel || typeof sel !== "object") {
      h += "<p class=\"practical__hint\">No <code>strategy_selection</code>.</p>";
      return h;
    }
    h += `<p><strong>trade_allowed</strong>: ${sel.trade_allowed ? "Yes" : "No"} ${sel.reason ? `· ${escHtml(String(sel.reason))}` : ""}. <strong>size_multiplier</strong>: ${escHtml(String(sel.size_multiplier ?? "—"))}</p>`;
    const strats = Array.isArray(sel.strategies) ? sel.strategies : [];
    if (strats.length === 0) {
      h += "<p class=\"practical__hint\">Empty <code>strategy_selection.strategies</code> (e.g.Q4).</p>";
    } else {
      const head2 =
        "<thead><tr><th>Name</th><th>Score</th><th>Status</th><th>min_score</th><th>eff size_mult</th><th>Interpretation</th></tr></thead>";
      const body2 = strats
        .map((r) => {
          const elig = Number(r.score) >= Number(r.min_score);
          const why = !elig
            ? "Rejected: score &lt; min_score"
            : r.status === "NOT_READY"
              ? "Below execution threshold / NOT_READY"
              : r.status === "ARMED"
                ? "ARMED when signal matched"
                : "WATCHING — score ok";
          return `<tr><td>${escHtml(r.name || "")}</td><td>${escHtml(String(r.score ?? ""))}</td><td>${escHtml(String(r.status ?? ""))}</td><td>${escHtml(String(r.min_score ?? ""))}</td><td>${escHtml(String(r.size_mult ?? ""))}</td><td>${escHtml(why)}</td></tr>`;
        })
        .join("");
      h += `<h5 class="practical__inline-h">strategy_selection.strategies</h5><table class="data-table">${head2}<tbody>${body2}</tbody></table>`;
    }
    return h;
  }

  /** @param {any} data @param {any} row @param {any} cs */
  function practicalMoneyTableHtml(data, row, cs) {
    const gap = "Not in /api/snapshot — extend backend.";
    /** @type {[string, string, string][]} */
    const rows = [
      ["Net profit (after costs)", "—", gap],
      ["ROI %", "—", gap],
      ["Profit factor", "—", gap],
      ["Expectancy / trade", "—", gap],
      ["Average R", "—", gap],
      ["Max drawdown", "—", gap],
      ["Risk of ruin (model)", "—", gap],
    ];
    let be = "—";
    let beNote = "Provide current_signal.rr_ratio or SL/TP distances.";
    const rr = cs ? practicalSafeNum(cs.rr_ratio) : null;
    if (rr != null && rr > 0) {
      be = `${((100 * 1) / (1 + rr)).toFixed(2)}%`;
      beNote = `Toy BE win rate if avg win/loss ≈ ${rr.toFixed(2)}:1 (not full tariff model).`;
    }
    rows.push(["Break-even win rate (approx.)", be, beNote]);
    const lot = practicalSafeNum(data.lot_size);
    rows.push([
      "Lot (risk_gate output)",
      lot != null ? lot.toFixed(2) : "—",
      "Server-side heuristic; UI does not multiply regime/confidence/gate without extra inputs.",
    ]);
    rows.push([
      "Position sizing (concept)",
      lot != null && lot > 0 ? `${lot.toFixed(2)} lots if approved` : "0 / blocked",
      "Intended: base × regime_mult × conf_mult × gate_mult — partial visibility via strategy_selection.size_multiplier only.",
    ]);
    if (row) {
      const n = practicalSafeNum(row.trades);
      const wr1 = practicalSafeNum(row.wr_1r);
      if (n != null && wr1 != null) {
        rows.push([
          "MFE table (selected row)",
          `${n} trades · WR@1R ${(wr1 * 100).toFixed(2)}%`,
          "Historical-ish stats in regime_detail only; not audited P&amp;L.",
        ]);
      }
    }
    const thead = "<thead><tr><th>Metric</th><th>Value</th><th>Notes</th></tr></thead>";
    const tb = rows
      .map(([a, b, c]) => `<tr><td>${escHtml(a)}</td><td>${escHtml(b)}</td><td>${escHtml(c)}</td></tr>`)
      .join("");
    return `<table class="data-table">${thead}<tbody>${tb}</tbody></table>`;
  }

  /** @param {any} cur @param {any} prev */
  function practicalDeltaHtml(cur, prev) {
    if (!prev || typeof prev !== "object") {
      return "<p class=\"practical__hint\">No previous response stored yet — hit <strong>Send</strong> twice in this tab.</p>";
    }
    const rows = [];
    const pair = (label, c, p) => {
      const cn = practicalSafeNum(c);
      const pn = practicalSafeNum(p);
      if (cn != null && pn != null) rows.push(`${label}: ${practicalFmtDelta(cn, pn)}`);
      else if (String(c) !== String(p)) rows.push(`${label}: ${String(c)} (was ${String(p)})`);
    };
    pair("confidence", cur.confidence, prev.confidence);
    pair("adx_14", cur.adx_14, prev.adx_14);
    pair("atr_14", cur.atr_14, prev.atr_14);
    const e50c = practicalSafeNum(cur.ema50);
    const e50p = practicalSafeNum(prev.ema50);
    const e200c = practicalSafeNum(cur.ema200);
    const e200p = practicalSafeNum(prev.ema200);
    if (e50c != null && e200c != null && e50p != null && e200p != null) {
      rows.push(`EMA50−EMA200: ${practicalFmtDelta(e50c - e200c, e50p - e200p)}`);
    }
    const sc = cur.strategy_scores;
    const sp = prev.strategy_scores;
    if (Array.isArray(sc) && Array.isArray(sp) && sc[0] && sp[0]) {
      const c0 = practicalSafeNum(sc[0].score);
      const p0 = practicalSafeNum(sp[0].score);
      if (c0 != null && p0 != null) rows.push(`strategy_scores[0].score: ${practicalFmtDelta(c0, p0, 2)}`);
    }
    if (String(cur.session || "") !== String(prev.session || "")) {
      rows.push(`session: ${String(cur.session)} ← ${String(prev.session)}`);
    }
    if (Boolean(cur.risk_gate?.approved) !== Boolean(prev.risk_gate?.approved)) {
      rows.push(`risk_gate.approved: ${Boolean(cur.risk_gate?.approved)} ← ${Boolean(prev.risk_gate?.approved)}`);
    }
    const gateKeys = ["score", "spread", "session", "rr", "regime", "news", "daily_dd", "trade_count", "kill_switch"];
    const curCh = cur.risk_gate && cur.risk_gate.checks;
    const prevCh = prev.risk_gate && prev.risk_gate.checks;
    if (curCh && prevCh && typeof curCh === "object" && typeof prevCh === "object") {
      gateKeys.forEach((k) => {
        if (k in curCh && k in prevCh && Boolean(curCh[k]) !== Boolean(prevCh[k])) {
          const lab = PRACTICAL_RISK_CHECK_LABELS[k] || k;
          rows.push(`${lab} (risk_gate): ${curCh[k] ? "Pass" : "Fail"} ← ${prevCh[k] ? "Pass" : "Fail"}`);
        }
      });
    }
    const sigMap = [
      ["score_ok", "Score gate (signal_checks)"],
      ["spread_ok", "Spread gate (signal_checks)"],
      ["session_ok", "Session gate (signal_checks)"],
      ["rr_ok", "R:R gate (signal_checks)"],
      ["regime_ok", "Regime gate (signal_checks)"],
    ];
    const cSig = cur.signal_checks;
    const pSig = prev.signal_checks;
    if (cSig && pSig && typeof cSig === "object" && typeof pSig === "object") {
      sigMap.forEach(([key, lab]) => {
        if (key in cSig && key in pSig && Boolean(cSig[key]) !== Boolean(pSig[key])) {
          rows.push(`${lab}: ${cSig[key] ? "Pass" : "Fail"} ← ${pSig[key] ? "Pass" : "Fail"}`);
        }
      });
    }
    if (rows.length === 0) return "<p class=\"practical__hint\">No comparable fields changed.</p>";
    return `<ul class="practical__quant-list">${rows.map((t) => `<li>${escHtml(t)}</li>`).join("")}</ul>`;
  }

  function practicalComputeUiStates(data) {
    /** @type {{ cls: string, t: string }[]} */
    const out = [];
    if (!data || data.error) {
      out.push({ cls: "bad", t: "Snapshot error" });
      return out;
    }
    if (data.label || data.quadrant) out.push({ cls: "neutral", t: "Regime detected" });
    const sel = data.strategy_selection;
    if (sel && Array.isArray(sel.strategies) && sel.strategies.length) out.push({ cls: "neutral", t: "Strategy ranked" });
    const cs = data.current_signal;
    if (cs && cs.status === "WATCHING") out.push({ cls: "warn", t: "Signal watching" });
    if (cs && cs.status === "ARMED") out.push({ cls: "ok", t: "Signal armed" });
    if (!cs) out.push({ cls: "neutral", t: "No signal" });
    const rg = data.risk_gate;
    if (rg && rg.approved) out.push({ cls: "ok", t: "Risk gate passed" });
    else out.push({ cls: "bad", t: "Risk blocked" });
    if (sel && sel.trade_allowed === false) out.push({ cls: "warn", t: "Selector: trade disallowed" });
    if (sel && sel.trade_allowed && practicalSafeNum(sel.size_multiplier) != null && sel.size_multiplier < 1) {
      out.push({ cls: "warn", t: "Reduced size" });
    }
    if (cs && cs.status === "NOT_READY") out.push({ cls: "warn", t: "Not ready" });
    if (!data.mt5_connected) out.push({ cls: "bad", t: "MT5 disconnected" });
    if (rg && rg.approved && sel && sel.trade_allowed) out.push({ cls: "ok", t: "Execution ready (gates)" });
    return out;
  }

  function practicalStateStripHtml(data) {
    return practicalComputeUiStates(data)
      .map((s) => `<span class="practical__pill practical__pill--${s.cls}">${escHtml(s.t)}</span>`)
      .join("");
  }

  function practicalConclusionLines(data, rd, row, sk) {
    const L = [];
    if (data.error) {
      L.push(`Error: ${String(data.error)}`);
      return L;
    }
    L.push(`Regime headline: ${String(data.label || data.quadrant || "—")}.`);
    if (row) L.push(`Strategy row ${sk || row.strategy_key}: ${row.strategy_title || ""}.`);
    const rg = data.risk_gate;
    const sel = data.strategy_selection;
    L.push(
      `Executable per gates: risk ${rg && rg.approved ? "approved" : "blocked"}${rg && rg.blocked_reason ? ` (${rg.blocked_reason})` : ""}; selector ${sel && sel.trade_allowed ? "allows" : "blocks"} trading.`
    );
    if (row) {
      const n = practicalSafeNum(row.trades);
      const wr = practicalSafeNum(row.wr_1r);
      if (n != null && wr != null) L.push(`MFE cell: ${n} trades, ~${(wr * 100).toFixed(1)}% @1R — not live P&amp;L.`);
    }
    L.push("Next-state Markov / probabilities: not in payload (panel 8 explains API limits).");
    return L;
  }

  /** Selector-aligned confidence bucket (same thresholds as strategy_selector). */
  function practicalConfidenceTierLabel(c) {
    const x = practicalSafeNum(c);
    if (x == null) return "—";
    if (x < 50.0) return "low (<50)";
    if (x < 70.0) return "medium (50–69)";
    return "high (≥70)";
  }

  /**
   * Metrics computed in-browser from snapshot numbers only (no extra API).
   * @param {any} data
   * @param {any} rd
   * @param {any} row
   * @param {any} cs
   */
  function practicalCalculatedMetricsHtml(data, rd, row, cs) {
    if (!data || typeof data !== "object") {
      return "<p class=\"practical__hint\">No data.</p>";
    }
    /** @type {[string, string, string][]} */
    const rows = [];
    const px = practicalSafeNum(data.last_price);
    const atr = practicalSafeNum(data.atr_14);
    const e50 = practicalSafeNum(data.ema50);
    const e200 = practicalSafeNum(data.ema200);
    const adx = practicalSafeNum(data.adx_14);
    const conf = practicalSafeNum(data.confidence);

    if (adx != null) {
      rows.push(["ADX vs ref 40 (%)", `${Math.min(100, (adx / 40) * 100).toFixed(1)}%`, "(adx_14 ÷ 40) × 100, capped at 100"]);
    }
    if (conf != null) {
      rows.push(["Confidence tier", practicalConfidenceTierLabel(conf), "Cuts at 50 and 70 to match selector logic"]);
    }
    if (atr != null && atr > 0 && e50 != null && e200 != null) {
      rows.push(["EMA50 − EMA200 (in ATR)", ((e50 - e200) / atr).toFixed(3), "(ema50 − ema200) ÷ atr_14"]);
    }
    if (atr != null && atr > 0 && px != null && e50 != null) {
      rows.push(["(Price − EMA50) ÷ ATR", ((px - e50) / atr).toFixed(3), "Signed: + above EMA50"]);
    }
    if (atr != null && atr > 0 && px != null && e200 != null) {
      rows.push(["(Price − EMA200) ÷ ATR", ((px - e200) / atr).toFixed(3), "Signed: + above EMA200"]);
    }
    if (atr != null && atr > 0 && px != null && e50 != null && e200 != null) {
      const mid = (e50 + e200) / 2;
      rows.push(["(Price − EMA midpoint) ÷ ATR", ((px - mid) / atr).toFixed(3), "mid = (ema50 + ema200) ÷ 2"]);
    }
    if (cs && typeof cs === "object" && atr != null && atr > 0) {
      const ent = practicalSafeNum(cs.entry_price);
      const sl = practicalSafeNum(cs.stop_loss);
      const tp = practicalSafeNum(cs.take_profit);
      if (ent != null && sl != null) {
        rows.push(["|Entry − SL| ÷ ATR", (Math.abs(ent - sl) / atr).toFixed(3), "Stop distance in ATR(14) units"]);
      }
      if (ent != null && tp != null) {
        rows.push(["|TP − Entry| ÷ ATR", (Math.abs(tp - ent) / atr).toFixed(3), "Target distance in ATR(14) units"]);
      }
    }
    if (rd && practicalSafeNum(rd.pct_of_sample) != null) {
      rows.push(["Regime % of loaded sample", `${fmtNum(rd.pct_of_sample, 2)}%`, "regime_detail.pct_of_sample"]);
    }
    if (row) {
      const w1 = practicalSafeNum(row.wr_1r);
      const w4 = practicalSafeNum(row.wr_4r);
      if (w1 != null) {
        const edge = 2 * w1 - 1;
        rows.push([
          "1R symmetric edge proxy (R/trade)",
          edge.toFixed(4),
          "2 × wr_1r − 1 when avg win ≈ avg loss ≈ 1R (MFE cell, not live trades)",
        ]);
      }
      if (w1 != null && w4 != null) {
        rows.push(["WR@4R − WR@1R", `${((w4 - w1) * 100).toFixed(2)} pp`, "Same scorecard cell: hold quality vs 1R"]);
      }
    }
    if (cs && typeof cs === "object") {
      const rr = practicalSafeNum(cs.rr_ratio);
      if (rr != null && rr > 0) {
        const be = 100 / (1 + rr);
        rows.push(["Break-even win rate (RR)", `${be.toFixed(2)}%`, "1 ÷ (1 + rr_ratio) × 100 for this setup’s R multiple"]);
      }
    }
    const lot = practicalSafeNum(data.lot_size);
    const sel = data.strategy_selection;
    const sm = sel ? practicalSafeNum(sel.size_multiplier) : null;
    if (lot != null && sm != null) {
      rows.push(["Lots × size_multiplier", (lot * sm).toFixed(4), "lot_size × strategy_selection.size_multiplier"]);
    }

    if (rows.length === 0) {
      return "<p class=\"practical__hint\">Not enough numeric fields in this payload to compute rows.</p>";
    }
    const thead = "<thead><tr><th>Calculated metric</th><th>Value</th><th>Definition</th></tr></thead>";
    const tb = rows
      .map(([a, b, c]) => `<tr><td>${escHtml(a)}</td><td>${escHtml(b)}</td><td>${escHtml(c)}</td></tr>`)
      .join("");
    return `<table class="data-table practical-calc-table">${thead}<tbody>${tb}</tbody></table>`;
  }

  /** @param {string} label @param {any} valueNum @param {any} maxNum */
  function practicalLiveGaugeRow(label, valueNum, maxNum, digits = 0) {
    const v = practicalSafeNum(valueNum);
    const mx = practicalSafeNum(maxNum);
    if (v == null || mx == null || mx <= 0) {
      return `<div class="practical-gauge"><span class="practical-gauge__label">${escHtml(label)}</span><span class="practical-gauge__val">—</span><div class="practical-gauge__bar practical-gauge__bar--empty"></div></div>`;
    }
    const pct = Math.min(100, Math.max(0, (v / mx) * 100));
    return `<div class="practical-gauge"><span class="practical-gauge__label">${escHtml(label)}</span><span class="practical-gauge__val">${v.toFixed(digits)}</span><div class="practical-gauge__bar"><span class="practical-gauge__fill" style="width:${pct.toFixed(1)}%"></span></div></div>`;
  }

  /**
   * Quant desk “cockpit”: live strip + regime · strategy · action from snapshot only.
   * @param {any} data
   * @param {any} rd
   * @param {any} row
   * @param {string} sk
   */
  function practicalTraderCockpitRender(data, rd, row, sk) {
    /** @type {(id: string) => HTMLElement|null} */
    const by = (id) => document.getElementById(id);
    const wrap = by("practicalTraderCockpit");
    const sub = by("practicalCockpitSub");
    const live = by("practicalCockpitLive");
    const reg = by("practicalCockpitRegime");
    const strat = by("practicalCockpitStrategy");
    const act = by("practicalCockpitAction");
    if (!wrap) return;
    if (!data || typeof data !== "object" || data.error) {
      wrap.hidden = true;
      if (sub) sub.textContent = "";
      if (live) live.innerHTML = "";
      if (reg) reg.innerHTML = "";
      if (strat) strat.innerHTML = "";
      if (act) act.innerHTML = "";
      return;
    }
    wrap.hidden = false;
    const meta = data.meta || {};
    const scope =
      data.snapshot_scope === "practical_focus" ? "API: practical_focus (selected regime row + matching scores)" : "API: full snapshot";
    const warn = data._focus_warning ? ` · ${data._focus_warning}` : data._focus_note ? ` · ${data._focus_note}` : "";
    if (sub) {
      sub.textContent = `${meta.symbol || "—"} · ${meta.tf_minutes != null ? String(meta.tf_minutes) + "m" : "—"} · regime ${rd && rd.regime_id != null ? rd.regime_id : "—"} · strategy ${sk || (row && row.strategy_key) || "—"} — ${scope}${warn}`;
    }
    if (live) {
      const px = data.last_price;
      const sp = data.spread;
      let h = '<div class="practical__cockpit-price">';
      h += `<div><span class="practical__cockpit-k">Last</span> <span class="practical__cockpit-v">${px != null ? fmtNum(px, 5) : "—"}</span></div>`;
      h += `<div><span class="practical__cockpit-k">Spread</span> <span class="practical__cockpit-v">${sp != null ? escHtml(String(sp)) : "—"}</span></div>`;
      h += `<div><span class="practical__cockpit-k">Session</span> <span class="practical__cockpit-v">${data.session ? escHtml(String(data.session)) : "—"}</span></div>`;
      h += "</div>";
      h += '<div class="practical__cockpit-gauges">';
      h += practicalLiveGaugeRow("ADX (14) vs ref 40", data.adx_14, 40, 1);
      h += practicalLiveGaugeRow("Confidence / 100", data.confidence, 100, 1);
      h += practicalLiveGaugeRow("ATR pctile (20) / 100", data.atr_pct, 100, 1);
      h += "</div>";
      live.innerHTML = h;
    }

    if (reg) {
      const bullets = practicalRegimeReasonBullets(data, rd).slice(0, 4);
      let h = '<h4 class="practical__cockpit-h">What this regime is</h4>';
      h += `<p class="practical__cockpit-lead"><strong>${escHtml(String(data.label || (rd && rd.regime_name) || "—"))}</strong> · quadrant ${escHtml(String(data.quadrant || (rd && rd.quadrant) || "—"))} · direction ${escHtml(String(data.direction || "—"))}</p>`;
      if (bullets.length) h += `<ul class="practical__cockpit-ul">${bullets.map((b) => `<li>${escHtml(b)}</li>`).join("")}</ul>`;
      else h += '<p class="practical__hint">No live explanatory features in payload.</p>';
      reg.innerHTML = h;
    }
    if (strat) {
      let h = '<h4 class="practical__cockpit-h">What this strategy is</h4>';
      if (row) {
        h += `<p class="practical__cockpit-lead"><code>${escHtml(row.strategy_key || "")}</code> — ${escHtml(row.strategy_title || "")}</p>`;
        h += '<ul class="practical__cockpit-ul">';
        h += `<li>Mechanism: <code>${escHtml(String(row.signal_kind || "—"))}</code> · side rule ${escHtml(String(row.side_rule ?? "—"))}</li>`;
        h += `<li>Historical cell (sample): ${escHtml(String(row.trades ?? "—"))} trades · win rate @1R ${fmtPct01(row.wr_1r)} · @4R ${fmtPct01(row.wr_4r)}</li>`;
        h += `<li>Within-regime rank ${escHtml(String(row.rank_score ?? "—"))} · blend ${escHtml(String(row.score_wr_blend ?? "—"))}</li></ul>`;
      } else {
        h += '<p class="practical__hint">No scorecard row — check regime_id + strategy_key match the server bundle.</p>';
      }
      strat.innerHTML = h;
    }
    if (act) {
      let h = '<h4 class="practical__cockpit-h">What you do now</h4>';
      h += practicalTradeVerdictBlock(data);
      const cs = data.current_signal;
      if (cs && typeof cs === "object") {
        h += '<div class="practical__cockpit-signal">';
        h += `<span class="practical__cockpit-k">Suggested setup</span> `;
        h += `${escHtml(String(cs.direction || ""))} · entry ${cs.entry_price != null ? fmtNum(cs.entry_price, 5) : "—"} · SL ${cs.stop_loss != null ? fmtNum(cs.stop_loss, 5) : "—"} · TP ${cs.take_profit != null ? fmtNum(cs.take_profit, 5) : "—"}`;
        h += ` · R:R ${cs.rr_ratio != null ? escHtml(String(cs.rr_ratio)) : "—"} · <strong>${escHtml(String(cs.status || ""))}</strong>`;
        h += "</div>";
      } else {
        h += '<p class="practical__hint">No object-level signal in payload (common in Q4 or when MT5 is off). Use gates + scorecard only.</p>';
      }
      const rg = data.risk_gate;
      if (rg && rg.approved === false && rg.blocked_reason) {
        h += `<p class="practical__cockpit-block">${escHtml(String(rg.blocked_reason))}</p>`;
      }
      act.innerHTML = h;
    }
  }

  /**
   * Live MT5 snapshot dashboard (single response + optional previous for Δ).
   * @param {any} data
   * @param {string} selectedStrategyKey
   * @param {any} [prevSnapshot]
   */
  function renderPracticalVisuals(data, selectedStrategyKey, prevSnapshot) {
    destroyPracticalCharts();
    const el = (id) => document.getElementById(id);
    const viz = el("practicalViz");
    if (!viz) return;

    const hideFigures = () => {
      [
        "practicalSlotRegimeFreq",
        "practicalSlotQuadDist",
        "practicalSlotStratScores",
        "practicalSlotLine",
        "practicalSlotMonthly",
        "practicalSlotStratWr",
        "practicalSlotNextMarginal",
      ].forEach((id) => {
        const n = el(id);
        if (n) n.hidden = true;
      });
    };
    hideFigures();

    const stratTable = el("practicalStratTable");
    const explorer = el("practicalFieldExplorer");
    const strip = el("practicalStateStrip");
    const marketB = el("practicalMarketBody");
    const calcB = el("practicalCalcBody");
    const whyB = el("practicalRegimeWhyBody");
    const stratB = el("practicalStrategyBody");
    const gateB = el("practicalGateBody");
    const histI = el("practicalHistoryIntro");
    const moneyB = el("practicalMoneyBody");
    const riskB = el("practicalRiskBody");
    const deltaB = el("practicalDeltaBody");
    const nextB = el("practicalNextBody");
    const conc = el("practicalConclusionList");

    const cardGrid = (rows) =>
      `<div class="practical__metric-grid">${rows
        .map(
          ([k, v]) =>
            `<div class="practical-metric-card"><span class="practical-metric-card__k">${escHtml(k)}</span><span class="practical-metric-card__v">${v}</span></div>`
        )
        .join("")}</div>`;

    const clearPanels = () => {
      [whyB, stratB, gateB, histI, moneyB, riskB, deltaB, nextB, conc, calcB].forEach((n) => {
        if (n) n.innerHTML = "";
      });
      if (stratTable) stratTable.innerHTML = "";
      if (explorer) explorer.innerHTML = "";
      if (strip) strip.innerHTML = "";
      ["practicalCockpitLive", "practicalCockpitRegime", "practicalCockpitStrategy", "practicalCockpitAction"].forEach((id) => {
        const n = el(id);
        if (n) n.innerHTML = "";
      });
      const csub = el("practicalCockpitSub");
      if (csub) csub.textContent = "";
      const cwrap = el("practicalTraderCockpit");
      if (cwrap) cwrap.hidden = true;
    };

    if (!data || typeof data !== "object") {
      clearPanels();
      if (marketB) marketB.innerHTML = "<p class=\"practical__hint\">No response data.</p>";
      if (calcB) calcB.innerHTML = "";
      viz.hidden = false;
      return;
    }

    const rd = data.regime_detail;
    const meta = data.meta;
    const sk = (selectedStrategyKey || "").trim();
    let row = null;
    if (rd && Array.isArray(rd.strategies)) {
      row = sk ? rd.strategies.find((s) => s.strategy_key === sk) : null;
      if (!row && rd.strategies.length === 1) row = rd.strategies[0];
    }

    if (strip) strip.innerHTML = practicalStateStripHtml(data);

    if (data.error) {
      if (marketB) marketB.innerHTML = `<p class="practical__hint">${escHtml(String(data.error))}</p>`;
      if (whyB) whyB.innerHTML = "";
      if (stratB) stratB.innerHTML = practicalStrategyMatchHtml(data);
      if (gateB) gateB.innerHTML = practicalTradeVerdictBlock(data) + practicalGateChecklistHtml(data.risk_gate, data.signal_checks);
      if (histI) histI.innerHTML = "";
      if (stratTable) stratTable.innerHTML = "";
      if (moneyB) moneyB.innerHTML = practicalMoneyTableHtml(data, null, data.current_signal);
      if (riskB) riskB.innerHTML = "<p class=\"practical__hint\">Fix snapshot error before execution readiness.</p>";
      if (deltaB) deltaB.innerHTML = practicalDeltaHtml(data, prevSnapshot);
      if (nextB)
        nextB.innerHTML =
          "<p>No regime frequencies on error payload.</p>";
      if (conc)
        conc.innerHTML = practicalConclusionLines(data, rd, row, sk)
          .map((t) => `<li>${escHtml(t)}</li>`)
          .join("");
      if (calcB) calcB.innerHTML = practicalCalculatedMetricsHtml(data, rd, row, data.current_signal);
      const focusedTree = practicalFocusedPayload(data, sk);
      if (explorer) explorer.innerHTML = practicalRenderFieldTree(focusedTree, 0, 6);
      viz.hidden = false;
      practicalTraderCockpitRender(data, rd, row, sk);
      return;
    }

    if (marketB) {
      const mrows = [];
      if (meta) {
        mrows.push(["Symbol", escHtml(String(meta.symbol || "—"))]);
        if (meta.tf_minutes != null) mrows.push(["Timeframe (min)", escHtml(String(meta.tf_minutes))]);
        mrows.push(["Data source", escHtml(String(meta.source || "—"))]);
      }
      if (data.mt5_connected != null) mrows.push(["MT5 connected", data.mt5_connected ? "Yes" : "No"]);
      if (data.session) mrows.push(["Session (UTC)", escHtml(String(data.session))]);
      if (data.quadrant) mrows.push(["Quadrant", escHtml(String(data.quadrant))]);
      if (data.label) mrows.push(["Regime label", escHtml(String(data.label))]);
      if (data.direction) mrows.push(["Direction", escHtml(String(data.direction))]);
      if (data.confidence != null) mrows.push(["Confidence", fmtNum(data.confidence, 1)]);
      if (data.last_update) mrows.push(["Last update", escHtml(String(data.last_update))]);
      marketB.innerHTML = cardGrid(mrows);
    }

    if (calcB) calcB.innerHTML = practicalCalculatedMetricsHtml(data, rd, row, data.current_signal);

    if (whyB) {
      const bullets = practicalRegimeReasonBullets(data, rd);
      whyB.innerHTML = bullets.length
        ? `<ul class="practical__reason-ul">${bullets.map((b) => `<li>${escHtml(b)}</li>`).join("")}</ul>`
        : "<p class=\"practical__hint\">No live explanatory features in payload.</p>";
    }

    if (stratB) stratB.innerHTML = practicalStrategyMatchHtml(data);

    if (gateB) {
      const rg = data.risk_gate;
      const sc = data.signal_checks;
      const sel = data.strategy_selection;
      let top = "";
      if (rg) {
        top += `<p><strong>risk_gate.approved</strong>: ${rg.approved ? "Yes" : "No"}${rg.blocked_reason ? ` · ${escHtml(String(rg.blocked_reason))}` : ""}</p>`;
      }
      if (sel) {
        top += `<p><strong>strategy_selection.trade_allowed</strong>: ${sel.trade_allowed ? "Yes" : "No"}${sel.reason ? ` · ${escHtml(String(sel.reason))}` : ""} · <strong>size_multiplier</strong> ${escHtml(String(sel.size_multiplier ?? "—"))}</p>`;
      }
      gateB.innerHTML = practicalTradeVerdictBlock(data) + top + practicalGateChecklistHtml(rg, sc);
    }

    if (histI) {
      histI.innerHTML = row
        ? `<p>Scorecard row <code>${escHtml(row.strategy_key || "")}</code> — ${escHtml(row.strategy_title || "")}.</p>`
        : "<p class=\"practical__hint\">Include <code>regime_id</code> and a valid <code>strategy_key</code> for the MFE row.</p>";
    }

    if (stratTable) {
      if (row) {
        const head =
          "<thead><tr><th>Key</th><th>Title</th><th>Signal</th><th>Side</th><th>Trades</th><th>WR 1R</th><th>WR 2R</th><th>WR 3R</th><th>WR 4R</th><th>Rank</th><th>Blend</th></tr></thead>";
        const s = row;
        const body = `<tr class="practical-strat-row--selected"><td><code>${escHtml(s.strategy_key || "")}</code></td><td>${escHtml(s.strategy_title || "")}</td><td><code>${escHtml(s.signal_kind || "")}</code></td><td>${escHtml(String(s.side_rule ?? ""))}</td><td>${escHtml(String(s.trades ?? ""))}</td><td>${fmtPct01(s.wr_1r)}</td><td>${fmtPct01(s.wr_2r)}</td><td>${fmtPct01(s.wr_3r)}</td><td>${fmtPct01(s.wr_4r)}</td><td>${escHtml(String(s.rank_score ?? ""))}</td><td>${escHtml(String(s.score_wr_blend ?? ""))}</td></tr>`;
        stratTable.innerHTML = `<table class="data-table practical-strat-table">${head}<tbody>${body}</tbody></table>`;
      } else {
        stratTable.innerHTML = "<p class=\"practical__hint\">No scorecard row for this selection.</p>";
      }
    }

    if (moneyB) moneyB.innerHTML = practicalMoneyTableHtml(data, row, data.current_signal);

    if (riskB) {
      const rows = [];
      if (data.lot_size != null) rows.push(["Suggested lot (API)", fmtNum(data.lot_size, 4)]);
      const rg = data.risk_gate;
      if (rg && typeof rg === "object") {
        if (rg.approved != null) rows.push(["risk_gate.approved", rg.approved ? "Yes" : "No"]);
        if (rg.blocked_reason) rows.push(["Blocked reason", escHtml(String(rg.blocked_reason))]);
      }
      const ac = data.account;
      if (ac && typeof ac === "object") {
        if (ac.balance != null) rows.push(["Balance", fmtNum(ac.balance, 2)]);
        if (ac.equity != null) rows.push(["Equity", fmtNum(ac.equity, 2)]);
        if (ac.profit != null) rows.push(["Floating P/L", fmtNum(ac.profit, 2)]);
        if (ac.is_demo != null) rows.push(["Account", ac.is_demo ? "Demo" : "Live"]);
      }
      const cs = data.current_signal;
      if (cs && typeof cs === "object" && cs.status) {
        rows.push(["Signal status", escHtml(String(cs.status))]);
      } else {
        rows.push(["Signal object", "—"]);
      }
      if (!data.mt5_connected) rows.push(["Executable", "No — MT5 disconnected in payload"]);
      else if (rg && !rg.approved) rows.push(["Executable", "No — risk_gate"]);
      else if (data.strategy_selection && !data.strategy_selection.trade_allowed)
        rows.push(["Executable", "No — strategy_selection"]);
      else rows.push(["Executable (gates only)", "Checklist green — still verify broker/session manually"]);
      riskB.innerHTML = cardGrid(rows);
    }

    if (deltaB) deltaB.innerHTML = practicalDeltaHtml(data, prevSnapshot);

    if (nextB)
      nextB.innerHTML =
        "<p><strong>Conditional next regime / transition matrix</strong> is not returned by <code>/api/snapshot</code>. The chart below shows <em>marginal</em> regime frequencies in the loaded sample only (descriptive, not predictive).</p>";

    if (conc)
      conc.innerHTML = practicalConclusionLines(data, rd, row, sk)
        .map((t) => `<li>${escHtml(t)}</li>`)
        .join("");

    const focusedTree = practicalFocusedPayload(data, sk);
    if (explorer) explorer.innerHTML = practicalRenderFieldTree(focusedTree, 0, 6);

    viz.hidden = false;
    practicalTraderCockpitRender(data, rd, row, sk);

    if (typeof Chart === "undefined") return;

    const chartOpts = {
      scales: {
        x: { ticks: { color: "#8b949e", maxRotation: 0 }, grid: { color: "#30363d" } },
        y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
      },
      plugins: { legend: { labels: { color: "#8b949e" } } },
    };

    const pairsFromRegimeCounts = () => {
      const rc = data.regime_counts;
      if (!rc || typeof rc !== "object") return [];
      return Object.entries(rc)
        .map(([k, v]) => [k, Number(v) || 0])
        .sort((a, b) => b[1] - a[1])
        .slice(0, 16);
    };
    const pairs = pairsFromRegimeCounts();

    const cvRf = el("practicalChartRegimeFreq");
    const slotRf = el("practicalSlotRegimeFreq");
    if (cvRf && slotRf && pairs.length) {
      state.practicalCharts.freq = new Chart(cvRf.getContext("2d"), {
        type: "bar",
        data: {
          labels: pairs.map(([k]) => `R${k}`),
          datasets: [
            {
              label: "Bars",
              data: pairs.map(([, v]) => v),
              backgroundColor: "rgba(136,146,176,0.55)",
              borderRadius: 4,
            },
          ],
        },
        options: {
          indexAxis: "y",
          scales: {
            x: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
            y: { ticks: { color: "#8b949e", font: { size: 10 } }, grid: { display: false } },
          },
          plugins: { legend: { display: false } },
        },
      });
      slotRf.hidden = false;
    }

    const qb = data.quadrant_bars;
    const cvQ = el("practicalChartQuadDist");
    const slotQ = el("practicalSlotQuadDist");
    if (cvQ && slotQ && qb && typeof qb === "object") {
      const labels = ["Q1", "Q2", "Q3", "Q4"];
      const vals = labels.map((k) => Number(qb[k]) || 0);
      state.practicalCharts.quad = new Chart(cvQ.getContext("2d"), {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              data: vals,
              backgroundColor: ["#3fb950", "#d29922", "#58a6ff", "#8b949e"],
              borderRadius: 4,
            },
          ],
        },
        options: {
          scales: {
            x: { ticks: { color: "#8b949e" }, grid: { display: false } },
            y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          },
          plugins: { legend: { display: false } },
        },
      });
      slotQ.hidden = false;
    }

    const scores = Array.isArray(data.strategy_scores) ? data.strategy_scores : [];
    const cvSc = el("practicalChartStratScores");
    const slotSc = el("practicalSlotStratScores");
    if (cvSc && slotSc && scores.length) {
      state.practicalCharts.stratsc = new Chart(cvSc.getContext("2d"), {
        type: "bar",
        data: {
          labels: scores.map((s) => s.name || ""),
          datasets: [
            {
              label: "Score",
              data: scores.map((s) => practicalSafeNum(s.score) ?? 0),
              backgroundColor: "rgba(88,166,255,0.55)",
              borderRadius: 4,
            },
          ],
        },
        options: {
          scales: {
            x: { ticks: { color: "#8b949e", maxRotation: 35 }, grid: { color: "#30363d" } },
            y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" }, max: 100 },
          },
          plugins: { legend: { display: false } },
        },
      });
      slotSc.hidden = false;
    }

    const lineEl = el("practicalChartLine");
    const ls = rd && rd.line_series;
    const slotLine = el("practicalSlotLine");
    if (lineEl && ls && ls.x && ls.y && ls.x.length && slotLine) {
      state.practicalCharts.line = new Chart(lineEl.getContext("2d"), {
        type: "line",
        data: {
          labels: ls.x.map(String),
          datasets: [
            {
              label: ls.label || "Cumulative % in regime",
              data: ls.y,
              borderColor: "#58a6ff",
              backgroundColor: "rgba(88,166,255,0.12)",
              fill: true,
              tension: 0.35,
            },
          ],
        },
        options: chartOpts,
      });
      slotLine.hidden = false;
    }

    const barEl = el("practicalChartMonthly");
    const mo = rd && Array.isArray(rd.monthly) ? rd.monthly : [];
    const tail = mo.slice(-18);
    const slotMo = el("practicalSlotMonthly");
    if (barEl && tail.length && slotMo) {
      state.practicalCharts.bar = new Chart(barEl.getContext("2d"), {
        type: "bar",
        data: {
          labels: tail.map((m) => m.period),
          datasets: [
            {
              label: "Bars in regime",
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
      slotMo.hidden = false;
    }

    const wrEl = el("practicalChartStrategyWR");
    const slotWr = el("practicalSlotStratWr");
    if (wrEl && row && slotWr) {
      const labels = ["1R", "2R", "3R", "4R"];
      const vals = ["wr_1r", "wr_2r", "wr_3r", "wr_4r"].map((f) => practicalWrPct01(row[f]));
      if (vals.every((v) => v != null)) {
        state.practicalCharts.stratwr = new Chart(wrEl.getContext("2d"), {
          type: "bar",
          data: {
            labels,
            datasets: [
              {
                label: row.strategy_key || "Win %",
                data: vals,
                backgroundColor: "rgba(88,166,255,0.55)",
                borderRadius: 4,
              },
            ],
          },
          options: {
            scales: {
              x: { ticks: { color: "#8b949e" }, grid: { display: false } },
              y: {
                ticks: { color: "#8b949e", callback: (v) => `${v}%` },
                grid: { color: "#30363d" },
                title: { display: true, text: "Win rate (%)", color: "#8b949e" },
              },
            },
            plugins: { legend: { display: false } },
          },
        });
        slotWr.hidden = false;
      }
    }

    const cvNm = el("practicalChartNextMarginal");
    const slotNm = el("practicalSlotNextMarginal");
    if (cvNm && slotNm && pairs.length) {
      state.practicalCharts.nextm = new Chart(cvNm.getContext("2d"), {
        type: "bar",
        data: {
          labels: pairs.map(([k]) => `R${k}`),
          datasets: [
            {
              label: "Share of sample (bars)",
              data: pairs.map(([, v]) => v),
              backgroundColor: "rgba(210,153,34,0.45)",
              borderRadius: 4,
            },
          ],
        },
        options: {
          scales: {
            x: { ticks: { color: "#8b949e", maxRotation: 45 }, grid: { color: "#30363d" } },
            y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          },
          plugins: { legend: { display: false } },
        },
      });
      slotNm.hidden = false;
    }
  }
  /**
   * Nested HTML explorer for full response (depth-limited).
   * @param {any} val
   * @param {number} depth
   * @param {number} maxDepth
   */
  function practicalRenderFieldTree(val, depth, maxDepth) {
    if (val === null || val === undefined) {
      return `<span class="practical-tree-null">${escHtml(String(val))}</span>`;
    }
    if (typeof val !== "object") {
      return `<code class="practical-tree-scalar">${escHtml(JSON.stringify(val))}</code>`;
    }
    if (depth >= maxDepth) {
      try {
        return `<code class="practical-tree-scalar">${escHtml(JSON.stringify(val).slice(0, 2000))}${JSON.stringify(val).length > 2000 ? "…" : ""}</code>`;
      } catch {
        return "<span class=\"practical-tree-null\">[Object]</span>";
      }
    }
    if (Array.isArray(val)) {
      if (val.length === 0) return "<span class=\"practical-tree-null\">[]</span>";
      const rows = val
        .map(
          (item, i) =>
            `<li class="practical-tree-li"><span class="practical-tree-idx">[${i}]</span> ${practicalRenderFieldTree(item, depth + 1, maxDepth)}</li>`
        )
        .join("");
      return `<ul class="practical-tree-ul practical-tree-ul--arr">${rows}</ul>`;
    }
    const keys = Object.keys(val).sort();
    if (keys.length === 0) return "<span class=\"practical-tree-null\">{}</span>";
    const rows = keys
      .map(
        (k) =>
          `<li class="practical-tree-li"><span class="practical-tree-key">${escHtml(k)}</span> ${practicalRenderFieldTree(val[k], depth + 1, maxDepth)}</li>`
      )
      .join("");
    return `<ul class="practical-tree-ul">${rows}</ul>`;
  }

  function setStepHighlight(n) {
    document.querySelectorAll(".steps__item").forEach((el) => {
      el.classList.toggle("steps__item--active", el.dataset.step === String(n));
    });
  }

  function hideBelowRegime() {
    stopLivePoll();
    state.lastPack = null;
    ["stepAnalytics", "stepCharts", "stepStrategy", "stepSignalExecute", "stepBacktest", "stepPerformance"].forEach((id) => {
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
    renderSignalExecute(null);
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

    ["stepAnalytics", "stepCharts", "stepStrategy", "stepSignalExecute", "stepBacktest", "stepPerformance"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.hidden = false;
    });

    $("#analyticsSubtitle").textContent = `${q} · Regime ${regimeId} (${nm}) — loading…`;
    setStepHighlight(3);

    const pack = await fetchRegimeData(q, regimeId);
    state.lastPack = pack;
    applyRegimeSnapshotPack(pack, q, regimeId, nm, null);
    setSnapshotStatusMessage(pack);
    if (pack.source === "mt5" && pack.snapshot && pack.snapshot.regime_detail) {
      scrollPanelIntoView("stepAnalytics");
    }
  }

  function renderMetricsMt5(snapshot) {
    const rd = snapshot.regime_detail;
    const meta = snapshot.meta;
    if (!rd || !meta) return;
    const fresh = liveDataFreshness(snapshot.last_update);
    const liveCards = [
      ["Live · MT5 tick + H1 (200)", snapshot.mt5_connected ? "connected" : "offline"],
      ["Last price (ask)", formatLiveScalar(snapshot.last_price)],
      ["Spread (pips, est.)", formatLiveScalar(snapshot.spread)],
      ["ADX (14) · H1", formatLiveScalar(snapshot.adx_14)],
      ["ATR (14) · H1", formatLiveScalar(snapshot.atr_14)],
      ["ATR percentile (20-bar)", formatLiveScalar(snapshot.atr_pct)],
      ["EMA 50 · H1", formatLiveScalar(snapshot.ema50)],
      ["EMA 200 · H1", formatLiveScalar(snapshot.ema200)],
      ["Live headline Q1–Q4", formatLiveScalar(snapshot.quadrant)],
      ["Live headline label", formatLiveScalar(snapshot.label)],
      ["Live confidence (0–100)", formatLiveScalar(snapshot.confidence)],
      ["Direction (EMA stack)", formatLiveScalar(snapshot.direction)],
      ["Last update (UTC)", formatLiveScalar(snapshot.last_update) + fresh],
    ];
    const strats = rd.strategies || [];
    const sumTrades = strats.reduce((a, s) => a + s.trades, 0);
    let best = strats[0];
    strats.forEach((s) => {
      if (s.rank_score > (best ? best.rank_score : -1)) best = s;
    });
    const cards = [
      ...liveCards,
      ["Symbol · timeframe", `${meta.symbol} · ${meta.tf_minutes}m`],
      ["Bars loaded", String(meta.bars_loaded)],
      ["Bars this regime", String(rd.bars_in_regime)],
      ["% of sample", `${rd.pct_of_sample}%`],
      ["Taxonomy quadrant (this regime)", rd.quadrant],
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
    updateLivePill(snapshot);
    renderSignalExecute(snapshot);
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

  function renderStrategies(quadrant, regimeId, regimeName, regimeDetail, preferredStrategyId) {
    const base = strategiesForRegime(regimeId);
    const list = base.map((st) => {
      if (!regimeDetail || !regimeDetail.strategies) return st;
      const row = regimeDetail.strategies.find((s) => s.strategy_key === st.id);
      if (!row) return st;
      const extra = `MT5: trades ${row.trades} · wr₂ ${(row.wr_2r * 100).toFixed(1)}% · rank ${row.rank_score}`;
      return { ...st, desc: `${st.desc}\n${extra}` };
    });
    const pickId =
      preferredStrategyId && list.some((s) => s.id === preferredStrategyId) ? preferredStrategyId : list[0]?.id;

    const tabs = $("#strategyTabs");
    const panels = $("#strategyPanels");
    const ctx = $("#strategyContext");
    if (ctx) {
      ctx.textContent =
        `${quadrant} · R${String(regimeId).padStart(2, "0")} ${regimeName} — four strategies (same blueprint set as all regimes in ${quadrant}). Tap one to open its scorecard in Steps 7–8; regime-wide charts stay in Steps 3–4.`;
    }
    tabs.innerHTML = "";
    panels.innerHTML = "";

    list.forEach((st) => {
      const tab = document.createElement("button");
      tab.type = "button";
      const isActive = st.id === pickId;
      tab.className = "tab" + (isActive ? " tab--active" : "");
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

    list.forEach((st) => {
      const card = document.createElement("button");
      card.type = "button";
      const isSel = st.id === pickId;
      card.className = "strategy-card" + (isSel ? " strategy-card--selected" : "");
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

    if (list.length && pickId) selectStrategy(pickId, { scroll: false });
    if (!list.length) setStepHighlight(5);
  }

  function selectStrategy(strategyId, options) {
    const scroll = !options || options.scroll !== false;
    state.strategyId = strategyId;
    if (!state.quadrant || state.regimeId == null) return;
    const rid = state.regimeId;
    const regimeNm = REGIME_NAMES[rid] || `ID ${rid}`;
    const spec = strategiesForRegime(rid).find((s) => s.id === strategyId);
    const stratTitle = spec ? spec.name.replace(/\s+—\s+.+$/, "") : strategyId;
    const pack = state.lastPack;
    if (pack && pack.source === "mt5" && pack.snapshot && pack.snapshot.regime_detail) {
      const row = pack.snapshot.regime_detail.strategies.find((s) => s.strategy_key === strategyId);
      if (row) {
        const ctx = $("#strategyContext");
        if (ctx) {
          ctx.textContent =
            `${state.quadrant} · R${String(rid).padStart(2, "0")} ${regimeNm} — selected ${strategyId} (${stratTitle}). Regime-level metrics: Steps 3–4. This strategy’s MFE scorecard: Steps 7–8.`;
        }
        $("#backtestSubtitle").textContent =
          `${strategyId} · ${stratTitle} — MT5 scorecard for bars where taxonomy = R${String(rid).padStart(2, "0")} and this signal spec fired (MFE vs ATR stop, not $ P&L).`;
        renderBacktestScorecard(row);
        renderPerformanceMt5(row, pack.snapshot.regime_detail);
        setStepHighlight(8);
        if (scroll) scrollPanelIntoView("stepBacktest");
        return;
      }
    }
    const ctx = $("#strategyContext");
    if (ctx) {
      ctx.textContent =
        `${state.quadrant} · R${String(rid).padStart(2, "0")} ${regimeNm} — ${strategyId} selected; load regime snapshot to see scorecard.`;
    }
    renderPerformanceEmpty();
    $("#monthlyTable").innerHTML =
      `<thead><tr><th>Month</th><th>Bars (this regime)</th></tr></thead><tbody><tr><td colspan="2">MT5 scorecard required</td></tr></tbody>`;
    $("#backtestMetrics").innerHTML =
      `<div class="bt-metric"><div class="bt-metric__v">—</div><div class="bt-metric__k">No MT5 scorecard — load regime with API online</div></div>`;
    setStepHighlight(7);
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

  function getApiUnreachableLines() {
    const lines = [
      "1) Start API:  cd forex_regime",
      "   python dashboard_api/server.py   →  listening on port 8766",
      "",
      "2) Open UI with:  dashboard-lite\\run.ps1",
      "   URL must be http://127.0.0.1:8765/  (not a file:// path)",
      "",
      "3) API base this page uses:  " + API_BASE,
    ];
    if (location.protocol === "file:") {
      lines.push("", "• You are on file:// — fetch to localhost is often blocked.");
    }
    if (location.protocol === "https:" && String(API_BASE).startsWith("http:")) {
      lines.push("", "• HTTPS page cannot call HTTP API (mixed content).");
    }
    return lines;
  }

  /**
   * Small panel under PDF: kind = "clear" | "info" | "ok" | "err"
   * @param {string[]} lines
   */
  function setPdfDiagnostics(kind, head, lines) {
    const box = document.getElementById("pdfDiagnostics");
    const h = document.getElementById("pdfDiagnosticsHead");
    const b = document.getElementById("pdfDiagnosticsBody");
    if (!box || !h || !b) return;
    box.classList.remove("pdf-diagnostics--info", "pdf-diagnostics--ok", "pdf-diagnostics--err");
    if (!kind || kind === "clear") {
      box.hidden = true;
      h.textContent = "";
      b.textContent = "";
      return;
    }
    box.hidden = false;
    if (kind === "info") box.classList.add("pdf-diagnostics--info");
    else if (kind === "ok") box.classList.add("pdf-diagnostics--ok");
    else if (kind === "err") box.classList.add("pdf-diagnostics--err");
    h.textContent = head || "";
    b.textContent = Array.isArray(lines) ? lines.filter((x) => x !== undefined).join("\n") : String(lines || "");
  }

  /** Lightweight reachability check (no MT5). Returns { ok, detail }. */
  async function probeDashboardApi() {
    const hOpts = {};
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
      hOpts.signal = AbortSignal.timeout(15000);
    }
    try {
      const h = await fetch(`${API_BASE}/api/health`, hOpts);
      if (h.ok) return { ok: true, detail: "" };
      const t = await h.text().catch(() => "");
      return {
        ok: false,
        detail: `health HTTP ${h.status}${t ? " · " + t.slice(0, 80) : ""}`,
      };
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      return { ok: false, detail: msg };
    }
  }

  /**
   * One MT5 + scorecard pull; returns session JSON (session_id, endpoints, …).
   * @param {string} sym
   * @param {number} tf
   * @param {number} bars
   */
  async function fetchReportWarm(sym, tf, bars) {
    const u = new URL(`${API_BASE}/api/report/warm`);
    u.searchParams.set("symbol", sym);
    u.searchParams.set("tf_minutes", String(tf));
    u.searchParams.set("bars", String(bars));
    const opts = {};
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
      opts.signal = AbortSignal.timeout(900000);
    }
    const res = await fetch(u.toString(), opts);
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (!res.ok) {
      let msg = "HTTP " + res.status;
      if (ct.includes("json")) {
        const j = await res.json().catch(() => ({}));
        msg = (j && j.error) || msg;
      }
      throw new Error(msg);
    }
    return await res.json();
  }

  /**
   * Fetch one PDF chunk from the API (small response — avoids long single HTTP body).
   * @param {string} url
   * @param {number} timeoutMs
   * @returns {Promise<Uint8Array>}
   */
  async function fetchPdfChunk(url, timeoutMs) {
    const opts = {};
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
      opts.signal = AbortSignal.timeout(timeoutMs);
    }
    const res = await fetch(url, opts);
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (!res.ok) {
      let msg = "HTTP " + res.status;
      if (ct.includes("json")) {
        const j = await res.json().catch(() => ({}));
        msg = (j && j.error) || msg;
      }
      throw new Error(msg);
    }
    if (!ct.includes("pdf")) {
      throw new Error("Expected application/pdf, got " + (ct || "(empty)"));
    }
    return new Uint8Array(await res.arrayBuffer());
  }

  /**
   * Merge PDF parts in order (browser-side) using pdf-lib ESM.
   * @param {Uint8Array[]} parts
   */
  async function mergePdfParts(parts) {
    const mod = await import("https://cdn.jsdelivr.net/npm/pdf-lib@1.17.1/+esm");
    const PDFDocument = mod.PDFDocument;
    const merged = await PDFDocument.create();
    for (let i = 0; i < parts.length; i++) {
      const doc = await PDFDocument.load(parts[i]);
      const idx = doc.getPageIndices();
      const copied = await merged.copyPages(doc, idx);
      copied.forEach((p) => merged.addPage(p));
    }
    return await merged.save();
  }

  function getResearchSymbol() {
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("researchSymbolSelect"));
    const cust = /** @type {HTMLInputElement|null} */ (document.getElementById("researchSymbolCustom"));
    if (sel && sel.value === "__custom__" && cust) {
      const raw = (cust.value || "").trim().toUpperCase();
      return raw || "EURUSD";
    }
    if (sel && sel.value && sel.value !== "__custom__") return sel.value;
    return getActiveSymbol();
  }

  /** First checked timeframe row in catalog order; else URL tf + research bars input. */
  function getFirstEnabledResearchTf() {
    for (let i = 0; i < RESEARCH_TF_CATALOG.length; i++) {
      const cb = /** @type {HTMLInputElement|null} */ (document.querySelector(`input[data-research-tf-use="${i}"]`));
      if (cb && cb.checked) {
        const row = RESEARCH_TF_CATALOG[i];
        const barsInp = /** @type {HTMLInputElement|null} */ (document.querySelector(`input[data-research-tf-bars="${i}"]`));
        const bars = barsInp ? parseInt(barsInp.value, 10) || row.defaultBars : row.defaultBars;
        return { tf_minutes: row.tf_minutes, bars, label: row.label };
      }
    }
    const rb = /** @type {HTMLInputElement|null} */ (document.getElementById("researchBars"));
    const b = rb ? parseInt(rb.value, 10) || API_BARS : API_BARS;
    return { tf_minutes: API_TF, bars: b, label: "page_default" };
  }

  /** When MT5 snapshot is unavailable: show quadrant blueprint names (metrics zero). */
  function researchStrategiesFromBlueprint(rid) {
    const q = REGIME_TO_QUAD[rid];
    const bps = q ? BLUEPRINTS[q] : null;
    if (!bps || !bps.length) return [];
    return bps.map((bp, idx) => ({
      strategy_key: "R" + String(rid).padStart(2, "0") + "-S" + String(idx + 1).padStart(2, "0"),
      strategy_title: bp.title,
      signal_kind: bp.kind,
      side_rule: bp.side,
      trades: 0,
      wr_1r: 0,
      wr_2r: 0,
      wr_3r: 0,
      wr_4r: 0,
      rank_score: 0,
      score_wr_blend: 0,
      risk_pct: "",
      rr_ratio: "",
      atr_multiplier: "",
      position_size: "",
      enabled: true,
      _source: "blueprint_defaults",
    }));
  }

  function collectStrategyRowsFromDom() {
    const tbody = document.getElementById("researchStrategyTbody");
    if (!tbody) return [];
    /** @type {typeof researchStrategiesDraft} */
    const out = [];
    tbody.querySelectorAll("tr[data-sk]").forEach((tr) => {
      const sk = tr.getAttribute("data-sk") || "";
      const en = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=enabled]"));
      const title = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=title]"));
      const sig = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=signal]"));
      const side = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=side]"));
      const trades = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=trades]"));
      const wr1 = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=wr1]"));
      const wr2 = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=wr2]"));
      const wr3 = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=wr3]"));
      const wr4 = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=wr4]"));
      const rnk = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=rank]"));
      const bl = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=blend]"));
      const risk = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=risk]"));
      const rr = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=rr]"));
      const atr = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=atr]"));
      const pos = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=pos]"));
      const g = (inp, def = 0) => {
        if (!inp || inp.value.trim() === "") return def;
        const n = parseFloat(inp.value);
        return Number.isFinite(n) ? n : def;
      };
      out.push({
        strategy_key: sk,
        strategy_title: (title && title.value) || "",
        signal_kind: (sig && sig.value) || "",
        side_rule: side ? parseInt(side.value, 10) || 0 : 0,
        trades: Math.round(g(trades, 0)),
        wr_1r: g(wr1, 0),
        wr_2r: g(wr2, 0),
        wr_3r: g(wr3, 0),
        wr_4r: g(wr4, 0),
        rank_score: g(rnk, 0),
        score_wr_blend: g(bl, 0),
        risk_pct: (risk && risk.value) || "",
        rr_ratio: (rr && rr.value) || "",
        atr_multiplier: (atr && atr.value) || "",
        position_size: (pos && pos.value) || "",
        enabled: !!(en && en.checked),
      });
    });
    return out;
  }

  function buildResearchPayload() {
    const selR = /** @type {HTMLSelectElement|null} */ (document.getElementById("researchRegimeSelect"));
    const rid = selR ? parseInt(selR.value, 10) || 1 : 1;
    const sym = getResearchSymbol();
    const barsGlobal = (() => {
      const el = /** @type {HTMLInputElement|null} */ (document.getElementById("researchBars"));
      return el ? parseInt(el.value, 10) || API_BARS : API_BARS;
    })();
    /** @type {{ tf_minutes: number, bars: number, label: string, enabled: boolean }[]} */
    const tfRows = [];
    RESEARCH_TF_CATALOG.forEach((row, i) => {
      const cb = /** @type {HTMLInputElement|null} */ (document.querySelector(`input[data-research-tf-use="${i}"]`));
      const barsInp = /** @type {HTMLInputElement|null} */ (document.querySelector(`input[data-research-tf-bars="${i}"]`));
      const bars = barsInp ? parseInt(barsInp.value, 10) || row.defaultBars : row.defaultBars;
      tfRows.push({
        tf_minutes: row.tf_minutes,
        bars,
        label: row.label,
        enabled: !!(cb && cb.checked),
      });
    });
    const enabledProfiles = tfRows.filter((r) => r.enabled);
    const timeframes = enabledProfiles.map((r) => ({
      tf_minutes: r.tf_minutes,
      bars: r.bars,
      label: r.label,
    }));
    const primaryTf = enabledProfiles[0] ? enabledProfiles[0].tf_minutes : API_TF;
    return {
      version: 1,
      symbol: sym,
      regime_id: rid,
      regime_name: REGIME_NAMES[rid] || "",
      quadrant: REGIME_TO_QUAD[rid] || "",
      bars: barsGlobal,
      tf_minutes: primaryTf,
      atr_sl_mult: (() => {
        const el = /** @type {HTMLInputElement|null} */ (document.getElementById("researchAtrSl"));
        const v = el ? parseFloat(el.value) : NaN;
        return Number.isFinite(v) ? v : API_ATR_SL;
      })(),
      max_bars: (() => {
        const el = /** @type {HTMLInputElement|null} */ (document.getElementById("researchMaxBars"));
        const v = el ? parseInt(el.value, 10) : NaN;
        return Number.isFinite(v) && v > 0 ? v : API_MAX_BARS_RR;
      })(),
      confidence: (() => {
        const el = /** @type {HTMLInputElement|null} */ (document.getElementById("researchConfidence"));
        const t = el && el.value.trim();
        return t || null;
      })(),
      historical: {
        range_note: (() => {
          const el = /** @type {HTMLInputElement|null} */ (document.getElementById("researchHistRange"));
          return (el && el.value.trim()) || "";
        })(),
        start_date_utc: (() => {
          const el = /** @type {HTMLInputElement|null} */ (document.getElementById("researchDateStart"));
          return (el && el.value) || null;
        })(),
        end_date_utc: (() => {
          const el = /** @type {HTMLInputElement|null} */ (document.getElementById("researchDateEnd"));
          return (el && el.value) || null;
        })(),
      },
      report_options: {
        volume: !!(/** @type {HTMLInputElement|null} */ (document.getElementById("researchOptVolume")))?.checked,
        institutional: !!(/** @type {HTMLInputElement|null} */ (document.getElementById("researchOptInstitutional")))?.checked,
        equity_curve: !!(/** @type {HTMLInputElement|null} */ (document.getElementById("researchOptEquity")))?.checked,
      },
      timeframes,
      strategies: collectStrategyRowsFromDom(),
      _backend: {
        warm: "POST /api/report/warm — scorecard uses symbol + first timeframes[] row (tf_minutes, bars); full JSON echoed in session GET …/client-request",
        dates_volume_equity: "Calendar dates & report_options are stored for orchestration; scorecard still uses bar count until engine supports date-range slicing.",
      },
    };
  }

  function researchPayloadForSingleTf(fullPayload, tfDef) {
    const p = JSON.parse(JSON.stringify(fullPayload));
    p.timeframes = [{ tf_minutes: tfDef.tf_minutes, bars: tfDef.bars, label: tfDef.label }];
    p.tf_minutes = tfDef.tf_minutes;
    p.bars = tfDef.bars;
    return p;
  }

  function updateResearchHeavyWarning() {
    const el = document.getElementById("researchHeavyWarn");
    if (!el) return;
    const p = buildResearchPayload();
    const tf = p.timeframes || [];
    let riskScore = 0;
    tf.forEach((t) => {
      const bars = t.bars || 0;
      const m = t.tf_minutes || 60;
      if (m <= 5 && bars > 15000) riskScore += 2;
      else if (m <= 15 && bars > 12000) riskScore += 1;
      if (bars > 25000) riskScore += 1;
    });
    if (tf.length > 3) riskScore += 1;
    if (riskScore >= 2) {
      el.hidden = false;
      el.className = "research__warn research__warn--info";
      el.textContent =
        "Heavy request: low timeframe(s) with high bar counts and/or many enabled TFs will increase MT5 load and PDF time. Consider lowering bars or fewer TFs.";
    } else {
      el.hidden = true;
      el.textContent = "";
    }
  }

  function scheduleResearchPreview() {
    if (researchPreviewScheduled) return;
    researchPreviewScheduled = true;
    requestAnimationFrame(() => {
      researchPreviewScheduled = false;
      const pre = document.getElementById("researchJsonPreview");
      if (pre) {
        try {
          pre.textContent = JSON.stringify(buildResearchPayload(), null, 2);
        } catch (e) {
          pre.textContent = String(e);
        }
      }
      updateResearchHeavyWarning();
    });
  }

  /** Debounced refetch of strategy scorecard defaults when TF / bars / symbol context changes. */
  function scheduleResearchStrategiesReload() {
    if (researchStrategiesRefreshTimer) clearTimeout(researchStrategiesRefreshTimer);
    researchStrategiesRefreshTimer = setTimeout(() => {
      researchStrategiesRefreshTimer = null;
      refreshResearchStrategiesFromApi();
    }, 450);
  }

  function renderResearchStrategyTbody() {
    const tbody = document.getElementById("researchStrategyTbody");
    if (!tbody) return;
    const f = (x) => {
      const n = Number(x);
      return Number.isFinite(n) ? n.toFixed(4) : "0.0000";
    };
    if (!researchStrategiesDraft.length) {
      tbody.innerHTML =
        '<tr><td colspan="16" class="research__hint">No rows — pick a regime (defaults load from MT5 snapshot when API is up).</td></tr>';
      return;
    }
    tbody.innerHTML = researchStrategiesDraft
      .map((s) => {
        const trd = s.trades != null ? Math.round(Number(s.trades)) : 0;
        return `
      <tr data-sk="${escHtml(s.strategy_key)}">
        <td><input type="checkbox" data-f="enabled" ${s.enabled ? "checked" : ""} /></td>
        <td><input type="text" data-f="title" value="${escAttr(s.strategy_title)}" /></td>
        <td><code>${escHtml(s.strategy_key)}</code></td>
        <td><input type="text" data-f="signal" value="${escAttr(s.signal_kind)}" /></td>
        <td><input type="number" data-f="side" value="${s.side_rule}" step="1" /></td>
        <td><input type="number" data-f="trades" min="0" step="1" value="${trd}" /></td>
        <td><input type="text" data-f="wr1" inputmode="decimal" value="${f(s.wr_1r)}" /></td>
        <td><input type="text" data-f="wr2" inputmode="decimal" value="${f(s.wr_2r)}" /></td>
        <td><input type="text" data-f="wr3" inputmode="decimal" value="${f(s.wr_3r)}" /></td>
        <td><input type="text" data-f="wr4" inputmode="decimal" value="${f(s.wr_4r)}" /></td>
        <td><input type="text" data-f="rank" inputmode="decimal" value="${f(s.rank_score)}" /></td>
        <td><input type="text" data-f="blend" inputmode="decimal" value="${f(s.score_wr_blend)}" /></td>
        <td><input type="text" data-f="risk" value="${escAttr(s.risk_pct)}" placeholder="%" /></td>
        <td><input type="text" data-f="rr" value="${escAttr(s.rr_ratio)}" /></td>
        <td><input type="text" data-f="atr" value="${escAttr(s.atr_multiplier)}" /></td>
        <td><input type="text" data-f="pos" value="${escAttr(s.position_size)}" /></td>
      </tr>`;
      })
      .join("");
    tbody.querySelectorAll("input").forEach((inp) => inp.addEventListener("input", scheduleResearchPreview));
    tbody.querySelectorAll("input[type=checkbox]").forEach((inp) => inp.addEventListener("change", scheduleResearchPreview));
  }

  async function refreshResearchStrategiesFromApi() {
    const hint = document.getElementById("researchStrategyHint");
    const selR = /** @type {HTMLSelectElement|null} */ (document.getElementById("researchRegimeSelect"));
    const rid = selR ? parseInt(selR.value, 10) || 1 : 1;
    const sym = getResearchSymbol();
    const { tf_minutes: tfm, bars } = getFirstEnabledResearchTf();
    if (hint) hint.textContent = "Loading snapshot…";
    try {
      const u = new URL(`${API_BASE}/api/snapshot`);
      u.searchParams.set("symbol", sym);
      u.searchParams.set("tf_minutes", String(tfm));
      u.searchParams.set("bars", String(bars));
      u.searchParams.set("atr_sl_mult", String(API_ATR_SL));
      u.searchParams.set("max_bars", String(API_MAX_BARS_RR));
      u.searchParams.set("regime_id", String(rid));
      const opts = {};
      if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
        opts.signal = AbortSignal.timeout(180000);
      }
      const res = await fetch(u.toString(), opts);
      const snap = await res.json().catch(() => ({}));
      if (!res.ok || (snap && snap.error)) {
        throw new Error((snap && snap.error) || "HTTP " + res.status);
      }
      const rd = snap.regime_detail;
      const strats = (rd && rd.strategies) || [];
      researchStrategiesDraft = strats.map((row) => ({
        strategy_key: row.strategy_key || "",
        strategy_title: row.strategy_title || "",
        signal_kind: row.signal_kind || "",
        side_rule: row.side_rule != null ? Number(row.side_rule) : 0,
        trades: row.trades != null ? Math.round(Number(row.trades)) : 0,
        wr_1r: row.wr_1r != null ? Number(row.wr_1r) : 0,
        wr_2r: row.wr_2r != null ? Number(row.wr_2r) : 0,
        wr_3r: row.wr_3r != null ? Number(row.wr_3r) : 0,
        wr_4r: row.wr_4r != null ? Number(row.wr_4r) : 0,
        rank_score: row.rank_score != null ? Number(row.rank_score) : 0,
        score_wr_blend: row.score_wr_blend != null ? Number(row.score_wr_blend) : 0,
        risk_pct: "",
        rr_ratio: "",
        atr_multiplier: "",
        position_size: "",
        enabled: true,
        _source: "mt5_scorecard",
      }));
      const confEl = /** @type {HTMLInputElement|null} */ (document.getElementById("researchConfidence"));
      if (confEl && snap.confidence != null && !confEl.dataset.touched) confEl.value = String(snap.confidence);
      renderResearchStrategyTbody();
      const srcHint = rd ? ` — bars in regime ${rd.bars_in_regime} (${rd.pct_of_sample}% of sample)` : "";
      if (hint) hint.textContent = "Loaded " + researchStrategiesDraft.length + " strategies from MT5 scorecard (R" + String(rid).padStart(2, "0") + ")" + srcHint + ".";
      scheduleResearchPreview();
    } catch (e) {
      researchStrategiesDraft = researchStrategiesFromBlueprint(rid);
      renderResearchStrategyTbody();
      const msg = e && e.message ? e.message : String(e);
      if (hint)
        hint.textContent =
          "MT5 snapshot unavailable — showing quadrant blueprint names (metrics 0). " + msg.slice(0, 120);
      scheduleResearchPreview();
    }
  }

  function setResearchProgressStep(activeKey, doneKeys) {
    document.querySelectorAll("#researchProgressList li").forEach((li) => {
      const k = li.getAttribute("data-step") || "";
      li.classList.remove("research__step--active", "research__step--done");
      if (doneKeys && doneKeys.has(k)) li.classList.add("research__step--done");
      if (activeKey && k === activeKey) li.classList.add("research__step--active");
    });
  }

  /**
   * @param {Record<string, unknown>} payload
   */
  async function fetchReportWarmPost(payload) {
    const opts = {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    };
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
      opts.signal = AbortSignal.timeout(900000);
    }
    const res = await fetch(`${API_BASE}/api/report/warm`, opts);
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (!res.ok) {
      let msg = "HTTP " + res.status;
      if (ct.includes("json")) {
        const j = await res.json().catch(() => ({}));
        msg = (j && j.error) || msg;
      }
      throw new Error(msg);
    }
    return await res.json();
  }

  /**
   * @param {string} sid
   * @param {(chunkIndex: number, chunkTotal: number) => void} [onChunk]
   */
  async function runSessionPdfAllChunks(sid, onChunk) {
    const chunkTo = 180000;
    const partUrls = [API_BASE + "/api/report/session/" + sid + "/pdf/cover"];
    for (let r = 1; r <= 52; r++) partUrls.push(API_BASE + "/api/report/session/" + sid + "/pdf/regime/" + r);
    await import("https://cdn.jsdelivr.net/npm/pdf-lib@1.17.1/+esm");
    const parts = [];
    for (let i = 0; i < partUrls.length; i++) {
      if (onChunk) onChunk(i + 1, partUrls.length);
      parts.push(await fetchPdfChunk(partUrls[i], chunkTo));
    }
    return mergePdfParts(parts);
  }

  function cloneTopSymbolOptionsToResearch() {
    const top = /** @type {HTMLSelectElement|null} */ (document.getElementById("symbolSelect"));
    const rs = /** @type {HTMLSelectElement|null} */ (document.getElementById("researchSymbolSelect"));
    if (!top || !rs) return;
    rs.innerHTML = top.innerHTML;
  }

  function syncResearchSymbolFromTopbar() {
    const top = /** @type {HTMLSelectElement|null} */ (document.getElementById("symbolSelect"));
    const cust = /** @type {HTMLInputElement|null} */ (document.getElementById("symbolCustom"));
    const rs = /** @type {HTMLSelectElement|null} */ (document.getElementById("researchSymbolSelect"));
    const rc = /** @type {HTMLInputElement|null} */ (document.getElementById("researchSymbolCustom"));
    if (!top || !rs) return;
    researchSymbolSync = true;
    rs.value = top.value;
    if (top.value === "__custom__" && cust && rc) {
      rc.hidden = false;
      rc.value = cust.value;
    } else if (rc) {
      rc.hidden = true;
      rc.value = "";
    }
    researchSymbolSync = false;
  }

  function applyTopbarSymbolFromResearch() {
    const top = /** @type {HTMLSelectElement|null} */ (document.getElementById("symbolSelect"));
    const cust = /** @type {HTMLInputElement|null} */ (document.getElementById("symbolCustom"));
    const rs = /** @type {HTMLSelectElement|null} */ (document.getElementById("researchSymbolSelect"));
    const rc = /** @type {HTMLInputElement|null} */ (document.getElementById("researchSymbolCustom"));
    if (!top || !rs) return;
    researchSymbolSync = true;
    top.value = rs.value;
    if (rs.value === "__custom__" && cust && rc) {
      cust.hidden = false;
      cust.value = rc.value;
      API_SYMBOL = getResearchSymbol();
    } else if (cust) {
      cust.hidden = true;
      cust.value = "";
      API_SYMBOL = rs.value;
    }
    researchSymbolSync = false;
    fetchLiveStrip(API_SYMBOL);
    scheduleResearchStrategiesReload();
  }

  function initResearchPanel() {
    cloneTopSymbolOptionsToResearch();
    syncResearchSymbolFromTopbar();

    const rs = /** @type {HTMLSelectElement|null} */ (document.getElementById("researchSymbolSelect"));
    const rc = /** @type {HTMLInputElement|null} */ (document.getElementById("researchSymbolCustom"));
    rs?.addEventListener("change", () => {
      if (!rc || !rs) return;
      if (rs.value === "__custom__") {
        rc.hidden = false;
        rc.focus();
        scheduleResearchPreview();
        scheduleResearchStrategiesReload();
      } else {
        rc.hidden = true;
        rc.value = "";
        applyTopbarSymbolFromResearch();
        scheduleResearchPreview();
      }
    });
    rc?.addEventListener("blur", () => {
      if (rs && rs.value === "__custom__") applyTopbarSymbolFromResearch();
    });
    rc?.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") applyTopbarSymbolFromResearch();
    });

    const regSel = /** @type {HTMLSelectElement|null} */ (document.getElementById("researchRegimeSelect"));
    if (regSel && !regSel.options.length) {
      for (let i = 1; i <= 52; i++) {
        const o = document.createElement("option");
        o.value = String(i);
        o.textContent = "R" + String(i).padStart(2, "0") + " · " + (REGIME_NAMES[i] || "");
        regSel.appendChild(o);
      }
    }
    if (regSel) {
      const initRid =
        API_REGIME_URL >= 1 && API_REGIME_URL <= 52
          ? API_REGIME_URL
          : state.regimeId != null
            ? state.regimeId
            : 7;
      regSel.value = String(initRid);
    }
    regSel?.addEventListener("change", () => {
      const rid = parseInt(regSel.value, 10) || 1;
      const nm = document.getElementById("researchRegimeName");
      const qu = document.getElementById("researchQuadrant");
      if (nm) nm.value = REGIME_NAMES[rid] || "";
      if (qu) qu.value = REGIME_TO_QUAD[rid] || "";
      scheduleResearchPreview();
      refreshResearchStrategiesFromApi();
    });

    const tbody = document.getElementById("researchTfTbody");
    if (tbody) {
      tbody.innerHTML = RESEARCH_TF_CATALOG.map((row, i) => {
        const on = row.tf_minutes === API_TF;
        const barsVal = row.tf_minutes === API_TF ? API_BARS : row.defaultBars;
        return `<tr>
          <td><input type="checkbox" data-research-tf-use="${i}" ${on ? "checked" : ""} /></td>
          <td class="research__tf-label">${row.label}</td>
          <td>${row.tf_minutes}</td>
          <td><input type="number" data-research-tf-bars="${i}" min="100" step="100" value="${barsVal}" /></td>
        </tr>`;
      }).join("");
      tbody.querySelectorAll("input").forEach((inp) =>
        inp.addEventListener("input", () => {
          scheduleResearchPreview();
          scheduleResearchStrategiesReload();
        })
      );
      tbody.querySelectorAll("input[type=checkbox]").forEach((inp) =>
        inp.addEventListener("change", () => {
          scheduleResearchPreview();
          scheduleResearchStrategiesReload();
        })
      );
    }

    const rb = /** @type {HTMLInputElement|null} */ (document.getElementById("researchBars"));
    const ra = /** @type {HTMLInputElement|null} */ (document.getElementById("researchAtrSl"));
    const rm = /** @type {HTMLInputElement|null} */ (document.getElementById("researchMaxBars"));
    if (rb) rb.value = String(API_BARS);
    if (ra) ra.value = String(API_ATR_SL);
    if (rm) rm.value = String(API_MAX_BARS_RR);

    [
      "researchAtrSl",
      "researchMaxBars",
      "researchHistRange",
      "researchDateStart",
      "researchDateEnd",
      "researchConfidence",
    ].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", scheduleResearchPreview);
    });
    document.getElementById("researchBars")?.addEventListener("input", () => {
      scheduleResearchPreview();
      scheduleResearchStrategiesReload();
    });
    regSel?.dispatchEvent(new Event("change"));
    ["researchOptVolume", "researchOptInstitutional", "researchOptEquity"].forEach((id) => {
      document.getElementById(id)?.addEventListener("change", scheduleResearchPreview);
    });

    document.getElementById("researchConfidence")?.addEventListener("input", (ev) => {
      const t = /** @type {HTMLInputElement} */ (ev.target);
      t.dataset.touched = "1";
    });

    document.getElementById("btnResearchLoadFlow")?.addEventListener("click", () => {
      const rsel = /** @type {HTMLSelectElement|null} */ (document.getElementById("researchRegimeSelect"));
      if (state.regimeId != null && rsel) {
        rsel.value = String(state.regimeId);
        rsel.dispatchEvent(new Event("change"));
      }
      syncResearchSymbolFromTopbar();
      scheduleResearchStrategiesReload();
    });

    document.getElementById("btnResearchRefreshStrategies")?.addEventListener("click", () => refreshResearchStrategiesFromApi());

    document.getElementById("btnResearchGenerate")?.addEventListener("click", async () => {
      const st = document.getElementById("researchGenStatus");
      const btn = /** @type {HTMLButtonElement|null} */ (document.getElementById("btnResearchGenerate"));
      if (location.protocol === "file:") {
        if (st) st.textContent = "Blocked: file://";
        return;
      }
      const full = buildResearchPayload();
      const profiles = RESEARCH_TF_CATALOG.map((row, i) => {
        const cb = /** @type {HTMLInputElement|null} */ (document.querySelector(`input[data-research-tf-use="${i}"]`));
        const barsInp = /** @type {HTMLInputElement|null} */ (document.querySelector(`input[data-research-tf-bars="${i}"]`));
        const bars = barsInp ? parseInt(barsInp.value, 10) || row.defaultBars : row.defaultBars;
        return { tf_minutes: row.tf_minutes, bars, label: row.label, enabled: !!(cb && cb.checked) };
      }).filter((x) => x.enabled);

      if (!profiles.length) {
        if (st) st.textContent = "Enable at least one timeframe.";
        return;
      }

      if (btn) btn.disabled = true;
      const detail = document.getElementById("researchProgressDetail");
      const done = new Set();
      const sym = getResearchSymbol();

      const probe = await probeDashboardApi();
      if (!probe.ok) {
        if (st) st.textContent = "API unreachable.";
        if (btn) btn.disabled = false;
        return;
      }

      stopLivePoll();
      if (liveStripTimer) {
        clearInterval(liveStripTimer);
        liveStripTimer = null;
      }

      try {
        setResearchProgressStep("mt5", done);
        if (detail) detail.textContent = "POST /api/report/warm (sequential per TF)…";
        const multiParts = [];
        for (let ti = 0; ti < profiles.length; ti++) {
          const pr = profiles[ti];
          if (st) st.textContent = "Warm " + (ti + 1) + "/" + profiles.length + " (" + pr.label + ")…";
          setResearchProgressStep("hist", done);
          const payload = researchPayloadForSingleTf(full, pr);
          const warm = await fetchReportWarmPost(payload);
          const sid = warm && warm.session_id;
          if (!sid) throw new Error("No session_id from warm");

          setResearchProgressStep("reg", done);
          setResearchProgressStep("strat", done);
          setResearchProgressStep("charts", done);
          if (detail) detail.textContent = "PDF chunks for " + pr.label + "… (session " + sid.slice(0, 8) + "…)";
          const pdfBytes = await runSessionPdfAllChunks(sid, (c, tot) => {
            if (detail) detail.textContent = pr.label + " · PDF " + c + "/" + tot;
          });
          multiParts.push(new Uint8Array(pdfBytes));
          done.add("hist");
          done.add("reg");
          done.add("strat");
          done.add("charts");
        }
        setResearchProgressStep("pdf", done);
        if (detail) detail.textContent = "Merging " + multiParts.length + " PDF volume(s)…";
        let finalBytes;
        if (multiParts.length === 1) {
          finalBytes = multiParts[0];
        } else {
          finalBytes = await mergePdfParts(multiParts);
        }
        const blob = new Blob([finalBytes], { type: "application/pdf" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `regime52_research_${sym}_${profiles.map((p) => p.label).join("_")}.pdf`;
        a.click();
        URL.revokeObjectURL(a.href);
        if (st) st.textContent = "Downloaded · " + new Date().toLocaleTimeString();
        done.add("pdf");
        setResearchProgressStep("", new Set(["mt5", "hist", "reg", "strat", "charts", "pdf"]));
        if (detail) detail.textContent = "Done. Session JSON: GET /api/report/session/<sid>/client-request";
      } catch (e) {
        const msg = e && e.message ? e.message : String(e);
        if (st) st.textContent = "Failed: " + msg.slice(0, 120);
        if (detail) detail.textContent = msg;
      } finally {
        if (liveStripTimer) clearInterval(liveStripTimer);
        liveStripTimer = setInterval(() => fetchLiveStrip(getActiveSymbol()), 10000);
        if (btn) btn.disabled = false;
      }
    });

    scheduleResearchPreview();
  }

  function practicalRenderRequestForm(host) {
    if (!host || host.dataset.practicalFormBuilt === "1") return;
    host.dataset.practicalFormBuilt = "1";
    /** @type {{ key: string, label: string, type: string, step?: string }[]} */
    const fields = [
      { key: "symbol", label: "symbol", type: "text" },
      { key: "tf_minutes", label: "tf_minutes", type: "number" },
      { key: "bars", label: "bars", type: "number" },
      { key: "atr_sl_mult", label: "atr_sl_mult", type: "number", step: "any" },
      { key: "max_bars", label: "max_bars", type: "number" },
      { key: "regime_id", label: "regime_id (1–52)", type: "number" },
      { key: "strategy_key", label: "strategy_key (or empty)", type: "text" },
    ];
    const grid = document.createElement("div");
    grid.className = "practical__req-grid";
    fields.forEach((f) => {
      const lab = document.createElement("label");
      lab.className = "practical__req-label";
      const code = document.createElement("code");
      code.textContent = f.label;
      const inp = document.createElement("input");
      inp.className = "practical__req-input practical__input";
      inp.id = `practicalReq_${f.key}`;
      inp.dataset.reqKey = f.key;
      inp.type = f.type;
      if (f.step) inp.step = f.step;
      inp.autocomplete = "off";
      lab.appendChild(code);
      lab.appendChild(inp);
      grid.appendChild(lab);
    });
    host.appendChild(grid);
  }

  /** @param {HTMLElement|null} host @param {any} o */
  function practicalApplyRequestToForm(host, o) {
    if (!host) return;
    const n = practicalNormalizeRequestObject(o);
    /** @param {string} key @param {string|number} val */
    const set = (key, val) => {
      const el = /** @type {HTMLInputElement|null} */ (host.querySelector(`[data-req-key="${key}"]`));
      if (el) el.value = val === null || val === undefined ? "" : String(val);
    };
    set("symbol", n.symbol);
    set("tf_minutes", n.tf_minutes);
    set("bars", n.bars);
    set("atr_sl_mult", n.atr_sl_mult);
    set("max_bars", n.max_bars);
    set("regime_id", n.regime_id);
    set("strategy_key", n.strategy_key);
  }

  /** @returns {Record<string, any>} */
  function practicalReadRequestFromForm(host) {
    if (!host) {
      return practicalDefaultRequestObj();
    }
    const get = (key) => {
      const el = /** @type {HTMLInputElement|null} */ (host.querySelector(`[data-req-key="${key}"]`));
      return el ? el.value : "";
    };
    const ridRaw = get("regime_id").trim();
    let regime_id;
    if (ridRaw === "") regime_id = undefined;
    else {
      const r = parseInt(ridRaw, 10);
      regime_id = Number.isFinite(r) ? r : undefined;
    }
    return {
      symbol: get("symbol"),
      tf_minutes: get("tf_minutes"),
      bars: get("bars"),
      atr_sl_mult: get("atr_sl_mult"),
      max_bars: get("max_bars"),
      regime_id,
      strategy_key: get("strategy_key"),
    };
  }

  /** Keep request object to the seven GET fields with sane defaults. */
  function practicalNormalizeRequestObject(o) {
    const d = practicalDefaultRequestObj();
    const src = o && typeof o === "object" && !Array.isArray(o) ? o : {};
    const sym =
      src.symbol != null && String(src.symbol).trim() !== "" ? String(src.symbol).trim() : String(d.symbol || "EURUSD");
    const num = (x, fallback) => {
      const v = Number(x);
      return Number.isFinite(v) ? v : fallback;
    };
    let regime_id = d.regime_id;
    if (src.regime_id === "" || src.regime_id === undefined) {
      regime_id = d.regime_id;
    } else if (src.regime_id === null) {
      regime_id = d.regime_id;
    } else {
      const r = parseInt(String(src.regime_id), 10);
      regime_id = Number.isFinite(r) ? Math.min(52, Math.max(1, r)) : d.regime_id;
    }
    return {
      symbol: sym,
      tf_minutes: num(src.tf_minutes, d.tf_minutes),
      bars: num(src.bars, d.bars),
      atr_sl_mult: num(src.atr_sl_mult, d.atr_sl_mult),
      max_bars: num(src.max_bars, d.max_bars),
      regime_id,
      strategy_key: src.strategy_key != null ? String(src.strategy_key) : "",
    };
  }

  /** @param {Record<string, any>} reqNormalized */
  function practicalRefreshRequestEnvelope(reqNormalized) {
    const el = document.getElementById("practicalRequestEnvelope");
    if (!el) return;
    const url = practicalBuildSnapshotUrl(reqNormalized);
    const q = {
      symbol: reqNormalized.symbol,
      tf_minutes: reqNormalized.tf_minutes,
      bars: reqNormalized.bars,
      atr_sl_mult: reqNormalized.atr_sl_mult,
      max_bars: reqNormalized.max_bars,
      regime_id: reqNormalized.regime_id,
      strategy_key: reqNormalized.strategy_key === "" ? "" : reqNormalized.strategy_key,
    };
    const inUrl = {};
    try {
      const u = new URL(url);
      u.searchParams.forEach((v, k) => {
        inUrl[k] = v;
      });
    } catch {
      /* */
    }
    const note =
      "strategy_key is sent on the query string; when it matches a row in regime_detail.strategies, the API returns a practical_focus snapshot (one strategy row, aligned selector scores, regime_counts for that id only).";
    el.textContent = JSON.stringify(
      {
        method: "GET",
        path: "/api/snapshot",
        note,
        query_all_fields: q,
        query_params_on_the_wire: inUrl,
        url,
      },
      null,
      2
    );
  }

  function practicalFirstStrategyKey(rid) {
    const rows = researchStrategiesFromBlueprint(rid);
    return rows[0] && rows[0].strategy_key ? rows[0].strategy_key : "";
  }

  function practicalStripNonApiRequestFields(o) {
    delete o.engine_reference;
    delete o.strategy;
    delete o.strategy_blueprint;
    delete o.snapshot_query;
    delete o.GET_envelope;
    return o;
  }

  /** Deep-clone one strategy row from snapshot JSON (authoritative MT5 pipeline fields only). */
  function practicalStrategyRowFromSnapshot(data, skVal) {
    const rd = data && data.regime_detail;
    if (!rd || !Array.isArray(rd.strategies) || !rd.strategies.length) return null;
    const sk = (skVal || "").trim();
    if (!sk) return null;
    const row = rd.strategies.find((s) => s.strategy_key === sk);
    return row ? JSON.parse(JSON.stringify(row)) : null;
  }

  /** @returns {number|null} */
  function practicalWrPct01(w) {
    const x = Number(w);
    return Number.isFinite(x) ? x * 100 : null;
  }

  function practicalDefaultRequestObj() {
    const sym = getActiveSymbol();
    const rid = 7;
    return {
      symbol: sym,
      tf_minutes: API_TF,
      bars: API_BARS,
      regime_id: rid,
      atr_sl_mult: API_ATR_SL,
      max_bars: API_MAX_BARS_RR,
      strategy_key: practicalFirstStrategyKey(rid),
    };
  }

  function practicalSyncJsonFromPickers(ta, sel, stratSel, formHost) {
    const o = practicalParseRequestTextarea();
    practicalStripNonApiRequestFields(o);
    o.regime_id = parseInt(sel.value, 10) || 7;
    o.strategy_key = stratSel.value || "";
    const n = practicalNormalizeRequestObject(o);
    ta.value = JSON.stringify(n, null, 2);
    practicalApplyRequestToForm(formHost, n);
    practicalRefreshRequestEnvelope(n);
  }

  function fillPracticalStrategySelect(stratSel, rid) {
    if (!stratSel) return;
    const r = parseInt(String(rid), 10) || 1;
    const rows = researchStrategiesFromBlueprint(r);
    stratSel.innerHTML = "";
    const o0 = document.createElement("option");
    o0.value = "";
    o0.textContent = "— None (first row in slice) —";
    stratSel.appendChild(o0);
    rows.forEach((row) => {
      const o = document.createElement("option");
      o.value = row.strategy_key;
      o.textContent = `${row.strategy_key} — ${row.strategy_title}`;
      stratSel.appendChild(o);
    });
  }

  function practicalPickStrategyValueForRegime(stratSel, rid, preferKey) {
    if (!stratSel) return;
    fillPracticalStrategySelect(stratSel, rid);
    const want = (preferKey || "").trim();
    if (want) {
      for (let i = 0; i < stratSel.options.length; i++) {
        if (stratSel.options[i].value === want) {
          stratSel.selectedIndex = i;
          return;
        }
      }
    }
    const first = stratSel.querySelector("option[value]:not([value=''])");
    stratSel.value = first ? first.value : "";
  }

  function practicalParseRequestTextarea() {
    const ta = /** @type {HTMLTextAreaElement|null} */ (document.getElementById("practicalRequestJson"));
    if (!ta) throw new Error("Missing request editor");
    const o = JSON.parse(ta.value.trim());
    if (!o || typeof o !== "object" || Array.isArray(o)) throw new Error("Request must be a JSON object");
    return o;
  }

  function practicalBuildSnapshotUrl(req) {
    const u = new URL(`${API_BASE}/api/snapshot`);
    u.searchParams.set("symbol", String(req.symbol || "EURUSD"));
    u.searchParams.set("tf_minutes", String(Number(req.tf_minutes) || 60));
    u.searchParams.set("bars", String(Number(req.bars) || 8000));
    u.searchParams.set("atr_sl_mult", String(Number(req.atr_sl_mult) || 1.5));
    u.searchParams.set("max_bars", String(Number(req.max_bars) || 40));
    const rid = req.regime_id;
    if (rid != null && rid !== "" && Number.isFinite(Number(rid)) && Number(rid) > 0) {
      u.searchParams.set("regime_id", String(Number(rid)));
    }
    const sk = req.strategy_key != null ? String(req.strategy_key).trim() : "";
    if (sk) {
      u.searchParams.set("strategy_key", sk);
    }
    return u.toString();
  }

  function practicalStrategyKeyFromReq(req) {
    const k = req.strategy_key;
    if (k != null && String(k).trim() !== "") return String(k).trim();
    const st = req.strategy;
    if (st && typeof st === "object" && st.strategy_key != null && String(st.strategy_key).trim() !== "") {
      return String(st.strategy_key).trim();
    }
    return "";
  }

  function initPracticalPanel() {
    const ta = /** @type {HTMLTextAreaElement|null} */ (document.getElementById("practicalRequestJson"));
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("practicalRegimeSelect"));
    const stratSel = /** @type {HTMLSelectElement|null} */ (document.getElementById("practicalStrategySelect"));
    const baseEl = document.getElementById("practicalApiBase");
    const urlEl = document.getElementById("practicalFullUrl");
    const lineEl = document.getElementById("practicalResponseLine");
    const bodyEl = document.getElementById("practicalResponseBody");
    const normEl = document.getElementById("practicalResponseNormalized");
    const sliceEl = document.getElementById("practicalStrategySlice");
    const st = document.getElementById("practicalSendStatus");
    const btnSend = /** @type {HTMLButtonElement|null} */ (document.getElementById("btnPracticalSend"));
    const formHost = document.getElementById("practicalRequestFormHost");

    if (!ta || !sel || !stratSel) return;

    if (baseEl) baseEl.textContent = API_BASE;

    practicalRenderRequestForm(formHost);

    for (let id = 1; id <= 52; id++) {
      const opt = document.createElement("option");
      opt.value = String(id);
      opt.textContent = `#${String(id).padStart(2, "0")} ${REGIME_NAMES[id] || "Regime"}`;
      sel.appendChild(opt);
    }
    sel.value = "7";

    function refreshUrlPreview() {
      try {
        const o = practicalParseRequestTextarea();
        practicalStripNonApiRequestFields(o);
        const n = practicalNormalizeRequestObject(o);
        const url = practicalBuildSnapshotUrl(n);
        if (urlEl) urlEl.textContent = url;
        practicalRefreshRequestEnvelope(n);
      } catch {
        if (urlEl) urlEl.textContent = "(fix JSON to preview URL)";
      }
    }

    ta.value = JSON.stringify(practicalDefaultRequestObj(), null, 2);
    practicalPickStrategyValueForRegime(stratSel, 7, practicalFirstStrategyKey(7));
    practicalSyncJsonFromPickers(ta, sel, stratSel, formHost);
    refreshUrlPreview();

    ta.addEventListener("input", refreshUrlPreview);

    ta.addEventListener("blur", () => {
      try {
        const o = practicalParseRequestTextarea();
        practicalStripNonApiRequestFields(o);
        const r = Math.max(1, Math.min(52, parseInt(String(o.regime_id), 10) || 7));
        sel.value = String(r);
        practicalPickStrategyValueForRegime(stratSel, r, String(o.strategy_key || ""));
        const n = practicalNormalizeRequestObject({
          ...o,
          regime_id: r,
          strategy_key: stratSel.value,
        });
        ta.value = JSON.stringify(n, null, 2);
        practicalApplyRequestToForm(formHost, n);
        refreshUrlPreview();
      } catch {
        /* invalid JSON — skip */
      }
    });

    formHost?.addEventListener("input", () => {
      try {
        const raw = practicalReadRequestFromForm(formHost);
        const n = practicalNormalizeRequestObject(raw);
        ta.value = JSON.stringify(n, null, 2);
        if (urlEl) urlEl.textContent = practicalBuildSnapshotUrl(n);
        practicalRefreshRequestEnvelope(n);
      } catch {
        /* */
      }
    });

    formHost?.addEventListener("change", () => {
      try {
        const raw = practicalReadRequestFromForm(formHost);
        let n = practicalNormalizeRequestObject(raw);
        const r = n.regime_id;
        if (Number.isFinite(r) && r >= 1 && r <= 52) {
          sel.value = String(r);
          practicalPickStrategyValueForRegime(stratSel, r, n.strategy_key);
          n = practicalNormalizeRequestObject({
            ...n,
            regime_id: parseInt(sel.value, 10) || 7,
            strategy_key: stratSel.value,
          });
          ta.value = JSON.stringify(n, null, 2);
          practicalApplyRequestToForm(formHost, n);
        }
        refreshUrlPreview();
      } catch {
        /* */
      }
    });

    document.getElementById("btnPracticalSyncPickers")?.addEventListener("click", () => {
      try {
        practicalSyncJsonFromPickers(ta, sel, stratSel, formHost);
        refreshUrlPreview();
      } catch (e) {
        const msg = e && e.message ? e.message : String(e);
        if (st) st.textContent = "JSON: " + msg;
      }
    });

    sel.addEventListener("change", () => {
      try {
        let prevKey = "";
        try {
          prevKey = String(practicalParseRequestTextarea().strategy_key || "").trim();
        } catch {
          /* */
        }
        const rid = parseInt(sel.value, 10) || 7;
        practicalPickStrategyValueForRegime(stratSel, rid, prevKey);
        practicalSyncJsonFromPickers(ta, sel, stratSel, formHost);
        refreshUrlPreview();
      } catch {
        /* ignore */
      }
    });

    stratSel.addEventListener("change", () => {
      try {
        practicalSyncJsonFromPickers(ta, sel, stratSel, formHost);
        refreshUrlPreview();
      } catch {
        /* ignore */
      }
    });

    document.getElementById("btnPracticalSyncSymbol")?.addEventListener("click", () => {
      try {
        const o = practicalParseRequestTextarea();
        practicalStripNonApiRequestFields(o);
        o.symbol = getActiveSymbol();
        const n = practicalNormalizeRequestObject(o);
        ta.value = JSON.stringify(n, null, 2);
        practicalApplyRequestToForm(formHost, n);
        refreshUrlPreview();
      } catch {
        /* ignore */
      }
    });

    btnSend?.addEventListener("click", async () => {
      let req;
      try {
        req = practicalParseRequestTextarea();
      } catch (e) {
        const msg = e && e.message ? e.message : String(e);
        if (st) st.textContent = "JSON error: " + msg;
        return;
      }
      practicalStripNonApiRequestFields(req);
      req.regime_id = parseInt(sel.value, 10) || 7;
      req.strategy_key = stratSel.value;
      const reqNorm = practicalNormalizeRequestObject(req);
      ta.value = JSON.stringify(reqNorm, null, 2);
      practicalApplyRequestToForm(formHost, reqNorm);
      const url = practicalBuildSnapshotUrl(reqNorm);
      if (urlEl) urlEl.textContent = url;
      if (st) st.textContent = "Sending…";
      btnSend.disabled = true;
      const t0 = performance.now();
      try {
        if (location.protocol === "file:") {
          throw new Error("Open dashboard via http://127.0.0.1:8765 (or your static server) — file:// blocks API fetch");
        }
        /** @type {any} */
        let prevSnapshot = null;
        try {
          const rawPrev = sessionStorage.getItem(PRACTICAL_PREV_SNAPSHOT_KEY);
          if (rawPrev) prevSnapshot = JSON.parse(rawPrev);
        } catch {
          prevSnapshot = null;
        }
        const res = await fetch(url, { signal: AbortSignal.timeout(120000) });
        const elapsed = Math.round(performance.now() - t0);
        const text = await res.text();
        let data;
        try {
          data = JSON.parse(text);
        } catch {
          data = { _parse_error: "response was not JSON", _raw_excerpt: text.slice(0, 4000) };
        }
        if (lineEl) {
          lineEl.textContent = `${res.status} ${res.statusText} · ${elapsed} ms · ${text.length} B`;
        }
        if (bodyEl) bodyEl.textContent = JSON.stringify(data, null, 2);
        if (normEl) normEl.textContent = JSON.stringify(practicalFocusedPayload(data, practicalStrategyKeyFromReq(reqNorm)), null, 2);

        const skVal = practicalStrategyKeyFromReq(reqNorm);
        let row = null;
        if (data && data.regime_detail && Array.isArray(data.regime_detail.strategies)) {
          if (skVal) row = data.regime_detail.strategies.find((s) => s.strategy_key === skVal) || null;
          if (!row && data.regime_detail.strategies.length) row = data.regime_detail.strategies[0];
        }
        if (sliceEl) {
          sliceEl.textContent = row ? JSON.stringify(row, null, 2) : "—";
        }
        renderPracticalVisuals(data, skVal, prevSnapshot);
        try {
          if (res.ok && data && typeof data === "object" && !data._parse_error) {
            sessionStorage.setItem(PRACTICAL_PREV_SNAPSHOT_KEY, JSON.stringify(data));
          }
        } catch {
          /* quota or privacy mode */
        }
        const reqOut = { ...reqNorm };
        practicalStripNonApiRequestFields(reqOut);
        reqOut.regime_id = parseInt(sel.value, 10) || 7;
        reqOut.strategy_key = stratSel.value;
        const apiStrat = practicalStrategyRowFromSnapshot(data, skVal);
        if (apiStrat) reqOut.strategy = apiStrat;
        else delete reqOut.strategy;
        const reqOutNorm = practicalNormalizeRequestObject(reqOut);
        ta.value = JSON.stringify(reqOutNorm, null, 2);
        practicalApplyRequestToForm(formHost, reqOutNorm);
        practicalRefreshRequestEnvelope(reqOutNorm);
        if (st) st.textContent = res.ok ? "Done" : "HTTP " + res.status;
      } catch (e) {
        const msg = e && e.message ? e.message : String(e);
        if (lineEl) lineEl.textContent = "Request failed";
        if (bodyEl) bodyEl.textContent = msg;
        if (normEl) normEl.textContent = "—";
        if (sliceEl) sliceEl.textContent = "—";
        destroyPracticalCharts();
        const pv = document.getElementById("practicalViz");
        if (pv) pv.hidden = true;
        if (st) st.textContent = "Failed";
      } finally {
        btnSend.disabled = false;
      }
    });

    const pollChk = /** @type {HTMLInputElement|null} */ (document.getElementById("practicalLivePoll"));
    pollChk?.addEventListener("change", () => {
      const route = document.getElementById("routePractical");
      if (!route || route.hidden) {
        stopPracticalPoll();
        return;
      }
      if (pollChk.checked) startPracticalPoll();
      else stopPracticalPoll();
    });
  }

  const PRACTICAL_POLL_MS = 10000;

  function stopPracticalPoll() {
    if (practicalPollTimer) {
      clearInterval(practicalPollTimer);
      practicalPollTimer = null;
    }
  }

  function syncPracticalPickersFromEngine() {
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("practicalRegimeSelect"));
    const stratSel = /** @type {HTMLSelectElement|null} */ (document.getElementById("practicalStrategySelect"));
    const ta = /** @type {HTMLTextAreaElement|null} */ (document.getElementById("practicalRequestJson"));
    const formHost = document.getElementById("practicalRequestFormHost");
    const urlEl = document.getElementById("practicalFullUrl");
    if (!sel || !stratSel || !ta || state.regimeId == null) return;
    const rid = state.regimeId;
    if (!Number.isFinite(rid) || rid < 1 || rid > 52) return;
    sel.value = String(rid);
    practicalPickStrategyValueForRegime(stratSel, rid, state.strategyId || "");
    try {
      practicalSyncJsonFromPickers(ta, sel, stratSel, formHost);
      const n = practicalNormalizeRequestObject(practicalParseRequestTextarea());
      if (urlEl) urlEl.textContent = practicalBuildSnapshotUrl(n);
      practicalRefreshRequestEnvelope(n);
    } catch {
      /* invalid JSON */
    }
  }

  async function practicalPollSnapshotOnce() {
    const route = document.getElementById("routePractical");
    if (!route || route.hidden || practicalPollInFlight) return;
    if (location.protocol === "file:") return;
    const pollPref = /** @type {HTMLInputElement|null} */ (document.getElementById("practicalLivePoll"));
    if (pollPref && !pollPref.checked) return;

    const ta = /** @type {HTMLTextAreaElement|null} */ (document.getElementById("practicalRequestJson"));
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("practicalRegimeSelect"));
    const stratSel = /** @type {HTMLSelectElement|null} */ (document.getElementById("practicalStrategySelect"));
    const formHost = document.getElementById("practicalRequestFormHost");
    const lineEl = document.getElementById("practicalResponseLine");
    const bodyEl = document.getElementById("practicalResponseBody");
    const normEl = document.getElementById("practicalResponseNormalized");
    const sliceEl = document.getElementById("practicalStrategySlice");
    const st = document.getElementById("practicalSendStatus");
    if (!ta || !sel || !stratSel) return;

    let req;
    try {
      req = practicalParseRequestTextarea();
    } catch {
      return;
    }
    practicalStripNonApiRequestFields(req);
    req.regime_id = parseInt(sel.value, 10) || 7;
    req.strategy_key = stratSel.value;
    const reqNorm = practicalNormalizeRequestObject(req);
    const url = practicalBuildSnapshotUrl(reqNorm);
    if (formHost) {
      ta.value = JSON.stringify(reqNorm, null, 2);
      practicalApplyRequestToForm(formHost, reqNorm);
    }

    practicalPollInFlight = true;
    try {
      let prevSnapshot = null;
      try {
        const rawPrev = sessionStorage.getItem(PRACTICAL_PREV_SNAPSHOT_KEY);
        if (rawPrev) prevSnapshot = JSON.parse(rawPrev);
      } catch {
        prevSnapshot = null;
      }
      const res = await fetch(url, { signal: AbortSignal.timeout(120000) });
      const text = await res.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch {
        data = { _parse_error: "response was not JSON", _raw_excerpt: text.slice(0, 4000) };
      }
      if (lineEl) {
        lineEl.textContent = `Live ${new Date().toLocaleTimeString()} · ${res.status} · ${text.length} B`;
      }
      if (bodyEl) bodyEl.textContent = JSON.stringify(data, null, 2);
      const skVal = practicalStrategyKeyFromReq(reqNorm);
      if (normEl) normEl.textContent = JSON.stringify(practicalFocusedPayload(data, skVal), null, 2);

      let row = null;
      if (data && data.regime_detail && Array.isArray(data.regime_detail.strategies)) {
        if (skVal) row = data.regime_detail.strategies.find((s) => s.strategy_key === skVal) || null;
        if (!row && data.regime_detail.strategies.length) row = data.regime_detail.strategies[0];
      }
      if (sliceEl) sliceEl.textContent = row ? JSON.stringify(row, null, 2) : "—";

      renderPracticalVisuals(data, skVal, prevSnapshot);
      try {
        if (res.ok && data && typeof data === "object" && !data._parse_error) {
          sessionStorage.setItem(PRACTICAL_PREV_SNAPSHOT_KEY, JSON.stringify(data));
        }
      } catch {
        /* */
      }
      if (st) st.textContent = res.ok ? "Live refresh · " + new Date().toLocaleTimeString() : "Live · HTTP " + res.status;
      if (data && typeof data === "object" && data.meta) updateLivePill(data);
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      if (lineEl) lineEl.textContent = "Live poll failed";
      if (st) st.textContent = "Live: " + msg.slice(0, 96);
    } finally {
      practicalPollInFlight = false;
    }
  }

  function startPracticalPoll() {
    stopPracticalPoll();
    const route = document.getElementById("routePractical");
    const chk = /** @type {HTMLInputElement|null} */ (document.getElementById("practicalLivePoll"));
    if (!route || route.hidden) return;
    if (chk && !chk.checked) return;
    practicalPollSnapshotOnce();
    practicalPollTimer = setInterval(() => practicalPollSnapshotOnce(), PRACTICAL_POLL_MS);
  }

  function initRouteNav() {
    const title = document.getElementById("pageTitle");
    const engine = document.getElementById("routeEngine");
    const practical = document.getElementById("routePractical");
    document.querySelectorAll(".sidebar__nav .nav-item[data-route]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled || btn.classList.contains("nav-item--disabled")) return;
        const route = btn.dataset.route || "engine";
        document.querySelectorAll(".sidebar__nav .nav-item[data-route]").forEach((b) => {
          b.classList.toggle("nav-item--active", b === btn);
        });
        if (engine) {
          engine.hidden = route !== "engine";
          engine.classList.toggle("route-view--active", route === "engine");
        }
        if (practical) {
          practical.hidden = route !== "practical";
          practical.classList.toggle("route-view--active", route === "practical");
        }
        if (title) title.textContent = route === "practical" ? "Practical regime" : "Regime Engine";
        if (route === "practical") {
          syncPracticalPickersFromEngine();
          startPracticalPoll();
        } else {
          stopPracticalPoll();
        }
      });
    });
  }

  function init() {
    showSectionsInitial();
    $("#menuToggle")?.addEventListener("click", () => openSidebar(true));
    $("#sidebarClose")?.addEventListener("click", () => openSidebar(false));
    $("#overlay")?.addEventListener("click", () => openSidebar(false));

    document.querySelectorAll(".quad-card").forEach((btn) => {
      btn.addEventListener("click", () => onQuadrantPick(btn.dataset.quadrant));
    });
    $("#btnExecute")?.addEventListener("click", () => {
      postExecute();
    });
    $("#btnAnalysis")?.addEventListener("click", () => {
      runAnalysis();
    });

    const symbolSelect = /** @type {HTMLSelectElement|null} */ (document.getElementById("symbolSelect"));
    const symbolCustom = /** @type {HTMLInputElement|null} */ (document.getElementById("symbolCustom"));
    if (symbolSelect) {
      const preset = new Set(
        Array.from(symbolSelect.options)
          .map((o) => o.value)
          .filter((v) => v && v !== "__custom__")
      );
      if (preset.has(API_SYMBOL)) {
        symbolSelect.value = API_SYMBOL;
      } else {
        symbolSelect.value = "__custom__";
        if (symbolCustom) {
          symbolCustom.hidden = false;
          symbolCustom.value = API_SYMBOL;
        }
      }
      symbolSelect.addEventListener("change", () => {
        if (!symbolCustom || !symbolSelect) return;
        if (symbolSelect.value === "__custom__") {
          symbolCustom.hidden = false;
          symbolCustom.focus();
        } else {
          symbolCustom.hidden = true;
          symbolCustom.value = "";
          API_SYMBOL = symbolSelect.value;
          fetchLiveStrip(API_SYMBOL);
        }
        if (!researchSymbolSync) syncResearchSymbolFromTopbar();
        scheduleResearchPreview();
        scheduleResearchStrategiesReload();
      });
      symbolCustom?.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
          ev.preventDefault();
          API_SYMBOL = getActiveSymbol();
          fetchLiveStrip(API_SYMBOL);
          if (!researchSymbolSync) syncResearchSymbolFromTopbar();
          scheduleResearchPreview();
          scheduleResearchStrategiesReload();
        }
      });
      symbolCustom?.addEventListener("blur", () => {
        if (symbolSelect.value === "__custom__") {
          API_SYMBOL = getActiveSymbol();
          fetchLiveStrip(API_SYMBOL);
          if (!researchSymbolSync) syncResearchSymbolFromTopbar();
          scheduleResearchPreview();
          scheduleResearchStrategiesReload();
        }
      });
    }

    $("#btnPdfReport")?.addEventListener("click", async () => {
      const sym = getActiveSymbol();
      API_SYMBOL = sym;
      const st = $("#pdfStatus");
      const btn = /** @type {HTMLButtonElement|null} */ (document.getElementById("btnPdfReport"));
      if (btn) btn.disabled = true;
      setPdfDiagnostics("info", "PDF export — quick report", [
        "Symbol: " + sym + "  ·  timeframe: " + API_TF + "m  ·  bars: " + API_BARS,
        "",
        "Flow: POST " + API_BASE + "/api/generate-pdf  →  MT5 snapshot  →  ReportLab PDF  →  one download.",
        "No session queue, no 53 PDF chunks, no browser merge.",
      ]);
      if (location.protocol === "file:") {
        if (st) st.textContent = "Blocked: file://";
        setPdfDiagnostics("err", "Wrong way to open the dashboard", [
          "The page is loaded as file:// — most browsers block calls to http://127.0.0.1:8766 from there.",
          "",
          "Fix:",
          "  • Open dashboard-lite and run:  .\\run.ps1",
          "  • In the browser use:  http://127.0.0.1:8765/",
        ]);
        if (btn) btn.disabled = false;
        return;
      }
      if (st) st.textContent = "Checking API…";
      setPdfDiagnostics("info", "Step 1 — API reachability", [
        "Request: GET " + API_BASE + "/api/health",
        "Then: POST /api/generate-pdf with { symbol, tf_minutes, bars }.",
      ]);
      const probe = await probeDashboardApi();
      if (!probe.ok) {
        if (st) st.textContent = "Failed · see panel below";
        const lines = [
          "What went wrong:  " + probe.detail,
          "",
          "Checklist:",
          ...getApiUnreachableLines(),
        ];
        if (/\b404\b/.test(probe.detail)) {
          lines.push("", "• HTTP 404: this API build has no /api/health — pull latest code and restart server.py.");
        }
        setPdfDiagnostics("err", "Cannot reach the dashboard API", lines);
        if (btn) btn.disabled = false;
        return;
      }
      if (st) st.textContent = "Generating PDF…";
      setPdfDiagnostics("info", "Step 2 — generate PDF", [
        "POST " + API_BASE + "/api/generate-pdf",
        "MT5 runs once for the snapshot; PDF bytes return in the response body.",
      ]);
      try {
        const res = await fetch(API_BASE + "/api/generate-pdf", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol: sym,
            tf_minutes: API_TF,
            bars: API_BARS,
          }),
        });
        const ct = (res.headers.get("Content-Type") || "").toLowerCase();
        if (!res.ok) {
          const errTxt = await res.text();
          let msg = res.status + " " + res.statusText;
          try {
            const j = JSON.parse(errTxt);
            if (j && j.error) msg += ": " + j.error;
          } catch {
            if (errTxt) msg += " — " + errTxt.slice(0, 200);
          }
          throw new Error(msg);
        }
        if (!ct.includes("pdf")) {
          const errTxt = await res.text();
          throw new Error("Expected application/pdf, got " + (ct || "(empty)") + " — " + errTxt.slice(0, 120));
        }
        const blob = await res.blob();
        const cd = res.headers.get("Content-Disposition") || "";
        let fname = "QUANT_REPORT_" + sym + "_" + API_TF + "m.pdf";
        const m = /filename=\"?([^\";]+)\"?/i.exec(cd);
        if (m) fname = m[1].trim();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = fname;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(a.href);
        if (st) st.textContent = "Downloaded · " + new Date().toLocaleTimeString();
        setPdfDiagnostics("ok", "PDF download triggered", [
          "Filename: " + fname,
          "",
          "Full 52-regime institutional chart PDF is still available via Research flow + chunked merge if you need it.",
        ]);
      } catch (e) {
        const msg = e && e.message ? e.message : String(e);
        if (st) st.textContent = "Failed · see panel below";
        setPdfDiagnostics("err", "PDF generation failed", [
          "What went wrong:  " + msg,
          "",
          "Check MT5, symbol in Market Watch, and the server terminal for tracebacks.",
        ]);
      } finally {
        if (btn) btn.disabled = false;
      }
    });

    initResearchPanel();

    initPracticalPanel();
    initRouteNav();

    setPdfDiagnostics("clear");
    fetchLiveStrip(getActiveSymbol());
    if (liveStripTimer) clearInterval(liveStripTimer);
    liveStripTimer = setInterval(() => fetchLiveStrip(getActiveSymbol()), 10000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
