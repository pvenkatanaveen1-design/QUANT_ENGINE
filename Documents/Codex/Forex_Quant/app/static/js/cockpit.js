/**
 * QUANTA FOREX - Cockpit Dashboard
 * Reads all trading data from backend APIs. Research priors are displayed only
 * as priors; performance is shown only when saved backtest data exists.
 */
(function () {
  const SLOTS = ["primary", "secondary", "confirmation", "fallback"];
  const state = {
    live: null,
    playbook: null,
    ranking: [],
    details: {},
    chart: null,
    running: false,
    currentRegime: null,
  };

  function el(id) {
    return document.getElementById(id);
  }

  function controls() {
    return {
      symbol: el("ctrlSymbol")?.value || "EURUSD",
      timeframe: el("ctrlTF")?.value || "M15",
      capital: Number(el("ctrlCapital")?.value || 10000),
      riskPct: Number(el("ctrlRisk")?.value || 1),
    };
  }

  function setStatus(message) {
    const bar = el("statusBar");
    if (bar) bar.textContent = message;
  }

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function fmt(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toFixed(digits);
  }

  function fmtPct(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return `${Number(value).toFixed(1)}%`;
  }

  function fmtUsd(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "Not tested";
    return `$${Number(value).toFixed(2)}`;
  }

  function fmtSignal(direction) {
    if (direction === "BUY") return "BUY";
    if (direction === "SELL") return "SELL";
    return "NONE";
  }

  function qs(params) {
    return new URLSearchParams(params).toString();
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || response.statusText);
    }
    return response.json();
  }

  async function copyText(text, title) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    openModal(title || "Copy JSON", `<pre class="max-h-[72vh] overflow-auto rounded border border-zinc-700 p-3 text-xs whitespace-pre-wrap">${esc(text)}</pre>`);
    return false;
  }

  function thresholds() {
    return state.live?.classification_thresholds || state.playbook?.classification_thresholds || {};
  }

  function statusClass(name) {
    if (name === "green") return "status-green";
    if (name === "blue") return "status-blue";
    if (name === "amber") return "status-amber";
    if (name === "red") return "status-red";
    return "status-gray";
  }

  function metricTone(kind, value) {
    const t = thresholds();
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "gray";
    const v = Number(value);
    if (kind === "adx") {
      if (t.adx_trend_min !== undefined && v >= Number(t.adx_trend_min)) return "green";
      if (t.adx_range_max !== undefined && v <= Number(t.adx_range_max)) return "blue";
      return "amber";
    }
    if (kind === "er") {
      if (t.efficiency_ratio_min !== undefined && v >= Number(t.efficiency_ratio_min)) return "green";
      if (t.efficiency_ratio_range_max !== undefined && v <= Number(t.efficiency_ratio_range_max)) return "blue";
      return "amber";
    }
    if (kind === "vol") {
      if (t.extreme_vol_percentile !== undefined && v >= Number(t.extreme_vol_percentile)) return "red";
      if (t.high_vol_percentile !== undefined && v >= Number(t.high_vol_percentile)) return "amber";
      return "gray";
    }
    if (kind === "spread") {
      if (t.spread_stress_percentile !== undefined && v >= Number(t.spread_stress_percentile)) return "red";
      return "gray";
    }
    if (kind === "jump") {
      if (t.jump_shock_z !== undefined && v >= Number(t.jump_shock_z)) return "red";
      if (t.jump_warning_z !== undefined && v >= Number(t.jump_warning_z)) return "amber";
      return "gray";
    }
    if (kind === "compression") {
      if (t.compression_percentile !== undefined && v <= Number(t.compression_percentile)) return "amber";
      return "gray";
    }
    return "gray";
  }

  function quadrantClass(regimeId) {
    const id = String(regimeId || "");
    if (id.startsWith("Q1")) return "status-green";
    if (id.startsWith("Q2")) return "status-amber";
    if (id.startsWith("Q3")) return "status-blue";
    return "status-red";
  }

  function rowShade(regimeId) {
    const id = String(regimeId || "");
    if (id.startsWith("Q1")) return "bg-emerald-950/20";
    if (id.startsWith("Q2")) return "bg-amber-950/20";
    if (id.startsWith("Q3")) return "bg-sky-950/20";
    return "bg-red-950/20";
  }

  function featureCell(label, value, tone) {
    return `<div class="viz-chip border ${statusClass(tone)}">
      <span>${esc(label)}</span>
      <strong>${esc(value)}</strong>
    </div>`;
  }

  function slotClass(slot) {
    if (slot === "primary") return "status-amber";
    if (slot === "secondary") return "status-blue";
    if (slot === "confirmation") return "status-green";
    return "status-gray";
  }

  function directionClass(direction) {
    if (direction === "BUY") return "status-green";
    if (direction === "SELL") return "status-red";
    return "status-gray";
  }

  function renderLiveBanner(data) {
    const banner = el("liveBanner");
    if (!banner) return;
    if (data.error) {
      banner.innerHTML = `<p class="label">Live regime</p><p class="mt-2 text-sm text-red-300">${esc(data.error)}</p>`;
      return;
    }

    const regime = data.regime || {};
    const market = data.market_values || {};
    const strategies = data.strategies || {};
    const risk = data.risk_parameters || {};
    const confidencePct = Math.max(0, Math.min(100, Math.round(Number(regime.confidence || 0) * 100)));
    const confidenceTone = confidencePct >= 70 ? "bg-emerald-500" : confidencePct >= 50 ? "bg-amber-500" : "bg-red-500";
    state.currentRegime = regime.regime_id || null;

    const sweepText = [market.sweep_high ? "Sweep high" : "", market.sweep_low ? "Sweep low" : ""].filter(Boolean).join(" / ");
    const strategyCards = SLOTS.map((slot) => {
      const item = strategies[slot] || {};
      const direction = item.signal_direction || "NONE";
      const hasSignal = direction !== "NONE";
      return `<div class="rounded border border-zinc-700 bg-zinc-950 p-3">
        <div class="flex items-start justify-between gap-2">
          <div>
            <span class="status-pill ${slotClass(slot)}">${esc(slot)}</span>
            <div class="mt-2 text-sm font-semibold">${esc(item.strategy_id || "-")}</div>
            <div class="mt-1 text-xs text-zinc-500">${esc(item.name || "")}</div>
          </div>
          <span class="status-pill ${directionClass(direction)}">${fmtSignal(direction)}</span>
        </div>
        ${hasSignal ? `<div class="mt-3 grid grid-cols-2 gap-2 text-xs">
          ${featureCell("Entry", fmt(item.entry_price, 5), "gray")}
          ${featureCell("Stop", fmt(item.stop_price, 5), "gray")}
          ${featureCell("Target", fmt(item.tp_price, 5), "gray")}
          ${featureCell("RR", item.rr_ratio === null || item.rr_ratio === undefined ? "-" : `1:${fmt(item.rr_ratio, 2)}`, "gray")}
        </div>` : `<p class="mt-3 text-xs text-zinc-500">No signal on current bar.</p>`}
        <p class="mt-3 text-xs text-zinc-500">${esc(item.reason || "")}</p>
        <div class="mt-3 flex items-center justify-between gap-2 text-xs">
          <span class="text-zinc-500">Conf: ${fmt(Number(item.confidence || 0) * 100, 0)}%</span>
          <button class="status-pill status-gray" type="button" onclick="cockpit.copyStrategyJSON('${slot}')">Copy JSON</button>
        </div>
      </div>`;
    }).join("");

    banner.innerHTML = `<div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <p class="label">Live MT5 regime</p>
        <div class="mt-1 flex flex-wrap items-center gap-2">
          <h2 class="text-3xl font-semibold">${esc(regime.regime_id || "Unavailable")}</h2>
          <span class="status-pill ${quadrantClass(regime.regime_id)}">${esc(regime.base_regime || "-")}</span>
          <span class="status-pill ${regime.tradable ? "status-green" : "status-red"}">${regime.tradable ? "Tradable research" : "No trade / blocked"}</span>
          <span class="status-pill ${market.kill_zone_active ? "status-amber" : "status-gray"}">${market.kill_zone_active ? "Kill zone active" : "No kill zone"}</span>
          ${sweepText ? `<span class="status-pill status-blue">${esc(sweepText)}</span>` : ""}
        </div>
        <p class="mt-2 max-w-4xl text-sm text-zinc-500">${esc((data.regime_definition || {}).description || "")}</p>
        <p class="mt-1 text-xs text-zinc-500">${esc(regime.risk_posture || "")} | Size ${fmt((data.regime_definition || {}).size_multiplier, 2)}x | Risk ${fmtUsd(risk.effective_risk_usd)}</p>
      </div>
      <div class="min-w-48">
        <p class="label text-right">Confidence</p>
        <div class="mt-2 flex items-center gap-2">
          <div class="h-3 flex-1 overflow-hidden rounded-full bg-zinc-800">
            <div class="${confidenceTone} h-3 rounded-full" style="width:${confidencePct}%"></div>
          </div>
          <span class="text-sm font-semibold">${confidencePct}%</span>
        </div>
        <p class="mt-2 text-right text-xs text-zinc-500">${esc(data.symbol)} ${esc(data.timeframe)} | Capital ${fmtUsd(risk.initial_capital)}</p>
      </div>
    </div>

    <div class="mt-4 rounded border border-zinc-700 bg-zinc-950 p-3 text-xs text-zinc-500">
      <span class="font-semibold text-zinc-300">Why this regime:</span>
      <ul class="mt-1 list-disc pl-5">${(regime.reasons || []).map((reason) => `<li>${esc(reason)}</li>`).join("") || "<li>No classifier reasons returned.</li>"}</ul>
    </div>

    <div class="mt-4 grid gap-2 md:grid-cols-4 xl:grid-cols-9">
      ${featureCell("ADX", fmt(market.adx, 2), metricTone("adx", market.adx))}
      ${featureCell("ER", fmt(market.efficiency_ratio, 3), metricTone("er", market.efficiency_ratio))}
      ${featureCell("ATR", fmt(market.atr, 6), "gray")}
      ${featureCell("ATR%", fmt(Number(market.atr_percent || 0) * 100, 4) + "%", "gray")}
      ${featureCell("Vol pct", fmtPct(market.volatility_pctile), metricTone("vol", market.volatility_pctile))}
      ${featureCell("Spread pct", fmtPct(market.spread_pctile), metricTone("spread", market.spread_pctile))}
      ${featureCell("Compression", fmtPct(market.compression_pctile), metricTone("compression", market.compression_pctile))}
      ${featureCell("Jump Z", fmt(market.jump_z, 3), metricTone("jump", market.jump_z))}
      ${featureCell("Session", market.session_label || "-", "gray")}
    </div>

    <div class="mt-4 grid gap-3 xl:grid-cols-4">${strategyCards}</div>`;
  }

  function renderReferencePanel(data) {
    const panel = el("referencePanel");
    if (!panel) return;
    const t = data?.classification_thresholds || thresholds();
    const risk = data?.risk_parameters || state.live?.risk_parameters || {};
    const sourceRows = (data?.research_sources || state.playbook?.research_sources || []).slice(0, 8);
    const thresholdRows = [
      ["ADX trend min", "adx_trend_min", "Wilder ADX trend filter"],
      ["ADX range max", "adx_range_max", "Wilder ADX range filter"],
      ["ER trend min", "efficiency_ratio_min", "Kaufman efficiency ratio"],
      ["ER range max", "efficiency_ratio_range_max", "Kaufman efficiency ratio"],
      ["High vol pctile", "high_vol_percentile", "ATR percentile"],
      ["Extreme vol pctile", "extreme_vol_percentile", "ATR percentile"],
      ["Spread stress pctile", "spread_stress_percentile", "Cost guard"],
      ["Compression pctile", "compression_percentile", "Squeeze condition"],
    ];

    panel.innerHTML = `<div class="xl:col-span-2">
      <p class="label">Regime thresholds from config/regimes.yaml</p>
      <table class="table-compact mt-2">
        <tbody>${thresholdRows.map(([label, key, note]) => `<tr>
          <td>${esc(label)}</td>
          <td class="text-right font-mono">${esc(t[key] ?? "-")}</td>
          <td class="text-zinc-500">${esc(note)}</td>
        </tr>`).join("")}</tbody>
      </table>
    </div>
    <div>
      <p class="label">Key formulas</p>
      <div class="mt-2 space-y-2 rounded border border-zinc-700 bg-zinc-950 p-3 text-xs text-zinc-400">
        <div>ADX = Wilder-smoothed DX from DI+ and DI-.</div>
        <div>ER = abs(close[n] - close[0]) / sum(abs(delta close)).</div>
        <div>Vol pctile = rank(ATR%) in rolling lookback.</div>
        <div>EV(R) = win_rate * RRR - loss_rate.</div>
        <div>Sharpe = mean(R) / std(R) * sqrt(252).</div>
        <div>Risk$ = equity * risk% * regime size multiplier.</div>
      </div>
    </div>
    <div>
      <p class="label">Risk values and references</p>
      <div class="mt-2 grid gap-2">
        ${featureCell("Capital", fmtUsd(risk.initial_capital), "gray")}
        ${featureCell("Risk/trade", fmtPct(risk.risk_per_trade_pct), "gray")}
        ${featureCell("Effective risk", fmtUsd(risk.effective_risk_usd), "gray")}
      </div>
      <div class="mt-3 grid gap-2">${sourceRows.map((source) => `<div class="rounded border border-zinc-700 bg-zinc-950 p-2 text-xs">
        <div class="font-semibold text-zinc-200">${esc(source.label || source.key)}</div>
        <div class="mt-1 text-zinc-500">${esc(source.note || source.finding || "")}</div>
      </div>`).join("") || "<p class='text-xs text-zinc-500'>No source metadata returned.</p>"}</div>
    </div>`;
  }

  function rankingStatus(row) {
    if (row.tested && row.validated) return "validated";
    if (row.tested) return "tested";
    if (!row.tradable) return "blocked prior";
    return "prior only";
  }

  function rankingStatusClass(row) {
    if (row.tested && row.validated) return "status-green";
    if (row.tested) return "status-blue";
    if (!row.tradable) return "status-red";
    return "status-amber";
  }

  function expectedWrLabel(row) {
    const range = row.expected_wr_range || [];
    if (range.length < 2) return "-";
    return `${fmt(Number(range[0]) * 100, 0)}-${fmt(Number(range[1]) * 100, 0)}% prior`;
  }

  function renderRanking(rows) {
    const body = el("rankingBody");
    if (!body) return;
    if (!Array.isArray(rows) || !rows.length) {
      body.innerHTML = `<tr><td colspan="15" class="py-8 text-center text-zinc-500">No ranking rows returned.</td></tr>`;
      return;
    }

    body.innerHTML = rows.map((row, index) => {
      const isCurrent = row.regime_id === state.currentRegime;
      const profit = row.net_profit_usd === null || row.net_profit_usd === undefined
        ? `<span class="text-zinc-500">EV ${fmt(row.expected_ev_r, 2)}R prior</span>`
        : `<span class="${Number(row.net_profit_usd) >= 0 ? "text-emerald-300" : "text-red-300"} font-semibold">${fmtUsd(row.net_profit_usd)}</span>`;
      const winRate = row.win_rate_pct === null || row.win_rate_pct === undefined
        ? `<span class="text-zinc-500">${expectedWrLabel(row)}</span>`
        : `<span class="${Number(row.win_rate_pct) >= 60 ? "text-emerald-300" : Number(row.win_rate_pct) >= 50 ? "text-amber-300" : "text-red-300"} font-semibold">${fmtPct(row.win_rate_pct)}</span>`;

      return `<tr class="${rowShade(row.regime_id)}">
        <td>${index + 1}</td>
        <td><span class="status-pill ${quadrantClass(row.regime_id)}">${esc(row.regime_id)}</span>${isCurrent ? "<span class='ml-1 status-pill status-amber'>live</span>" : ""}</td>
        <td class="min-w-64">${esc(row.description || "")}<div class="mt-1 text-xs text-zinc-500">${esc(row.validation_note || "")}</div></td>
        <td class="text-right">${profit}</td>
        <td class="text-right">${winRate}</td>
        <td class="text-right">${fmt(row.profit_factor, 2)}</td>
        <td class="text-right">${esc(row.total_trades || 0)}</td>
        <td class="text-right">${fmt(row.sharpe, 2)}</td>
        <td class="text-right">${row.max_drawdown_pct === null || row.max_drawdown_pct === undefined ? "-" : `${fmt(row.max_drawdown_pct, 2)}%`}</td>
        <td class="text-right">${fmtPct(row.kill_zone_win_rate_pct)}</td>
        <td class="text-right">${esc(row.institutional_trap_failures || 0)}</td>
        <td class="text-right">${esc(row.sweep_failures || 0)}</td>
        <td class="text-right">${esc(row.spread_rejections || 0)}</td>
        <td><span class="status-pill ${rankingStatusClass(row)}">${rankingStatus(row)}</span></td>
        <td>
          <div class="flex flex-wrap gap-1">
            <button class="status-pill status-blue" type="button" onclick="cockpit.toggleDetail('${esc(row.regime_id)}')">Detail</button>
            <button class="status-pill status-amber" type="button" onclick="cockpit.runBacktest('${esc(row.regime_id)}')">Backtest</button>
            ${row.run_id ? `<button class="status-pill status-gray" type="button" onclick="cockpit.showTrades('${esc(row.run_id)}','${esc(row.regime_id)}')">Trades</button>` : ""}
          </div>
        </td>
      </tr>
      <tr id="detail-${esc(row.regime_id)}" class="hidden">
        <td colspan="15" class="bg-zinc-950/70 p-4">
          <div id="detail-content-${esc(row.regime_id)}" class="text-sm text-zinc-500">Loading strategy details...</div>
        </td>
      </tr>`;
    }).join("");
  }

  async function refreshAll() {
    const c = controls();
    setStatus("Refreshing MT5 cockpit state...");
    try {
      const queryLive = qs({ symbol: c.symbol, timeframe: c.timeframe, capital: String(c.capital) });
      const queryRank = qs({ symbol: c.symbol, timeframe: c.timeframe });
      const [live, playbook, ranking] = await Promise.all([
        fetchJson(`/cockpit/api/live-state?${queryLive}`),
        fetchJson(`/cockpit/api/playbook-json?${queryLive}`),
        fetchJson(`/cockpit/api/ranking?${queryRank}`),
      ]);
      state.live = live;
      state.playbook = playbook;
      state.ranking = ranking;
      renderLiveBanner(live);
      renderReferencePanel(playbook);
      renderRanking(ranking);
      setStatus(`Updated ${new Date().toLocaleTimeString()}`);
    } catch (error) {
      setStatus(`Error: ${String(error.message || error).slice(0, 160)}`);
    }
  }

  async function loadLiveBanner() {
    const c = controls();
    const query = qs({ symbol: c.symbol, timeframe: c.timeframe, capital: String(c.capital) });
    const [live, playbook] = await Promise.all([
      fetchJson(`/cockpit/api/live-state?${query}`),
      fetchJson(`/cockpit/api/playbook-json?${query}`),
    ]);
    state.live = live;
    state.playbook = playbook;
    renderLiveBanner(live);
    renderReferencePanel(playbook);
  }

  async function loadRanking() {
    const c = controls();
    const rows = await fetchJson(`/cockpit/api/ranking?${qs({ symbol: c.symbol, timeframe: c.timeframe })}`);
    state.ranking = rows;
    renderRanking(rows);
  }

  function renderStrategyDetail(regimeId, detail, container) {
    state.details[regimeId] = detail;
    const slotHtml = SLOTS.map((slot) => {
      const item = detail[slot] || {};
      const tested = Boolean(item.tested);
      const filters = (item.filters || []).map((value) => `<li>${esc(value)}</li>`).join("");
      const invalidations = (item.invalidations || []).map((value) => `<li>${esc(value)}</li>`).join("");
      const evidence = (item.evidence || []).map((value) => `<span class="status-pill status-gray">${esc(value)}</span>`).join("");
      return `<div class="rounded border border-zinc-700 bg-zinc-900 p-4">
        <div class="flex items-start justify-between gap-2">
          <div>
            <span class="status-pill ${slotClass(slot)}">${esc(slot)}</span>
            <div class="mt-2 text-xs font-mono text-zinc-500">${esc(item.strategy_id || "")}</div>
            <div class="mt-1 text-sm font-semibold">${esc(item.name || "")}</div>
          </div>
          <span class="status-pill ${tested ? "status-blue" : "status-amber"}">${tested ? "tested" : "not tested"}</span>
        </div>
        ${tested ? `<table class="table-compact mt-3">
          <tbody>
            <tr><td>Trades</td><td class="text-right font-semibold">${esc(item.total_trades || 0)} (${esc(item.wins || 0)}W/${esc(item.losses || 0)}L)</td></tr>
            <tr><td>Win rate</td><td class="text-right">${fmtPct(item.win_rate_pct)}</td></tr>
            <tr><td>Profit factor</td><td class="text-right">${fmt(item.profit_factor, 2)}</td></tr>
            <tr><td>Net profit</td><td class="text-right">${fmtUsd(item.net_profit_usd)}</td></tr>
            <tr><td>Sharpe / Sortino</td><td class="text-right">${fmt(item.sharpe, 2)} / ${fmt(item.sortino, 2)}</td></tr>
            <tr><td>Expectancy</td><td class="text-right">${fmt(item.expectancy_r, 3)}R</td></tr>
            <tr><td>Avg RR target / actual</td><td class="text-right">${fmt(item.avg_rr_target, 2)} / ${fmt(item.avg_rr_achieved, 2)}</td></tr>
            <tr><td>Max drawdown</td><td class="text-right">${fmt(item.max_drawdown_pct, 2)}%</td></tr>
            <tr><td>Kill zone win</td><td class="text-right">${fmtPct(item.kill_zone_win_rate_pct)}</td></tr>
            <tr><td>No kill zone win</td><td class="text-right">${fmtPct(item.no_kill_zone_win_rate_pct)}</td></tr>
            <tr><td>Trap / sweep / spread failures</td><td class="text-right">${esc(item.institutional_trap_failures || 0)} / ${esc(item.sweep_failures || 0)} / ${esc(item.spread_rejections || 0)}</td></tr>
          </tbody>
        </table>
        <div class="mt-3 rounded border border-zinc-700 bg-zinc-950 p-2 text-xs text-zinc-500">${esc(item.validation_note || "")}</div>
        <button class="mt-3 status-pill status-gray w-full justify-center" type="button" onclick="cockpit.showTradesForSlot('${esc(regimeId)}','${slot}')">View ${esc(item.total_trades || 0)} trades</button>` : `<div class="mt-3 space-y-3">
          <p class="text-xs text-zinc-500">No stored backtest yet. Values below are the strategy definition and research prior only.</p>
          <div class="rounded border border-zinc-700 bg-zinc-950 p-3 text-xs text-zinc-400">${esc(item.entry_logic || "No entry logic text returned.")}</div>
          <div class="grid grid-cols-3 gap-2 text-xs">
            ${featureCell("Prior WR", `${fmt(Number(item.expected_wr_low || 0) * 100, 0)}-${fmt(Number(item.expected_wr_high || 0) * 100, 0)}%`, "gray")}
            ${featureCell("Prior RRR", fmt(item.expected_rrr, 2), "gray")}
            ${featureCell("Prior EV", `${fmt(item.expected_ev_r, 2)}R`, "gray")}
          </div>
        </div>`}
        <div class="mt-3 grid gap-3 text-xs md:grid-cols-2">
          <div><p class="label">Filters</p><ul class="mt-1 list-disc pl-5 text-zinc-500">${filters || "<li>None returned.</li>"}</ul></div>
          <div><p class="label">Invalidations</p><ul class="mt-1 list-disc pl-5 text-zinc-500">${invalidations || "<li>None returned.</li>"}</ul></div>
        </div>
        <div class="mt-3 flex flex-wrap gap-1">${evidence || "<span class='text-xs text-zinc-500'>No evidence metadata.</span>"}</div>
      </div>`;
    }).join("");

    const series = findEquitySeries(detail);
    const chart = series ? `<div class="mb-4 rounded border border-zinc-700 bg-zinc-900 p-3">
      <p class="label">Stored equity curve</p>
      <div class="mt-2 h-72"><canvas id="equityChart"></canvas></div>
    </div>` : "";
    container.innerHTML = `${chart}<div class="grid gap-3 xl:grid-cols-4">${slotHtml}</div>`;
    renderEquityChart(series);
  }

  async function toggleDetail(regimeId, forceOpen) {
    const row = el(`detail-${regimeId}`);
    const content = el(`detail-content-${regimeId}`);
    if (!row || !content) return;
    if (!forceOpen && !row.classList.contains("hidden")) {
      row.classList.add("hidden");
      return;
    }
    row.classList.remove("hidden");
    content.innerHTML = "Loading strategy details...";
    try {
      const c = controls();
      const detail = await fetchJson(`/cockpit/api/strategy-detail/${encodeURIComponent(regimeId)}?${qs({ symbol: c.symbol, timeframe: c.timeframe })}`);
      renderStrategyDetail(regimeId, detail, content);
    } catch (error) {
      content.innerHTML = `<span class="text-red-300">${esc(error.message || error)}</span>`;
    }
  }

  function findEquitySeries(detail) {
    for (const slot of SLOTS) {
      const item = detail?.[slot];
      if (item && Array.isArray(item.equity_curve) && item.equity_curve.length) {
        return { slot, rows: item.equity_curve };
      }
    }
    return null;
  }

  function renderEquityChart(series) {
    if (!series || !window.Chart) return;
    const canvas = el("equityChart");
    if (!canvas) return;
    if (state.chart) state.chart.destroy();
    state.chart = new Chart(canvas, {
      type: "line",
      data: {
        labels: series.rows.map((row) => String(row.trade_number ?? "")),
        datasets: [{
          label: `${series.slot} equity`,
          data: series.rows.map((row) => Number(row.equity_usd ?? row.equity ?? 0)),
          borderColor: "#58a6ff",
          backgroundColor: "rgba(88, 166, 255, 0.12)",
          fill: true,
          tension: 0.25,
          pointRadius: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#a1a1aa" } } },
        scales: {
          x: { ticks: { color: "#a1a1aa" }, grid: { color: "rgba(63,63,70,0.55)" } },
          y: { ticks: { color: "#a1a1aa" }, grid: { color: "rgba(63,63,70,0.55)" } },
        },
      },
    });
  }

  function analyzeFailures(trades) {
    const closed = trades.filter((trade) => trade.result !== "open");
    const killZone = closed.filter((trade) => Boolean(trade.kill_zone_active));
    const noKillZone = closed.filter((trade) => !trade.kill_zone_active);
    const winRate = (items) => items.length ? Math.round((items.filter((trade) => trade.result === "win").length / items.length) * 100) : 0;
    const sessions = {};
    closed.forEach((trade) => {
      const label = trade.session_label || "Unknown";
      sessions[label] ||= { wins: 0, losses: 0, count: 0 };
      sessions[label].count += 1;
      if (trade.result === "win") sessions[label].wins += 1;
      if (trade.result === "loss") sessions[label].losses += 1;
    });
    const kzWr = winRate(killZone);
    const nkzWr = winRate(noKillZone);
    return {
      trap: closed.filter((trade) => Boolean(trade.failed_institutional)).length,
      sweep: closed.filter((trade) => Boolean(trade.failed_sweep_no_reclaim)).length,
      spread: closed.filter((trade) => Boolean(trade.failed_high_spread)).length,
      news: closed.filter((trade) => Boolean(trade.failed_news_event)).length,
      regimeChange: closed.filter((trade) => Boolean(trade.failed_regime_change)).length,
      killZoneTrades: killZone.length,
      noKillZoneTrades: noKillZone.length,
      killZoneWr: kzWr,
      noKillZoneWr: nkzWr,
      lift: kzWr - nkzWr,
      sessions,
    };
  }

  function renderTradeModal(title, trades) {
    const list = Array.isArray(trades) ? trades : [];
    const analysis = analyzeFailures(list);
    const sessionRows = Object.entries(analysis.sessions).map(([label, item]) => {
      const wr = item.count ? Math.round((item.wins / item.count) * 100) : 0;
      return `<div>${esc(label)}: ${item.wins}W/${item.losses}L (${wr}%)</div>`;
    }).join("");
    const tradeRows = list.map((trade, index) => {
      const flags = [
        trade.failed_institutional ? "Trap" : "",
        trade.failed_sweep_no_reclaim ? "No reclaim" : "",
        trade.failed_high_spread ? "Spread" : "",
        trade.failed_news_event ? "News" : "",
        trade.failed_regime_change ? "Regime change" : "",
      ].filter(Boolean).join(", ");
      return `<tr class="${trade.result === "win" ? "bg-emerald-950/20" : trade.result === "loss" ? "bg-red-950/20" : ""}">
        <td>${esc(trade.trade_number ?? index + 1)}</td>
        <td>${esc(trade.direction || "-")}</td>
        <td>${esc(trade.entry_time || "-")}</td>
        <td>${fmt(trade.entry_price, 5)}</td>
        <td>${fmt(trade.stop_price, 5)}</td>
        <td>${fmt(trade.tp_price, 5)}</td>
        <td>${fmt(trade.rr_target, 2)}</td>
        <td>${esc(trade.result || "-")}</td>
        <td>${fmt(trade.pnl_r, 3)}R</td>
        <td>${fmtUsd(trade.pnl_usd)}</td>
        <td>${esc(trade.session_label || "-")}</td>
        <td>${trade.kill_zone_active ? "yes" : "no"}</td>
        <td>${fmt(trade.adx_at_entry, 1)}</td>
        <td>${fmt(trade.er_at_entry, 3)}</td>
        <td class="text-red-300">${esc(flags)}</td>
      </tr>`;
    }).join("");

    openModal(title, `<div class="space-y-4">
      <div class="grid gap-3 md:grid-cols-3">
        <div class="rounded border border-red-900/60 bg-red-950/20 p-3 text-sm">
          <p class="font-semibold text-red-200">Failure analysis</p>
          <div class="mt-2 text-zinc-400">Institutional trap: <strong>${analysis.trap}</strong></div>
          <div class="text-zinc-400">Sweep no reclaim: <strong>${analysis.sweep}</strong></div>
          <div class="text-zinc-400">Spread spike: <strong>${analysis.spread}</strong></div>
          <div class="text-zinc-400">News event: <strong>${analysis.news}</strong></div>
          <div class="text-zinc-400">Regime changed: <strong>${analysis.regimeChange}</strong></div>
        </div>
        <div class="rounded border border-sky-900/60 bg-sky-950/20 p-3 text-sm">
          <p class="font-semibold text-sky-200">Session breakdown</p>
          <div class="mt-2 text-zinc-400">${sessionRows || "No closed trades."}</div>
        </div>
        <div class="rounded border border-emerald-900/60 bg-emerald-950/20 p-3 text-sm">
          <p class="font-semibold text-emerald-200">Kill zone lift</p>
          <div class="mt-2 text-zinc-400">KZ trades: ${analysis.killZoneTrades} (${analysis.killZoneWr}%)</div>
          <div class="text-zinc-400">Non-KZ trades: ${analysis.noKillZoneTrades} (${analysis.noKillZoneWr}%)</div>
          <div class="mt-2 font-semibold text-zinc-200">Lift: ${analysis.lift}%</div>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="table-compact">
          <thead><tr><th>#</th><th>Dir</th><th>Entry time</th><th>Entry</th><th>Stop</th><th>TP</th><th>RR</th><th>Result</th><th>R</th><th>P/L</th><th>Session</th><th>KZ</th><th>ADX</th><th>ER</th><th>Failure flags</th></tr></thead>
          <tbody>${tradeRows || "<tr><td colspan='15' class='py-6 text-center text-zinc-500'>No trades to display.</td></tr>"}</tbody>
        </table>
      </div>
    </div>`);
  }

  function showTradesForSlot(regimeId, slot) {
    const detail = state.details[regimeId]?.[slot];
    renderTradeModal(`${regimeId} ${slot} trades`, detail?.trades || []);
  }

  async function showTrades(runId, title) {
    const trades = await fetchJson(`/cockpit/api/trade-list/${encodeURIComponent(runId)}`);
    renderTradeModal(`${title || runId} trades`, trades);
  }

  function openModal(title, html) {
    const titleEl = el("modalTitle");
    const content = el("modalContent");
    const modal = el("tradeModal");
    if (titleEl) titleEl.textContent = title;
    if (content) content.innerHTML = html;
    if (modal) {
      modal.classList.remove("hidden");
      modal.classList.add("flex");
    }
  }

  function closeModal() {
    const modal = el("tradeModal");
    if (modal) {
      modal.classList.add("hidden");
      modal.classList.remove("flex");
    }
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
  }

  async function runBacktest(regimeId) {
    const c = controls();
    setStatus(`Running backtest for ${regimeId}...`);
    const form = new FormData();
    form.append("symbol", c.symbol);
    form.append("timeframe", c.timeframe);
    form.append("capital", String(c.capital));
    form.append("risk_pct", String(c.riskPct));
    try {
      const result = await fetchJson(`/cockpit/api/run-backtest/${encodeURIComponent(regimeId)}`, { method: "POST", body: form });
      await loadRanking();
      await toggleDetail(regimeId, true);
      setStatus(`Backtest complete: ${(result.runs_saved || []).length} runs saved for ${regimeId}`);
    } catch (error) {
      setStatus(`Backtest failed: ${String(error.message || error).slice(0, 160)}`);
    }
  }

  async function runAllMissing() {
    if (state.running) return;
    state.running = true;
    try {
      if (!state.ranking.length) await loadRanking();
      const missing = state.ranking.filter((row) => !row.tested && row.tradable && Number(row.expected_ev_r || 0) > 0);
      for (let index = 0; index < missing.length; index += 1) {
        setStatus(`Running ${index + 1}/${missing.length}: ${missing[index].regime_id}`);
        await runBacktest(missing[index].regime_id);
      }
      setStatus("Missing tradable backtests complete.");
    } finally {
      state.running = false;
    }
  }

  async function copyPlaybook() {
    const c = controls();
    const data = await fetchJson(`/cockpit/api/playbook-json?${qs({ symbol: c.symbol, timeframe: c.timeframe, capital: String(c.capital) })}`);
    state.playbook = data;
    const copied = await copyText(JSON.stringify(data, null, 2), "Current playbook JSON");
    setStatus(copied ? "Playbook JSON copied." : "Clipboard unavailable; JSON opened.");
  }

  async function copyStrategyJSON(slot) {
    if (!state.live) await loadLiveBanner();
    const signal = state.live?.strategies?.[slot] || {};
    const definition = (state.playbook?.strategies || []).find((item) => item.slot === slot) || {};
    const payload = {
      symbol: state.live?.symbol,
      timeframe: state.live?.timeframe,
      generated_utc: new Date().toISOString(),
      current_regime: state.live?.regime,
      market_values: state.live?.market_values,
      slot,
      strategy_signal: signal,
      strategy_definition: definition,
      live_trading_enabled: false,
      real_order_enabled: false,
    };
    const copied = await copyText(JSON.stringify(payload, null, 2), `${slot} strategy JSON`);
    setStatus(copied ? `${slot} strategy JSON copied.` : "Clipboard unavailable; strategy JSON opened.");
  }

  window.cockpit = {
    refreshAll,
    loadLiveBanner,
    loadRanking,
    toggleDetail,
    showTrades,
    showTradesForSlot,
    closeModal,
    runBacktest,
    runRegime: runBacktest,
    runAllMissing,
    copyPlaybook,
    copyStrategyJSON,
    openStrategyDetail: toggleDetail,
  };

  document.addEventListener("DOMContentLoaded", refreshAll);
})();
