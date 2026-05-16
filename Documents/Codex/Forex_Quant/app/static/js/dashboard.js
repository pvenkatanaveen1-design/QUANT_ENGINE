/**
 * Quant Cockpit dashboard — /api/dashboard/* + /api/regimes/* for chart.
 */
(function () {
  "use strict";

  const DashboardState = {
    definitions: null,
    lastRegime: null,
    ranking: [],
    expandedCache: {},
    regimeChart: null,
    equityChart: null
  };

  function $(id) {
    return document.getElementById(id);
  }

  function showError(msg) {
    const el = $("dashboard-error");
    if (!el) return;
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  function clearError() {
    const el = $("dashboard-error");
    if (el) el.classList.add("hidden");
  }

  function showInfo(msg) {
    const el = $("dashboard-info");
    if (!el) return;
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  function clearInfo() {
    const el = $("dashboard-info");
    if (el) el.classList.add("hidden");
  }

  function qs() {
    const symbol = $("symbolSelect")?.value || "EURUSD";
    const timeframe = $("tfSelect")?.value || "M15";
    const investment = $("investmentInput")?.value || "10000";
    return {
      symbol: symbol.toUpperCase(),
      timeframe: timeframe.toUpperCase(),
      investment: Number(investment)
    };
  }

  async function fetchEnvelope(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    const body = await res.json();
    if (!body.ok) {
      const det = (body.errors && body.errors[0] && body.errors[0].detail) || body.message || "request failed";
      throw new Error(det);
    }
    return body.data;
  }

  async function fetchDashboard(path) {
    const { symbol, timeframe, investment } = qs();
    const u = new URL(path, window.location.origin);
    u.searchParams.set("symbol", symbol);
    u.searchParams.set("timeframe", timeframe);
    if (path.includes("/ranking")) u.searchParams.set("investment", String(investment));
    const res = await fetch(u, { credentials: "same-origin" });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(t || res.statusText);
    }
    return res.json();
  }

  function formatMoney(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    const n = Number(v);
    const sign = n < 0 ? "-" : "";
    return `${sign}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }

  /** win_rate from API may be 0–1 or already percent for legacy rows */
  function formatPctFraction(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    const n = Number(v);
    const frac = n > 1 ? n / 100 : n;
    return `${(frac * 100).toFixed(1)}%`;
  }

  function formatNumber(v, digits) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    return Number(v).toFixed(digits);
  }

  function regimeHumanTitle(regime, defs) {
    if (!regime) return "";
    const b = defs?.base_regimes?.[regime.base_regime]?.name || regime.base_regime;
    const m = defs?.modifiers?.[regime.modifier]?.name || regime.modifier;
    return `${b} — ${m}`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderReferenceThresholdsPanel() {
    const el = $("referenceThresholdsDynamic");
    if (!el) return;
    const d = DashboardState.definitions;
    const th = d && d.thresholds;
    if (!th || typeof th !== "object") {
      el.textContent = "";
      el.classList.add("hidden");
      return;
    }
    const rows = Object.entries(th)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}: ${v}`)
      .join("\n");
    el.textContent = `Live threshold block from config (regimes.yaml):\n\n${rows}`;
    el.classList.remove("hidden");
  }

  async function loadDefinitions() {
    if (!DashboardState.definitions) {
      try {
        DashboardState.definitions = await fetchEnvelope("/api/regimes/definitions");
      } catch (e) {
        console.warn("definitions", e);
        DashboardState.definitions = { base_regimes: {}, modifiers: {} };
      }
    }
    renderReferenceThresholdsPanel();
  }

  async function populateControls() {
    const symSel = $("symbolSelect");
    const tfSel = $("tfSelect");
    if (!symSel || !tfSel) return;

    symSel.innerHTML = "";
    tfSel.innerHTML = "";

    const tfs = [
      { key: "M1", minutes: 1 },
      { key: "M5", minutes: 5 },
      { key: "M15", minutes: 15 },
      { key: "M30", minutes: 30 },
      { key: "H1", minutes: 60 },
      { key: "H4", minutes: 240 },
      { key: "D1", minutes: 1440 }
    ];

    try {
      const data = await fetchEnvelope("/api/regimes/options");
      const rawList = data?.symbols?.symbols || [];
      const keys = new Set();
      for (const item of rawList) {
        const name = item.symbol || item.name || item.path || item.keyword;
        if (name) keys.add(String(name).toUpperCase());
      }
      const list = keys.size ? Array.from(keys).sort() : ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US30"];
      for (const s of list) {
        const o = document.createElement("option");
        o.value = s;
        o.textContent = s;
        symSel.appendChild(o);
      }
      const tfRaw = Array.isArray(data?.timeframes) ? data.timeframes : [];
      if (Array.isArray(tfRaw) && tfRaw.length) {
        tfSel.innerHTML = "";
        for (const tf of tfRaw) {
          const k = tf.key || tf.name || tf;
          if (!k) continue;
          const o = document.createElement("option");
          o.value = String(k).toUpperCase();
          o.textContent = tf.label || String(k).toUpperCase();
          tfSel.appendChild(o);
        }
      }
    } catch {
      const o = document.createElement("option");
      o.value = "EURUSD";
      o.textContent = "EURUSD";
      symSel.appendChild(o);
    }

    if (!tfSel.options.length) {
      for (const tf of tfs) {
        const o = document.createElement("option");
        o.value = tf.key;
        o.textContent = tf.key;
        tfSel.appendChild(o);
      }
    }

    symSel.value = "EURUSD";
    tfSel.value = "M15";
  }

  function pctRangeLabel(low, high) {
    if (low == null && high == null) return "—";
    const fmt = (v) => {
      if (v == null) return "—";
      const n = Number(v);
      if (Number.isNaN(n)) return "—";
      return (n > 1 ? n : n * 100).toFixed(0);
    };
    return `${fmt(low)}–${fmt(high)}`;
  }

  function renderStrategyCards(strategies) {
    const cards = (strategies || []).map((s) => {
      const slot = (s.slot || "").toUpperCase();
      const id = escapeHtml(s.id || "");
      const name = escapeHtml(s.name || "");
      const fam = escapeHtml(s.family || "");
      const sig = escapeHtml(s.signal_fn || "");
      const wrBand = pctRangeLabel(s.win_rate_low, s.win_rate_high);
      const rrr = s.rrr != null ? Number(s.rrr).toFixed(1) : "—";
      const ev = s.ev != null ? Number(s.ev).toFixed(2) : "—";
      const desc = escapeHtml((s.description || "").slice(0, 220) || "—");
      const notes = escapeHtml((s.notes || "").slice(0, 200) || "—");
      return `
        <div class="rounded-lg border border-zinc-200 bg-zinc-50/80 p-3 shadow-sm">
          <div class="mb-1 inline-block rounded bg-zinc-800 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">${slot || "SLOT"}</div>
          <h4 class="mt-1 text-sm font-semibold text-zinc-900">${id} — ${name}</h4>
          <p class="mt-1 text-xs text-zinc-600">Family: ${fam} | Signal: ${sig}</p>
          <p class="mt-1 text-xs text-zinc-600">Expected WR: ${wrBand}% | RRR: ${rrr} | EV: ${ev}R</p>
          <p class="mt-1 text-xs leading-snug text-zinc-500">Conditions: <span class="text-zinc-700">${desc}</span></p>
          <p class="mt-1 text-xs text-zinc-500">Invalidation / notes: ${notes}</p>
        </div>`;
    });
    return `<div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">${cards.join("")}</div>`;
  }

  async function fetchCurrentRegime() {
    await loadDefinitions();
    const { symbol, timeframe } = qs();
    const u = new URL("/api/dashboard/current-regime", window.location.origin);
    u.searchParams.set("symbol", symbol);
    u.searchParams.set("timeframe", timeframe);
    u.searchParams.set("bars", "500");
    const data = await fetch(u, { credentials: "same-origin" }).then((r) => {
      if (!r.ok) throw new Error(r.statusText);
      return r.json();
    });
    DashboardState.lastRegime = data;
    const el = $("liveRegimeBanner");
    if (!el) return;

    const regime = data.regime || {};
    const mv = data.market_values || {};
    const defs = DashboardState.definitions || {};
    const title = regimeHumanTitle(regime, defs);
    const confRaw = Number(regime.confidence);
    const confPct = confRaw <= 1 ? confRaw * 100 : confRaw;
    const tradable = regime.tradable ? "YES" : "NO";
    const ex = mv.extra || {};
    const kz = ex.kill_zone_active ? "YES" : "NO";

    el.innerHTML = `
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <span class="inline-block rounded bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-900">Regime: ${escapeHtml(regime.regime_id || "—")}</span>
          <h2 class="mt-2 text-lg font-semibold text-zinc-900">${escapeHtml(title)}</h2>
          <p class="mt-1 text-sm text-zinc-600">Confidence: ${formatNumber(confPct, 1)}% | Tradable: ${tradable} | Risk posture: ${escapeHtml(regime.risk_posture || "—")}</p>
        </div>
        <div class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs text-zinc-700 md:grid-cols-4">
          <div>ATR: ${formatNumber(mv.atr, 5)} (${formatPctFraction(mv.atr_percent)})</div>
          <div>ADX: ${formatNumber(mv.adx, 2)}</div>
          <div>Eff.Ratio: ${formatNumber(mv.efficiency_ratio, 3)}</div>
          <div>Vol %ile: ${formatNumber(mv.volatility_percentile, 0)}</div>
          <div>Spread %ile: ${formatNumber(mv.spread_percentile, 0)}</div>
          <div>Kill Zone: ${kz}</div>
          <div>Sweep High: ${mv.sweep_high ? "YES" : "NO"}</div>
          <div>Sweep Low: ${mv.sweep_low ? "YES" : "NO"}</div>
        </div>
      </div>
      <div class="mt-6 border-t border-zinc-100 pt-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-zinc-800">Active strategies</h3>
          <button type="button" id="btnCopyPlaybook" class="rounded border border-zinc-300 bg-white px-2 py-1 text-xs font-medium text-zinc-800 hover:bg-zinc-50">Copy playbook JSON</button>
        </div>
        <div class="mt-3">${renderStrategyCards(data.strategies)}</div>
      </div>`;

    $("btnCopyPlaybook")?.addEventListener("click", copyPlaybookJSON);
  }

  function copyPlaybookJSON() {
    const { symbol, timeframe, investment } = qs();
    const payload = {
      generated_at: new Date().toISOString(),
      symbol,
      timeframe,
      investment,
      regime: DashboardState.lastRegime?.regime,
      market_values: DashboardState.lastRegime?.market_values,
      strategies: DashboardState.lastRegime?.strategies,
      definitions: DashboardState.definitions,
    };
    const text = JSON.stringify(payload, null, 2);
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(() => showInfo("Playbook JSON copied to clipboard.")).catch(() => window.prompt("Copy:", text));
    } else {
      window.prompt("Copy:", text);
    }
    setTimeout(clearInfo, 3000);
  }

  function removeExpandedRow(rid) {
    const next = document.querySelector(`tr.expanded-detail[data-parent-regime="${CSS.escape(rid)}"]`);
    if (next) next.remove();
  }

  function isExpanded(rid) {
    return !!document.querySelector(`tr.expanded-detail[data-parent-regime="${CSS.escape(rid)}"]`);
  }

  async function ensureSummary(rid) {
    if (DashboardState.expandedCache[rid]) return DashboardState.expandedCache[rid];
    const { symbol, timeframe } = qs();
    const u = new URL(`/api/dashboard/backtest-summary/${encodeURIComponent(rid)}`, window.location.origin);
    u.searchParams.set("symbol", symbol);
    u.searchParams.set("timeframe", timeframe);
    const data = await fetch(u, { credentials: "same-origin" }).then((r) => {
      if (!r.ok) throw new Error(r.statusText);
      return r.json();
    });
    DashboardState.expandedCache[rid] = data;
    return data;
  }

  function slotLabel(slot) {
    return (slot || "").replace(/^./, (c) => c.toUpperCase());
  }

  function buildInnerTable(rid, summary) {
    const slots = ["primary", "secondary", "confirmation", "fallback"];
    const rows = [];
    for (const slot of slots) {
      const block = summary[slot];
      if (!block || typeof block !== "object") continue;
      const sid = escapeHtml(block.strategy_id || "—");
      const net = formatMoney(block.net_profit);
      const wr = formatPctFraction(block.win_rate);
      const pf = block.profit_factor != null ? formatNumber(block.profit_factor, 2) : "—";
      const tr = block.total_trades != null ? String(block.total_trades) : "—";
      const kz = formatPctFraction(block.kill_zone_win_rate);
      const inst = block.institutional_trap_failures != null ? String(block.institutional_trap_failures) : "—";
      rows.push(`
        <tr class="border-b border-zinc-100">
          <td class="px-2 py-2">${slotLabel(slot)}</td>
          <td class="px-2 py-2 font-mono text-xs">${sid}</td>
          <td class="px-2 py-2">${net}</td>
          <td class="px-2 py-2">${wr}</td>
          <td class="px-2 py-2">${pf}</td>
          <td class="px-2 py-2">${tr}</td>
          <td class="px-2 py-2">${kz}</td>
          <td class="px-2 py-2">${inst}</td>
          <td class="px-2 py-2 text-xs">
            <button type="button" class="text-sky-700 underline hover:text-sky-900" data-action="trades" data-regime="${escapeHtml(rid)}" data-slot="${slot}">Trades</button>
            <span class="text-zinc-300">|</span>
            <button type="button" class="text-sky-700 underline hover:text-sky-900" data-action="equity" data-regime="${escapeHtml(rid)}" data-slot="${slot}">Equity</button>
          </td>
        </tr>`);
    }
    return `
      <table class="w-full min-w-[720px] border-collapse text-xs">
        <thead class="bg-zinc-100 text-zinc-700">
          <tr>
            <th class="border border-zinc-200 px-2 py-1 text-left">Slot</th>
            <th class="border border-zinc-200 px-2 py-1 text-left">Strategy</th>
            <th class="border border-zinc-200 px-2 py-1 text-left">Net Profit</th>
            <th class="border border-zinc-200 px-2 py-1 text-left">WR</th>
            <th class="border border-zinc-200 px-2 py-1 text-left">PF</th>
            <th class="border border-zinc-200 px-2 py-1 text-left">Trades</th>
            <th class="border border-zinc-200 px-2 py-1 text-left">KZ WR</th>
            <th class="border border-zinc-200 px-2 py-1 text-left">Inst. fails</th>
            <th class="border border-zinc-200 px-2 py-1 text-left">Details</th>
          </tr>
        </thead>
        <tbody>${rows.join("")}</tbody>
      </table>`;
  }

  async function toggleExpandRow(rid, anchorTr) {
    if (isExpanded(rid)) {
      removeExpandedRow(rid);
      return;
    }
    removeExpandedRow(rid);
    document.querySelectorAll("tr.expanded-detail").forEach((tr) => tr.remove());
    const summary = await ensureSummary(rid);
    const detail = document.createElement("tr");
    detail.className = "expanded-detail bg-zinc-50";
    detail.dataset.parentRegime = rid;
    detail.innerHTML = `<td colspan="12" class="border-b border-zinc-200 p-4">${buildInnerTable(rid, summary)}</td>`;
    anchorTr.insertAdjacentElement("afterend", detail);
    detail.querySelectorAll("button[data-action]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const r = btn.getAttribute("data-regime");
        const s = btn.getAttribute("data-slot");
        if (!r || !s) return;
        if (btn.getAttribute("data-action") === "trades") await showTradeList(r, s);
        else showEquityCurve(r, s);
      });
    });
  }

  function tradeRowClass(t) {
    const trap = t.trap_score != null ? Number(t.trap_score) : null;
    const sweepDir = (t.liquidity_sweep_direction || "").toLowerCase();
    const badTrap = trap != null && trap < 60;
    const badSweep = sweepDir && sweepDir !== "none" && Number(t.pnl) < 0;
    const highSpr = t.spread_percentile != null && Number(t.spread_percentile) > 80;
    if (badTrap || badSweep || highSpr) return "bg-amber-50";
    return "";
  }

  async function showTradeList(regimeId, slot) {
    destroyEquityChart();
    const summary = await ensureSummary(regimeId);
    const block = summary[slot];
    const trades = Array.isArray(block?.trades) ? block.trades : [];
    const modal = $("tradeModal");
    const body = $("tradeModalBody");
    const title = $("tradeModalTitle");
    if (!modal || !body || !title) return;
    title.textContent = `${regimeId} · ${slot} — ${trades.length} trades`;
    body.innerHTML = trades
      .map((t, i) => {
        const cls = tradeRowClass(t);
        const trap = t.trap_score != null ? String(t.trap_score) : "—";
        const note = [t.reason, t.liquidity_sweep_direction, t.signal_template].filter(Boolean).join(" · ");
        return `<tr class="${cls}">
        <td class="border border-zinc-200 px-2 py-1">${i + 1}</td>
        <td class="border border-zinc-200 px-2 py-1">${escapeHtml(t.time || "")}</td>
        <td class="border border-zinc-200 px-2 py-1">${escapeHtml(t.side || "")}</td>
        <td class="border border-zinc-200 px-2 py-1 text-right">${t.r != null ? formatNumber(t.r, 2) : "—"}</td>
        <td class="border border-zinc-200 px-2 py-1 text-right">${t.pnl != null ? formatMoney(t.pnl) : "—"}</td>
        <td class="border border-zinc-200 px-2 py-1">${escapeHtml(trap)}</td>
        <td class="border border-zinc-200 px-2 py-1">${escapeHtml(note)}</td>
      </tr>`;
      })
      .join("");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  }

  function closeTradeModal() {
    const modal = $("tradeModal");
    if (modal) {
      modal.classList.add("hidden");
      modal.classList.remove("flex");
    }
    destroyEquityChart();
  }

  function destroyEquityChart() {
    if (DashboardState.equityChart) {
      DashboardState.equityChart.destroy();
      DashboardState.equityChart = null;
    }
  }

  async function showEquityCurve(regimeId, slot) {
    const summary = await ensureSummary(regimeId);
    const block = summary[slot];
    const series = Array.isArray(block?.equity_curve) ? block.equity_curve : [];
    if (!series.length) {
      showInfo("No equity curve stored for this slot.");
      setTimeout(clearInfo, 2500);
      return;
    }
    destroyEquityChart();
    const modal = $("tradeModal");
    const body = $("tradeModalBody");
    const title = $("tradeModalTitle");
    if (!modal || !body || !title) return;
    title.textContent = `${regimeId} · ${slot} — equity curve`;
    body.innerHTML = '<canvas id="equityCurveCanvas" height="240"></canvas>';
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    const ctx = document.getElementById("equityCurveCanvas")?.getContext("2d");
    if (!ctx || typeof Chart === "undefined") return;
    const labels = series.map((_, i) => String(i + 1));
    const data = series.map((pt) => {
      if (pt.equity != null) return Number(pt.equity);
      if (pt.net_pl != null) return Number(pt.net_pl);
      return null;
    });
    DashboardState.equityChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Equity / net P/L",
            data,
            borderColor: "rgb(2, 132, 199)",
            tension: 0.15,
            spanGaps: true
          }
        ]
      },
      options: {
        responsive: true,
        scales: {
          x: { title: { display: true, text: "Step" } },
          y: { title: { display: true, text: "Value" } }
        },
        plugins: { legend: { display: false } }
      }
    });
  }

  async function fetchRanking() {
    const data = await fetchDashboard("/api/dashboard/ranking");
    DashboardState.ranking = Array.isArray(data) ? data : [];
    const tbody = $("rankingTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";
    for (const row of DashboardState.ranking) {
      const tr = document.createElement("tr");
      tr.className = "border-b border-zinc-100 hover:bg-zinc-50/80";
      tr.dataset.regimeId = row.regime_id;
      const statCls = row.status === "not_tested" ? "text-zinc-400" : "text-zinc-800";
      tr.innerHTML = `
        <td class="whitespace-nowrap px-3 py-2 font-mono text-xs font-medium ${statCls}">${escapeHtml(row.regime_id)}</td>
        <td class="whitespace-nowrap px-3 py-2 ${statCls}">${formatMoney(row.net_profit)}</td>
        <td class="whitespace-nowrap px-3 py-2 ${statCls}">${row.profit_factor != null ? formatNumber(row.profit_factor, 2) : "—"}</td>
        <td class="whitespace-nowrap px-3 py-2 ${statCls}">${formatPctFraction(row.win_rate)}</td>
        <td class="whitespace-nowrap px-3 py-2 ${statCls}">${row.total_trades != null ? row.total_trades : "—"}</td>
        <td class="whitespace-nowrap px-3 py-2 ${statCls}">${row.sharpe != null ? formatNumber(row.sharpe, 2) : "—"}</td>
        <td class="whitespace-nowrap px-3 py-2 ${statCls}">${row.max_drawdown != null ? formatNumber(row.max_drawdown, 2) : "—"}</td>
        <td class="whitespace-nowrap px-3 py-2 ${statCls}">${formatPctFraction(row.kill_zone_win_rate)}</td>
        <td class="whitespace-nowrap px-3 py-2 ${statCls}">${row.institutional_trap_failures != null ? row.institutional_trap_failures : "—"}</td>
        <td class="whitespace-nowrap px-3 py-2 ${statCls}">${row.sweep_failures != null ? row.sweep_failures : "—"}</td>
        <td class="whitespace-nowrap px-3 py-2 ${statCls}">${row.spread_rejections != null ? row.spread_rejections : "—"}</td>
        <td class="whitespace-nowrap px-3 py-2">
          <button type="button" class="mr-2 text-xs text-sky-700 underline hover:text-sky-900 btn-expand" data-regime="${escapeHtml(row.regime_id)}">Expand</button>
          <button type="button" class="text-xs text-amber-800 underline hover:text-amber-950 btn-rerun" data-regime="${escapeHtml(row.regime_id)}">Re-run</button>
        </td>`;
      tbody.appendChild(tr);

      tr.querySelector(".btn-expand")?.addEventListener("click", () => toggleExpandRow(row.regime_id, tr));
      tr.querySelector(".btn-rerun")?.addEventListener("click", () => runBacktestForRegime(row.regime_id));
    }
  }

  async function runBacktestForRegime(regimeId) {
    const { symbol, timeframe, investment } = qs();
    const u = new URL(`/api/dashboard/run-backtest/${encodeURIComponent(regimeId)}`, window.location.origin);
    u.searchParams.set("symbol", symbol);
    u.searchParams.set("timeframe", timeframe);
    u.searchParams.set("investment", String(investment));
    u.searchParams.set("bars", "17280");
    showInfo(`Running backtest for ${regimeId}…`);
    try {
      const res = await fetch(u, { method: "POST", credentials: "same-origin" });
      if (!res.ok) throw new Error(await res.text());
      await res.json();
      delete DashboardState.expandedCache[regimeId];
      await fetchRanking();
      showInfo(`Finished backtest for ${regimeId}.`);
      setTimeout(clearInfo, 4000);
    } catch (e) {
      showError(`Backtest failed: ${e.message || e}`);
    }
  }

  async function runMissingBacktests() {
    if (!confirm("Run POST /run-backtest for every regime with status not_tested? This may take a long time and uses MT5 data.")) return;
    await fetchRanking();
    const { investment } = qs();
    let n = 0;
    for (const row of DashboardState.ranking) {
      if (row.status !== "not_tested") continue;
      n += 1;
      showInfo(`Running missing (${n})… ${row.regime_id}`);
      const u = new URL(`/api/dashboard/run-backtest/${encodeURIComponent(row.regime_id)}`, window.location.origin);
      u.searchParams.set("symbol", qs().symbol);
      u.searchParams.set("timeframe", qs().timeframe);
      u.searchParams.set("investment", String(investment));
      u.searchParams.set("bars", "17280");
      try {
        const res = await fetch(u, { method: "POST", credentials: "same-origin" });
        if (!res.ok) console.warn(row.regime_id, await res.text());
        delete DashboardState.expandedCache[row.regime_id];
      } catch (e) {
        console.warn(e);
      }
    }
    await fetchRanking();
    clearInfo();
    showInfo(`Missing backtest sweep complete (${n} regimes attempted).`);
    setTimeout(clearInfo, 5000);
  }

  async function renderHistoryChart() {
    const canvas = $("regimeHistoryChart");
    const cap = $("historyChartCaption");
    if (!canvas || typeof Chart === "undefined") return;
    const days = Number($("historyDaysInput")?.value || 180);
    const { symbol, timeframe } = qs();
    const u = new URL("/api/regimes/scan", window.location.origin);
    u.searchParams.set("symbol", symbol);
    u.searchParams.set("timeframe", timeframe);
    u.searchParams.set("lookback_days", String(days));
    u.searchParams.set("bars", "0");

    let barsBy;
    try {
      const snap = await fetchEnvelope(u.pathname + u.search);
      barsBy = snap.bars_by_regime || {};
      if (cap) cap.textContent = `${symbol} ${timeframe} · ~${days}d window · ${snap.bars_analyzed || 0} bars`;
    } catch (e) {
      console.warn("history chart", e);
      barsBy = {};
      if (cap) cap.textContent = "Chart data unavailable";
    }

    const entries = Object.entries(barsBy).sort((a, b) => b[1] - a[1]).slice(0, 24);
    const labels = entries.map(([k]) => k);
    const values = entries.map(([, v]) => v);

    if (DashboardState.regimeChart) DashboardState.regimeChart.destroy();
    const ctx = canvas.getContext("2d");
    DashboardState.regimeChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Bars in regime",
            data: values,
            backgroundColor: "rgba(39, 39, 42, 0.75)"
          }
        ]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { maxRotation: 60, minRotation: 45, font: { size: 9 } } } }
      }
    });
  }

  async function refreshAll() {
    clearError();
    clearInfo();
    try {
      await loadDefinitions();
      await fetchCurrentRegime();
      await fetchRanking();
      await renderHistoryChart();
    } catch (e) {
      showError(String(e.message || e));
    }
  }

  async function initDashboard() {
    $("tradeModalClose")?.addEventListener("click", closeTradeModal);
    $("tradeModal")?.addEventListener("click", (ev) => {
      if (ev.target.id === "tradeModal") closeTradeModal();
    });

    $("btnRefresh")?.addEventListener("click", refreshAll);
    $("btnRunMissing")?.addEventListener("click", runMissingBacktests);
    $("symbolSelect")?.addEventListener("change", refreshAll);
    $("tfSelect")?.addEventListener("change", refreshAll);
    $("historyDaysInput")?.addEventListener("change", () => renderHistoryChart().catch(console.warn));

    await populateControls();
    await refreshAll();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initDashboard);
  else initDashboard();
})();
