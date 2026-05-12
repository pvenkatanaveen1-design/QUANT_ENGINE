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

  /** @type {{ strategy_key: string, strategy_title: string, signal_kind: string, side_rule: number, risk_pct: string, rr_ratio: string, atr_multiplier: string, position_size: string, enabled: boolean }[]} */
  let researchStrategiesDraft = [];

  let researchPreviewScheduled = false;
  let researchSymbolSync = false;

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
    /** @type {{ source: string, snapshot?: any, error?: string }|null} */
    lastPack: null,
  };

  /** @type {ReturnType<typeof setInterval>|null} */
  let livePollTimer = null;
  /** @type {ReturnType<typeof setInterval>|null} */
  let liveStripTimer = null;

  const PAGE = new URLSearchParams(location.search);
  const API_BASE = (PAGE.get("api") || "http://127.0.0.1:8766").replace(/\/$/, "");
  let API_SYMBOL = (PAGE.get("symbol") || "EURUSD").trim().toUpperCase() || "EURUSD";
  const API_TF = parseInt(PAGE.get("tf") || "60", 10);
  const API_BARS = parseInt(PAGE.get("bars") || "12000", 10);

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
      const risk = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=risk]"));
      const rr = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=rr]"));
      const atr = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=atr]"));
      const pos = /** @type {HTMLInputElement|null} */ (tr.querySelector("input[data-f=pos]"));
      out.push({
        strategy_key: sk,
        strategy_title: (title && title.value) || "",
        signal_kind: (sig && sig.value) || "",
        side_rule: side ? parseInt(side.value, 10) || 0 : 0,
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
        return Number.isFinite(v) ? v : 1.5;
      })(),
      max_bars: (() => {
        const el = /** @type {HTMLInputElement|null} */ (document.getElementById("researchMaxBars"));
        return el ? parseInt(el.value, 10) || 40 : 40;
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

  function renderResearchStrategyTbody() {
    const tbody = document.getElementById("researchStrategyTbody");
    if (!tbody) return;
    if (!researchStrategiesDraft.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="research__hint">No rows — pick a regime and refresh.</td></tr>';
      return;
    }
    tbody.innerHTML = researchStrategiesDraft
      .map(
        (s, i) => `
      <tr data-sk="${escHtml(s.strategy_key)}">
        <td><input type="checkbox" data-f="enabled" ${s.enabled ? "checked" : ""} /></td>
        <td><input type="text" data-f="title" value="${escAttr(s.strategy_title)}" /></td>
        <td><code>${escHtml(s.strategy_key)}</code></td>
        <td><input type="text" data-f="signal" value="${escAttr(s.signal_kind)}" /></td>
        <td><input type="number" data-f="side" value="${s.side_rule}" step="1" /></td>
        <td><input type="text" data-f="risk" value="${escAttr(s.risk_pct)}" placeholder="%" /></td>
        <td><input type="text" data-f="rr" value="${escAttr(s.rr_ratio)}" /></td>
        <td><input type="text" data-f="atr" value="${escAttr(s.atr_multiplier)}" /></td>
        <td><input type="text" data-f="pos" value="${escAttr(s.position_size)}" /></td>
      </tr>`
      )
      .join("");
    tbody.querySelectorAll("input").forEach((inp) => inp.addEventListener("input", scheduleResearchPreview));
    tbody.querySelectorAll("input[type=checkbox]").forEach((inp) => inp.addEventListener("change", scheduleResearchPreview));
  }

  async function refreshResearchStrategiesFromApi() {
    const hint = document.getElementById("researchStrategyHint");
    const selR = /** @type {HTMLSelectElement|null} */ (document.getElementById("researchRegimeSelect"));
    const rid = selR ? parseInt(selR.value, 10) || 1 : 1;
    const sym = getResearchSymbol();
    const p = buildResearchPayload();
    const tf0 = p.timeframes && p.timeframes[0];
    const tfm = tf0 ? tf0.tf_minutes : API_TF;
    const bars = tf0 ? tf0.bars : p.bars;
    if (hint) hint.textContent = "Loading snapshot…";
    try {
      const u = new URL(`${API_BASE}/api/snapshot`);
      u.searchParams.set("symbol", sym);
      u.searchParams.set("tf_minutes", String(tfm));
      u.searchParams.set("bars", String(bars));
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
        risk_pct: "",
        rr_ratio: "",
        atr_multiplier: "",
        position_size: "",
        enabled: true,
      }));
      const confEl = /** @type {HTMLInputElement|null} */ (document.getElementById("researchConfidence"));
      if (confEl && snap.confidence != null && !confEl.dataset.touched) confEl.value = String(snap.confidence);
      renderResearchStrategyTbody();
      if (hint) hint.textContent = "Loaded " + researchStrategiesDraft.length + " strategies from API for R" + String(rid).padStart(2, "0") + ".";
      scheduleResearchPreview();
    } catch (e) {
      researchStrategiesDraft = [];
      renderResearchStrategyTbody();
      if (hint) hint.textContent = "Could not load strategies: " + (e && e.message ? e.message : e);
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
      } else {
        rc.hidden = true;
        rc.value = "";
        applyTopbarSymbolFromResearch();
      }
      scheduleResearchPreview();
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
      regSel.value = String(state.regimeId != null ? state.regimeId : 7);
    }
    regSel?.addEventListener("change", () => {
      const rid = parseInt(regSel.value, 10) || 1;
      const nm = document.getElementById("researchRegimeName");
      const qu = document.getElementById("researchQuadrant");
      if (nm) nm.value = REGIME_NAMES[rid] || "";
      if (qu) qu.value = REGIME_TO_QUAD[rid] || "";
      scheduleResearchPreview();
    });
    regSel?.dispatchEvent(new Event("change"));

    const tbody = document.getElementById("researchTfTbody");
    if (tbody) {
      tbody.innerHTML = RESEARCH_TF_CATALOG.map((row, i) => {
        const on = row.tf_minutes === API_TF;
        return `<tr>
          <td><input type="checkbox" data-research-tf-use="${i}" ${on ? "checked" : ""} /></td>
          <td class="research__tf-label">${row.label}</td>
          <td>${row.tf_minutes}</td>
          <td><input type="number" data-research-tf-bars="${i}" min="100" step="100" value="${row.defaultBars}" /></td>
        </tr>`;
      }).join("");
      tbody.querySelectorAll("input").forEach((inp) => inp.addEventListener("input", scheduleResearchPreview));
      tbody.querySelectorAll("input[type=checkbox]").forEach((inp) => inp.addEventListener("change", scheduleResearchPreview));
    }

    const rb = /** @type {HTMLInputElement|null} */ (document.getElementById("researchBars"));
    const ra = /** @type {HTMLInputElement|null} */ (document.getElementById("researchAtrSl"));
    const rm = /** @type {HTMLInputElement|null} */ (document.getElementById("researchMaxBars"));
    if (rb) rb.value = String(API_BARS);
    if (ra) ra.value = "1.5";
    if (rm) rm.value = "40";

    [
      "researchBars",
      "researchAtrSl",
      "researchMaxBars",
      "researchHistRange",
      "researchDateStart",
      "researchDateEnd",
      "researchConfidence",
    ].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", scheduleResearchPreview);
    });
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
      refreshResearchStrategiesFromApi();
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

    refreshResearchStrategiesFromApi();
    scheduleResearchPreview();
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
      });
      symbolCustom?.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
          ev.preventDefault();
          API_SYMBOL = getActiveSymbol();
          fetchLiveStrip(API_SYMBOL);
          if (!researchSymbolSync) syncResearchSymbolFromTopbar();
          scheduleResearchPreview();
        }
      });
      symbolCustom?.addEventListener("blur", () => {
        if (symbolSelect.value === "__custom__") {
          API_SYMBOL = getActiveSymbol();
          fetchLiveStrip(API_SYMBOL);
          if (!researchSymbolSync) syncResearchSymbolFromTopbar();
          scheduleResearchPreview();
        }
      });
    }

    $("#btnPdfReport")?.addEventListener("click", async () => {
      const sym = getActiveSymbol();
      API_SYMBOL = sym;
      const st = $("#pdfStatus");
      const btn = /** @type {HTMLButtonElement|null} */ (document.getElementById("btnPdfReport"));
      if (btn) btn.disabled = true;
      setPdfDiagnostics("info", "PDF export — starting", [
        "Symbol: " + sym + "  ·  timeframe: " + API_TF + "m  ·  bars: " + API_BARS,
        "",
        "Flow: one MT5 warm → 53 small PDF chunks (cover + regimes 1..52) → merge in the browser.",
        "Per-regime JSON (same shape as dashboard regime_detail, 4 strategies):",
        "  GET " + API_BASE + "/api/report/session/<sid>/bundle/regime/7",
        "Multiple timeframes: each (symbol, tf, bars) needs its own warm (separate session_id).",
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
        "No MT5 yet — this only checks that Python server.py is running.",
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
      stopLivePoll();
      if (liveStripTimer) {
        clearInterval(liveStripTimer);
        liveStripTimer = null;
      }
      try {
      if (st) st.textContent = "Warming session (MT5)…";
      setPdfDiagnostics("info", "Step 2 — Warm (one MT5 + scorecard)", [
        "Request: GET " + API_BASE + "/api/report/warm?symbol=…&tf_minutes=…&bars=…",
        "Can take several minutes (same work as before, but no matplotlib yet).",
        "While warm runs, other MT5 API calls wait in line (by design — MT5 is not thread-safe).",
        "",
        "If this fails: check MT5, symbol in Market Watch, server.py terminal; restart API after update.",
      ]);
      let warm;
      try {
        warm = await fetchReportWarm(sym, API_TF, API_BARS);
      } catch (e) {
        const msg = e && e.message ? e.message : String(e);
        if (st) st.textContent = "Failed · see panel below";
        const hint =
          /failed to fetch|networkerror|load failed/i.test(msg)
            ? [
                "",
                "If MT5 looks fine in the UI: the API may have dropped the connection (often fixed by restarting server.py after the MT5-serialize patch).",
                "Also try a smaller ?bars=4000 and watch the Python terminal for tracebacks during warm.",
              ]
            : [];
        setPdfDiagnostics("err", "Warm request failed", [
          "What went wrong:  " + msg,
          "",
          "Typical causes: MT5 offline, symbol missing, Python crash during scorecard, or stale API process.",
          ...hint,
        ]);
        return;
      }
      const sid = warm && warm.session_id ? warm.session_id : "";
      if (!sid) {
        if (st) st.textContent = "Failed · no session_id";
        setPdfDiagnostics("err", "Unexpected warm response", ["No session_id in JSON.", JSON.stringify(warm).slice(0, 400)]);
        return;
      }

      const chunkTo = 180000;
      const partUrls = [API_BASE + "/api/report/session/" + sid + "/pdf/cover"];
      for (let r = 1; r <= 52; r++) partUrls.push(API_BASE + "/api/report/session/" + sid + "/pdf/regime/" + r);

      const parts = [];
      try {
        if (st) st.textContent = "PDF 0/53 (loading pdf-lib + cover)…";
        setPdfDiagnostics("info", "Step 3 — PDF chunks (small HTTP bodies)", [
          "Session: " + sid.slice(0, 8) + "…",
          "Each slice ~ short request — avoids one giant response that drops with “Failed to fetch”.",
          "",
          "Example JSON (regime + 4 strategies):",
          API_BASE + "/api/report/session/" + sid + "/bundle/regime/1",
        ]);
        await import("https://cdn.jsdelivr.net/npm/pdf-lib@1.17.1/+esm");

        for (let i = 0; i < partUrls.length; i++) {
          if (st) st.textContent = "PDF " + (i + 1) + "/53…";
          setPdfDiagnostics("info", "Step 3 — fetching chunk " + (i + 1) + "/53", [
            "GET " + partUrls[i],
            "Timeout per chunk: " + Math.round(chunkTo / 1000) + "s",
            "",
            "Troubleshooting: if a single chunk fails, read server.py traceback (matplotlib/MT5).",
            "Smaller sample: add ?bars=4000 to this page’s URL and retry.",
          ]);
          try {
            parts.push(await fetchPdfChunk(partUrls[i], chunkTo));
          } catch (chunkErr) {
            const cm = chunkErr && chunkErr.message ? chunkErr.message : String(chunkErr);
            throw new Error("Chunk " + (i + 1) + "/53 failed: " + cm + "\nURL: " + partUrls[i]);
          }
        }

        if (st) st.textContent = "Merging PDF…";
        setPdfDiagnostics("info", "Step 4 — merge in browser", ["Combining " + parts.length + " PDFs with pdf-lib…"]);
        const mergedBytes = await mergePdfParts(parts);
        const blob = new Blob([mergedBytes], { type: "application/pdf" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `regime52_${sym}_${API_TF}m.pdf`;
        a.click();
        URL.revokeObjectURL(a.href);
        if (st) st.textContent = "Downloaded · " + new Date().toLocaleTimeString();
        setPdfDiagnostics("ok", "PDF download triggered (chunked + merged)", [
          "If the file did not appear: check download bar / pop-up blocker.",
          "Expected filename:  regime52_" + sym + "_" + API_TF + "m.pdf",
          "",
          "Inspect raw regime payloads: GET …/bundle/regime/{1..52}",
        ]);
      } catch (e) {
        const msg = e && e.message ? e.message : String(e);
        if (st) st.textContent = "Failed · see panel below";
        const lines = [
          "What went wrong:  " + msg,
          "",
          "If a chunk failed mid-run: fix that regime or check VPN/proxy/antivirus.",
          "Fallback: old monolithic (one long HTTP) — GET /api/report/pdf?symbol=… (may still timeout).",
        ];
        if (/failed to fetch|networkerror|load failed/i.test(msg)) {
          lines.push("", "• CDN blocked? pdf-lib loads from jsdelivr; allow it or host pdf-lib locally.");
        }
        setPdfDiagnostics("err", "Chunked PDF did not finish", lines);
      }
      } finally {
        if (liveStripTimer) clearInterval(liveStripTimer);
        liveStripTimer = setInterval(() => fetchLiveStrip(getActiveSymbol()), 10000);
        if (btn) btn.disabled = false;
      }
    });

    initResearchPanel();

    setPdfDiagnostics("clear");
    fetchLiveStrip(getActiveSymbol());
    if (liveStripTimer) clearInterval(liveStripTimer);
    liveStripTimer = setInterval(() => fetchLiveStrip(getActiveSymbol()), 10000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
