const state = {
  market: null,
  regimes: [],
  strategies: [],
  modifiers: [],
  formulas: {},
  calibrationProfiles: [],
  apiStructure: null,
  dataSources: [],
  backtest: null,
  walkForward: null,
  outOfSample: null,
  validation: null,
  portfolio: null,
  optimizer: null,
  monteCarlo: null,
  mt5Import: null,
  mt5Tester: null,
  mt5Comparison: null,
  mt5ParityPacket: null,
  mt5Parity: null,
  mt5ParityCompletion: null,
  realTickWorkflow: null,
  brokerCostCalibration: null,
  macroEvidence: null,
  macroDiagnostics: null,
  llmReview: null,
  finalApproval: null,
  regimeLab: null,
  monthlyResearch: null,
  savedMonthlySweeps: [],
  savedValueProfiles: [],
  activeValueProfile: null,
  activeValuePayloadOverride: null,
  abExperiment: null,
  savedExperiments: [],
  latestMarket: null,
  savedRuns: [],
  savedValidationRuns: [],
  savedFeatures: [],
  jsonTesterResponses: {},
  selectedRegimeId: null,
};

const charts = {};

const $ = (id) => document.getElementById(id);

function selectedDataSourceMeta() {
  const value = $("dataSourceType")?.value || "mt5_retail_candles";
  return (state.dataSources || []).find((item) => item.value === value) || {};
}

function renderDataProviderHint() {
  const meta = selectedDataSourceMeta();
  const el = $("dataProviderHint");
  if (!el) return;
  const env = (meta.env || []).join(", ") || "none";
  const configured = meta.configured_env?.length ? `Configured env: ${meta.configured_env.join(", ")}` : "No matching env key/path detected.";
  el.innerHTML = `
    <div><b>${escapeHtml(meta.label || $("dataSourceType")?.value || "Data source")}</b> - ${escapeHtml(meta.free || "")}</div>
    <div class="mt-1">Env fallback: ${escapeHtml(env)}. ${escapeHtml(configured)}</div>
  `;
  if (meta.provider && !$("dataProviderName").value) $("dataProviderName").value = meta.provider;
}

function currentDataSourceControls(includeCredentials = false) {
  const source = $("dataSourceType")?.value || "mt5_retail_candles";
  const controls = {
    data_source: source,
    provider: $("dataProviderName")?.value || selectedDataSourceMeta().provider || "MT5 / SQLite",
    require_real_tick_validation: $("requireRealTickValidation")?.checked ?? true,
    require_institutional_order_flow: $("requireInstitutionalOrderFlow")?.checked ?? false,
    has_true_order_flow: $("hasTrueOrderFlow")?.checked ?? false,
    has_l2_order_book: $("hasL2OrderBook")?.checked ?? false,
    has_external_tick_data: ["dukascopy_ticks", "csv_import", "cme_fx_futures_proxy", "prime_broker_ticks", "ecn_l2_order_book", "reuters_ebs_tick", "bloomberg_bpipe_tick", "institutional_order_flow"].includes(source),
  };
  if (includeCredentials) {
    controls.api_key = $("dataProviderApiKey")?.value || "";
    controls.url = $("dataProviderLocation")?.value || "";
    controls.csv_url = $("dataProviderLocation")?.value || "";
    controls.csv_path = $("dataProviderLocation")?.value || "";
  }
  return controls;
}

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

function fmt(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "--";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(digits);
  return String(value);
}

function formatPrice(symbol, value) {
  if (value === null || value === undefined || value === "") return "--";
  const s = String(symbol || $("symbol")?.value || "").toUpperCase();
  const digits = s.includes("JPY") ? 3 : s.includes("XAU") || s.includes("XAG") ? 2 : 5;
  return Number(value).toFixed(digits);
}

function metricItems(items) {
  return items
    .map(([label, value]) => `<div class="metric-item"><div class="metric-label">${label}</div><div class="metric-value">${fmt(value)}</div></div>`)
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function jsonBlock(value) {
  return `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
}

function jsonText(value) {
  return escapeHtml(JSON.stringify(value, null, 2));
}

function statusBadge(status) {
  const normalized = String(status || "REFERENCE").toUpperCase();
  const cls = normalized.includes("APPROVED") || normalized.includes("ACCEPT") || normalized.includes("ACTIVE") || normalized.includes("PASS") || normalized.includes("READY")
    ? "badge-green"
    : normalized.includes("WATCH")
      ? "badge-yellow"
      : normalized.includes("INSUFFICIENT")
        ? "badge-orange"
        : normalized.includes("REJECT") || normalized.includes("BLOCK") || normalized.includes("FAIL") || normalized.includes("ERROR") || normalized.includes("MISSING")
          ? "badge-red"
          : "badge-gray";
  return `<span class="badge ${cls}">${normalized}</span>`;
}

function favoriteButton(itemType, itemId, isFavorite) {
  if (!itemId) return "";
  const nextValue = isFavorite ? "0" : "1";
  const title = isFavorite ? "Remove star" : "Star this result";
  const symbol = isFavorite ? "&#9733;" : "&#9734;";
  return `<button class="favorite-btn ${isFavorite ? "is-favorite" : ""}" title="${title}" aria-label="${title}" data-favorite-type="${escapeHtml(itemType)}" data-favorite-id="${escapeHtml(itemId)}" data-favorite-value="${nextValue}">${symbol}</button>`;
}

function sortFavoriteRows(rows, createdKey = "created_at") {
  return [...(rows || [])].sort((a, b) => {
    const favDiff = Number(b.is_favorite || 0) - Number(a.is_favorite || 0);
    if (favDiff) return favDiff;
    return String(b[createdKey] || "").localeCompare(String(a[createdKey] || ""));
  });
}

function applyFavoriteState(rows, idKey, itemId, isFavorite) {
  return sortFavoriteRows((rows || []).map((row) => (
    String(row[idKey] || "") === String(itemId) ? { ...row, is_favorite: isFavorite ? 1 : 0 } : row
  )));
}

const SECTION_HELP = {
  "Research Controls": {
    what: "Main research input console. It defines mode preset, symbol, timeframe, date range, regime, strategy, risk, RR, sentiment, filters, strict validation, and pattern switches.",
    why: "These values become the base payload for local backtests, MT5 tester config, optimizer, OOS, walk-forward, Monte Carlo, final approval, and LLM review.",
    how: ["Start with Discovery for broad scans.", "Use Strict Validation when a candidate has edge.", "Use Final Approval only after OOS, walk-forward, Monte Carlo, and MT5 validation look acceptable.", "Manual edits after a preset are allowed and sent with the run."],
    when: ["Use before every run.", "Use score_only for broad research.", "Use hard_filter when validating a candidate.", "Use Final Approval for funded-account style review."],
    combinations: ["R01 + T1 + hard spread/killzone + min alpha 8 for clean trend validation.", "R36 + VW1/VW2 + VWAP/session VWAP + min pattern score 2 for mean reversion.", "ALL + ALL + score_only for first-pass discovery."],
    values: ["Risk %: research 0.25-1.0; funded-style 0.25-0.75.", "RR: 1.5 for mean reversion, 2.0 for trend/breakout.", "Strict Validation: alpha 7, spread 70, ER 0.22, ADX 16-38, one tolerated non-critical regime fail.", "Final Approval: alpha 8, spread 65, ER 0.25, ADX 18-35, zero tolerated regime fails."]
  },
  "Regime Research Lab": {
    what: "A single-regime strategy-building workspace. It shows the selected regime's reference conditions, mapped strategies, editable threshold ranges, and candidate rankings.",
    why: "A real quant workflow does not ask whether one fixed setting works. It tests controlled permutations, then keeps only robust candidates for OOS, walk-forward, Monte Carlo, and MT5 real-tick validation.",
    how: ["Select one regime.", "Review the regime conditions/rules and mapped strategies.", "Edit the JSON ranges for RR, alpha, spread, pattern score, and calibration thresholds.", "Run Regime Lab to rank candidates.", "Backtest the best candidate before deeper validation."],
    when: ["After ALL/ALL discovery identifies a regime worth studying.", "When a regime has edge but poor consistency.", "Before MT5 real-tick validation."],
    combinations: ["R01: T1/T2/T3 with alpha 7-9, spread 60-70, RR 1.5-2.5, FVG+BOS pattern thresholds.", "R36: VW1/VW2/VW3 with VWAP/session VWAP, RR 1.2-1.8, ADX/ER max ranges.", "R34/R35: liquidity sweep strategies with hard spread and London/NY sessions."],
    values: ["Min trades: 20 for exploration, 50+ for candidate, 100+ preferred.", "PF: 1.15 watchlist, 1.20+ candidate.", "Pattern score: 0 discovery, 2 normal, 3 strict.", "Max DD R: align with funded-account limits."]
  },
  "Experiment Builder / A-B Testing": {
    what: "A named baseline-vs-variant research gate. It compares current controls against explicit variant changes and records the decision.",
    why: "Institutional research needs controlled comparisons. A/B avoids changing five things at once without knowing which change helped.",
    how: ["Load from the Regime Lab or current controls.", "Edit variant JSON with one or two targeted changes per variant.", "Set decision gates for trades, PF, expectancy improvement, and drawdown.", "Run and save the experiment before promoting a candidate."],
    when: ["After an optimizer candidate looks interesting.", "Before OOS/walk-forward/Monte Carlo validation.", "When deciding whether a stricter filter actually improves the setup."],
    combinations: ["Baseline R01/T1 vs hard killzone + alpha 8.", "Baseline R36/VW1 vs pattern hard minimum.", "Baseline R22/AR1 vs stricter spread and conservative calibration."],
    values: ["Min trades: 30+ for early A/B, 50-100 preferred.", "Min PF: 1.20 for candidate.", "Min expectancy gain: 0.02R or higher.", "Max DD worsening: keep small unless profit factor and OOS improve."]
  },
  "Editable Research Values": {
    what: "A reusable profile editor for the exact values sent to research APIs: filters, pattern engine, regime controls, strategy controls, calibration thresholds, costs, risk, and execution assumptions.",
    why: "After a backtest, monthly sweep, optimizer, or A/B result works, you need to preserve the exact tested values rather than trying to remember which sliders and JSON settings created the edge.",
    how: ["Run a backtest or monthly sweep.", "Click Load Current Values.", "Edit only the values you intentionally want to test.", "Click Apply Edited Values to use them in future runs.", "Click Save Values Profile once the tested setup is worth reusing."],
    when: ["Use after finding a candidate in Regime Lab, Optimizer, Monthly Sweep, or A/B Testing.", "Use before running OOS, walk-forward, Monte Carlo, MT5 parity, and real-tick validation on the same values."],
    combinations: ["R01 + T1 with alpha 8, spread 65, pattern hard minimum 2, stop ATR 0.75.", "R36 + VW1/VW2 with VWAP enabled, RR 1.5, ADX/ER mean-reversion thresholds.", "R22 + AR1/AR2 with Asia-only range settings and conservative cost model."],
    values: ["Save only tested values, not guesses.", "Use profile descriptions to record why the change was made.", "Loaded profiles override future payloads until Clear Active is clicked.", "The baseline regime/strategy library remains unchanged for reference integrity."]
  },
  "MT5 Strategy Tester Automation": {
    what: "Builds MT5 .set and .ini files from the current UI controls and can launch MT5 Strategy Tester.",
    why: "Local Python backtest is research; MT5 Strategy Tester checks execution model, spread, slippage, tick sequence, and broker data behavior.",
    how: ["Compile QuantForexV10_ResearchEA.mq5 in MetaEditor.", "Set terminal path or MT5_TERMINAL_PATH.", "Choose 1-Min OHLC for fast research, Real Ticks for final validation.", "Enable wait/import only when MT5 writes the report path."],
    when: ["After a local setup looks promising.", "Before final approval.", "Always for tight SL/scalping or spread-sensitive setups."],
    combinations: ["Run same R/strategy on 1-Min OHLC, Every Tick, Real Ticks.", "Use strict filters for Real Ticks final validation."],
    values: ["1-Min OHLC = fast filter.", "Every Tick = better intrabar simulation.", "Real Ticks = final validation.", "Launch terminal off = config generation only."]
  },
  "Walk-Forward Testing": {
    what: "Repeated train/test validation windows across the selected date range.",
    why: "Checks whether the strategy survives changing market periods rather than fitting one static sample.",
    how: ["Use current controls.", "Start with 2 train months and 1 test month.", "Require pass rate above 60%.", "Review failed windows by regime/session."],
    when: ["After optimizer finds a candidate.", "Before Monte Carlo/final approval."],
    combinations: ["R01/T1 strict trend validation.", "R36/VW1 or VW2 for session mean reversion stability."],
    values: ["Train months: 2-6.", "Test months: 1-2.", "Min test trades: 20+.", "Min test PF: 1.10+."]
  },
  "Out-of-Sample Testing": {
    what: "Splits the selected period into in-sample and unseen future out-of-sample data.",
    why: "A setup that only works in the fit period is not reliable.",
    how: ["Use OOS 30% by default.", "Check OOS PF, expectancy, trade count, and retention.", "Reject if OOS expectancy turns negative."],
    when: ["After a promising local backtest.", "Before walk-forward or final approval."],
    combinations: ["Optimizer candidate -> OOS -> walk-forward -> Monte Carlo -> MT5 Real Ticks."],
    values: ["OOS %: 25-40.", "Min OOS trades: 20+.", "Min OOS PF: 1.10+.", "Retention below 50% = warning."]
  },
  "Optimizer Grid": {
    what: "Runs controlled permutations of regimes, strategies, RR, alpha, spread, killzone, and pattern thresholds.",
    why: "Ranks candidates without calling them approved. It finds where the edge may be hiding.",
    how: ["Keep grids small.", "Change one family of values at a time.", "Use top candidates as inputs for OOS/WF/MC/MT5 validation."],
    when: ["Discovery stage.", "When a strategy has weak but positive edge and you need better thresholds."],
    combinations: ["Min alpha 5,7,8.", "Spread max 65,70.", "RR 1.5,2.0.", "Pattern score 0,2,3."],
    values: ["Min PF: 1.20 for candidates.", "Min trades: 30+.", "Max DD R: 10-12.", "Max combos: keep low for speed."]
  },
  "Monte Carlo Drawdown Test": {
    what: "Resamples trade results to estimate drawdown, loss probability, and losing-streak risk.",
    why: "A profitable average can still fail a funded account if drawdowns cluster badly.",
    how: ["Run after there are enough trades.", "Use bootstrap for uncertainty.", "Use shuffle to test sequence risk only."],
    when: ["After OOS and walk-forward pass.", "Before final approval."],
    combinations: ["Strict trend setups: max DD 10%, max losing streak 5.", "Higher frequency setups need more source trades."],
    values: ["Simulations: 1000 normal, 5000 stronger.", "Min trades: 30 minimum, 100 better.", "Drawdown breach <=10% is preferred."]
  },
  "Saved Backtest Runs": {
    what: "Reloads stored local backtest results.",
    why: "Lets you compare prior experiments without rerunning everything.",
    how: ["Click Load Saved Runs.", "Click a run id to reload summary, trades, charts, and analysis."],
    when: ["When comparing optimizer candidates or older settings."],
    combinations: ["Reload a candidate, then run OOS/WF/MC/final approval."],
    values: ["Use run_id to match MT5 report imports."]
  },
  "Saved Feature Rows": {
    what: "Shows saved calculated feature rows such as ADX, ER, ATR percentile, spread, session, and regime inputs.",
    why: "Helps debug why regimes or strategies trigger or fail.",
    how: ["Load rows for the selected symbol/timeframe/date range.", "Check data quality, feature NaN, spread, session, trend weakening."],
    when: ["When detect latest or backtest looks wrong."],
    combinations: ["Compare feature rows with skipped setup reasons."],
    values: ["ADX 18-35 clean trend.", "ER >=0.25 trend quality.", "Spread percentile <=65 strict."]
  },
  "Data Health": {
    what: "Data quality and feature completeness summary.",
    why: "Bad OHLC, missing spreads, duplicate timestamps, or NaN features can create fake edge.",
    how: ["Review before trusting performance.", "If status is not OK, inspect R40/manual review reasons."],
    when: ["Every backtest.", "Especially after importing/fetching new data."],
    combinations: ["R40 blocks trades when data is unreliable."],
    values: ["Minimum percentile history ideally 252 bars.", "Required active-strategy features should be complete."]
  },
  "Feature Summary": {
    what: "Condensed view of market features used by regimes and strategies.",
    why: "Explains the data behind the classification, not just the final trade result.",
    how: ["Use it to verify ADX/ER/spread/session/VWAP context.", "Compare to regime conditions."],
    when: ["When a regime seems wrong or a strategy does not trigger."],
    combinations: ["Feature summary + skipped setups = failure diagnosis."],
    values: ["ADX, ER, ATR percentile, spread percentile, MTF conflict, trend weakening."]
  },
  "Regime Confidence": {
    what: "Shows evaluated regime candidates and confidence.",
    why: "Helps identify mixed states, fuzzy classification, and transition regimes.",
    how: ["Check whether active regime is pure or only barely above threshold.", "Use strict validation for clean trend regimes."],
    when: ["Before trusting R01/R02 clean trend results."],
    combinations: ["If confidence is weak, test R31 transition/watchlist behavior."],
    values: ["Clean regimes should be high confidence; transition often means reduce risk or no trade."]
  },
  "Regime Cards": {
    what: "Reference cards for all regimes.",
    why: "Shows market state meaning, direction, allowed strategies, conditions, values, and rules.",
    how: ["Click a regime to filter detail, trades, skipped setups, and explanation."],
    when: ["When studying a regime or selecting a backtest filter."],
    combinations: ["R01/T1 trend, R03/S1 sweep, R36/VW1 VWAP mean reversion, R40 no trade."],
    values: ["Use cards as research reference, not execution approval."]
  },
  "Selected Regime": {
    what: "Detailed drilldown for the clicked regime.",
    why: "Connects reference rules with actual backtest evidence.",
    how: ["Click a regime card.", "Review allowed strategies, formulas, trades, pattern impact, skipped reasons."],
    when: ["When deciding if one regime is worth optimizing or validating."],
    combinations: ["Select R36 then inspect VW1/VW2 performance and VWAP pattern rows."],
    values: ["Good regime should show enough trades, positive expectancy, and explainable failures."]
  },
  "Regime Performance": {
    what: "Performance grouped by regime.",
    why: "Shows which market states help or hurt the system.",
    how: ["Look for PF, expectancy, trade count, and drawdown.", "Do not trust tiny samples."],
    when: ["After ALL/ALL discovery backtest."],
    combinations: ["Promote regimes with positive expectancy into single-regime tests."],
    values: ["Trade count 50+ useful, 100+ stronger.", "PF >1.15 initial, >1.20 better."]
  },
  "Strategy Performance": {
    what: "Performance grouped by strategy.",
    why: "Separates whether the regime works from whether the entry model works.",
    how: ["Find positive strategies inside positive regimes.", "Reject strategies with negative expectancy or poor sample."],
    when: ["After ALL strategy testing or selected regime testing."],
    combinations: ["R01 with T1/T2/T3; R36 with VW1/VW2/VW3."],
    values: ["Expectancy >0 required.", "PF >1.10 watchlist, >1.20 candidate."]
  },
  "Unique Setup Combinations": {
    what: "Performance of unique regime/strategy/session/pattern/filter combinations.",
    why: "Real edge often exists only in specific combinations, not broad labels.",
    how: ["Sort by expectancy and trade count.", "Check whether a profitable combo is robust or tiny sample."],
    when: ["After pattern and filter testing."],
    combinations: ["R01+T1+London+FVG+BOS, R36+VW1+NY+VWAP_HIGH."],
    values: ["Use enough trades before trusting a combination."]
  },
  "Modifier Impact": {
    what: "Shows how modifiers affect performance.",
    why: "Modifiers explain failure modes such as MTF conflict, exhaustion, spread stress, or news risk.",
    how: ["Compare trades with and without each modifier.", "Turn harmful modifiers into hard blocks."],
    when: ["When success rate is low or losses cluster."],
    combinations: ["Reject M08 conflict for clean trend.", "Reject M11 exhaustion for continuation entries."],
    values: ["Hard block when modifier impact is consistently negative."]
  },
  "Pattern Performance": {
    what: "Performance grouped by patterns such as FVG, OB, BOS, MSS, VWAP, liquidity, and round numbers.",
    why: "Tests whether a pattern actually improves results instead of just sounding institutional.",
    how: ["Compare pattern trades vs non-pattern trades.", "Use minimum pattern score only if it improves real results."],
    when: ["After enabling pattern engine."],
    combinations: ["FVG+BOS trend continuation.", "VWAP+wick rejection mean reversion.", "Sweep+MSS reversal."],
    values: ["Pattern score 2 normal, 3 strict.", "FVG min ATR 0.20, max age 30 bars."]
  },
  "MT5 Model Comparison": {
    what: "Compares imported MT5 1-Min OHLC, Every Tick, and Real Tick reports.",
    why: "If results collapse from candle model to real ticks, execution assumptions are not reliable.",
    how: ["Import all three reports from the same setup.", "Check PF drift, trade count drift, net profit drift, and real-tick PF."],
    when: ["Before final approval.", "Always for tight stops and spread-sensitive strategies."],
    combinations: ["Same symbol/date/regime/strategy/settings across all three models."],
    values: ["Real tick PF >=1.10.", "PF drift <=0.35.", "Trade-count drift <=35%."]
  },
  "MT5 Real Tick Report Importer": {
    what: "Imports a single MT5 Strategy Tester report or all three model reports.",
    why: "Brings broker-side execution evidence into the research console.",
    how: ["Paste deals/history table text.", "Choose model.", "For comparison, paste all three reports.", "Use same setup for all reports."],
    when: ["After running MT5 Strategy Tester."],
    combinations: ["1-Min OHLC for research, Every Tick for validation, Real Ticks for final review."],
    values: ["Preferred report columns: result_R, initial_risk, alpha_score, pattern_score, final_score, patterns_detected.", "If result_R is missing but initial_risk exists, R = profit / initial_risk.", "If a run_id is supplied, importer enriches matched rows from saved Python trades."]
  },
  "Session Performance": {
    what: "Performance grouped by trading session.",
    why: "Forex edge is session-dependent; London/NY/Overlap often behave differently from Asia/off-session.",
    how: ["Check expectancy by session.", "Use hard_filter if off-session is harmful."],
    when: ["Before enabling killzone hard filters."],
    combinations: ["Trend: London/NY/Overlap.", "Asia range: R22-specific only."],
    values: ["Allowed strict sessions usually London, NewYork, Overlap."]
  },
  "Monthly Performance": {
    what: "Performance by month.",
    why: "Shows whether edge is stable or concentrated in one lucky month.",
    how: ["Look for multiple positive months.", "Investigate month-end/fixing distortions."],
    when: ["Before final approval."],
    combinations: ["Compare with R30 month-end/fixing regime."],
    values: ["Avoid approval if one month contributes most profit."]
  },
  "Equity / Drawdown": {
    what: "Equity and drawdown charts for selected regime trades.",
    why: "Visualizes path risk and streak pain, not just total profit.",
    how: ["Click a regime card to populate charts.", "Look for smoothness, deep drawdowns, and recovery time."],
    when: ["After each backtest."],
    combinations: ["Use with Monte Carlo to understand drawdown tails."],
    values: ["Drawdown must fit funded account limits."]
  },
  "Monthly / Session Charts": {
    what: "Visual monthly/session performance charts.",
    why: "Quickly shows concentration risk across time and trading sessions.",
    how: ["Use after selecting a regime or running ALL backtest."],
    when: ["When deciding which sessions/months to include or exclude."],
    combinations: ["Session chart + killzone hard filter.", "Monthly chart + month-end modifier."],
    values: ["Negative sessions should be filtered or moved to watchlist."]
  },
  "Trade List": {
    what: "Executed trades with regime, strategy, patterns, alpha, result, profit, and reason.",
    why: "Trade-level evidence is where you learn why winners/losers happen.",
    how: ["Inspect losses by setup context.", "Check spread, session, pattern score, and alpha."],
    when: ["After every backtest and MT5 import."],
    combinations: ["Sort mentally by regime+strategy+pattern+session."],
    values: ["Good trades should have clear reason and valid SL/TP."]
  },
  "Skipped / Blocked Setups": {
    what: "Signals that almost traded but were blocked.",
    why: "This explains strategy failure and filter behavior better than winners alone.",
    how: ["Read block reason.", "If good trades are blocked, loosen settings.", "If bad trades are blocked, keep or strengthen settings."],
    when: ["When trade count is low or filters feel too strict."],
    combinations: ["Strict trend validation + reject low ER + reject ADX outside band."],
    values: ["Common blockers: spread, session, low ER, MTF conflict, pattern score, data quality."]
  },
  "Approval Checklist": {
    what: "Local per-regime/per-strategy approval checks.",
    why: "Prevents calling a weak sample approved.",
    how: ["Use as first local quality check.", "Then run final approval gate for full validation."],
    when: ["After local backtest."],
    combinations: ["Checklist + OOS + WF + MC + MT5 Real Ticks."],
    values: ["Insufficient trades remains a warning even if PF is positive."]
  },
  "What Worked / Failed / Next Tests": {
    what: "Narrative summary of backtest strengths, failures, warnings, and next experiments.",
    why: "Turns statistics into research actions.",
    how: ["Read after each run.", "Convert next tests into optimizer/OOS/WF settings."],
    when: ["After local backtest and before changing parameters."],
    combinations: ["Use with LLM reviewer for deeper diagnosis."],
    values: ["Warnings should drive the next experiment."]
  },
  "Final Approval Gate": {
    what: "Single gate that checks whether candidate survived all required validation layers.",
    why: "Optimizer ranking alone is not approval. Final approval needs local, OOS, WF, MC, and MT5 Real Tick evidence.",
    how: ["Run local backtest, OOS, WF, MC, and MT5 comparison first.", "Then run final approval.", "Use auto-run only for local validators, not MT5 reports."],
    when: ["Only after a strategy candidate looks promising."],
    combinations: ["Optimizer candidate -> Backtest -> OOS -> WF -> MC -> MT5 comparison -> Final gate."],
    values: ["Backtest trades 50+, Real Tick trades 30+, PF thresholds 1.10-1.15, DD limit 12R."]
  },
  "Ollama / LLM Quant Reviewer": {
    what: "Optional local model reviewer using Ollama, with rule-based fallback.",
    why: "Helps summarize failure reasons, validation gaps, and next research steps.",
    how: ["Run Ollama locally.", "Use model like llama3.1:8b.", "Click Run Reviewer after generating results."],
    when: ["After backtest, MT5 comparison, optimizer, and final approval gate."],
    combinations: ["Use reviewer output to plan next optimizer grid."],
    values: ["Ollama URL default http://127.0.0.1:11434.", "If offline, fallback still works."]
  },
  "Strategy Library": {
    what: "Reference list of all strategies.",
    why: "Shows which strategy belongs to which regime and category.",
    how: ["Use it to choose a strategy filter.", "Avoid testing strategies outside their regime."],
    when: ["Before targeted backtesting."],
    combinations: ["Select regime first, then choose mapped strategy."],
    values: ["Default RR is a starting point, not final approval."]
  },
  "Modifier Library": {
    what: "Reference list of modifiers and hard-block behavior.",
    why: "Modifiers explain special market conditions that can improve or invalidate setups.",
    how: ["Review hard-block modifiers.", "Promote consistently harmful modifiers to strict filters."],
    when: ["When performance changes by context."],
    combinations: ["M08 conflict + clean trend = reject.", "Spread stress + no-trade regimes = block."],
    values: ["Hard-block means no trade; score modifier means confidence adjustment."]
  },
  "Formula Reference": {
    what: "Formula definitions used by feature/regime/pattern logic.",
    why: "Makes research auditable and adjustable.",
    how: ["Use formulas to understand features before changing thresholds.", "Keep formulas measurable from OHLC/tick volume."],
    when: ["When adding ICT/VWAP/regime logic or debugging unexpected output."],
    combinations: ["Formula -> feature -> regime -> strategy -> filter -> trade."],
    values: ["Every discretionary concept should become a measurable formula."]
  },
  "API Request Examples": {
    what: "Postman-style request and response shapes.",
    why: "Lets you inspect and test backend endpoints directly from UI.",
    how: ["Open a block, edit JSON, send request, inspect output.", "Use MT5 endpoint payloads for tester config checks."],
    when: ["When UI output seems wrong or you want endpoint-level debugging."],
    combinations: ["Regime+strategy payload + pattern_engine + filters + mt5_backtest."],
    values: ["Backend returns exact skipped reasons, payload, config, and response fields."]
  }
};

function defaultHelp(title) {
  return {
    what: `${title} is part of the research workflow.`,
    why: "Use it to connect configuration, validation evidence, and trade-level diagnosis.",
    how: ["Open the section, run or load data, then compare the output against the validation gates."],
    when: ["Use after the relevant upstream data has been generated."],
    combinations: ["Combine with regime, strategy, filter, pattern, and MT5 validation context."],
    values: ["Prefer enough trades, positive expectancy, controlled drawdown, and real-tick confirmation."]
  };
}

function helpBlock(title, data) {
  const group = (name, value) => {
    const items = Array.isArray(value) ? value : [value];
    return `
      <div>
        <div class="help-mini-title">${escapeHtml(name)}</div>
        <ul>${items.filter(Boolean).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </div>`;
  };
  return `
    <details class="section-help">
      <summary>What / Why / How / When / Examples</summary>
      <div class="section-help-grid">
        ${group("What", data.what)}
        ${group("Why", data.why)}
        ${group("How To Use", data.how)}
        ${group("When To Use", data.when)}
        ${group("Combinations / Examples", data.combinations)}
        ${group("Values To Watch", data.values)}
      </div>
    </details>`;
}

function sectionHeading(panel) {
  const first = panel.firstElementChild;
  if (!first) return null;
  if (first.matches("h2")) return first;
  return first.querySelector("h2");
}

function sectionTitleFromHeading(heading) {
  const textOnly = Array.from(heading.childNodes)
    .filter((node) => node.nodeType === Node.TEXT_NODE)
    .map((node) => node.textContent)
    .join(" ");
  return (textOnly || heading.textContent || "")
    .replace(/\s+/g, " ")
    .replace(/\bShow\b|\bHide\b/g, "")
    .trim();
}

function setupSectionHelp() {
  const topLevelSections = [...document.querySelectorAll("main > section")].filter((section) => {
    const first = section.firstElementChild;
    return first && !first.classList.contains("table-panel") && !section.className.includes("grid");
  });
  const panels = [...topLevelSections, ...document.querySelectorAll(".table-panel"), ...document.querySelectorAll("aside")];

  panels.forEach((panel) => {
    if (panel.dataset.helpReady === "true") return;
    const heading = sectionHeading(panel);
    if (!heading) return;
    const title = sectionTitleFromHeading(heading);
    if (!title) return;
    const wrapper = document.createElement("div");
    wrapper.innerHTML = helpBlock(title, SECTION_HELP[title] || defaultHelp(title));
    const help = wrapper.firstElementChild;
    const header = heading.parentElement && heading.parentElement !== panel ? heading.parentElement : heading;
    header.insertAdjacentElement("afterend", help);
    panel.dataset.helpReady = "true";
  });
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = json.detail || json.error || `${res.status} ${res.statusText}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return json;
}

function setLoading(message) {
  setText("lastAction", message);
}

function setError(error) {
  setText("lastAction", `Error: ${error.message || error}`);
}

function selectOptions(id, values, selected) {
  const el = $(id);
  const selectedText = String(selected ?? "");
  el.innerHTML = values
    .map((item) => {
      const value = typeof item === "object" && item !== null ? item.value : item;
      const label = typeof item === "object" && item !== null ? item.label : item;
      const valueText = String(value ?? "");
      return `<option value="${escapeHtml(valueText)}" ${valueText === selectedText ? "selected" : ""}>${escapeHtml(label ?? valueText)}</option>`;
    })
    .join("");
}

function setControlValue(id, value) {
  const el = $(id);
  if (!el || value === undefined || value === null) return;
  el.value = value;
}

function setControlChecked(id, value) {
  const el = $(id);
  if (!el || value === undefined || value === null) return;
  el.checked = Boolean(value);
}

function modePresetByName(name) {
  return state.market?.research_mode_presets?.[name] || null;
}

function renderModePresetSummary() {
  const name = $("modePreset")?.value || state.market?.default_mode_preset || "Strict Validation";
  const preset = modePresetByName(name);
  const target = $("modePresetSummary");
  if (!target || !preset) return;
  const model = preset.mt5_tester_model || $("mt5TesterModel")?.value || "every_tick";
  const rows = [
    ["Mode", name],
    ["Use", preset.description || ""],
    ["Spread", `${preset.spread_filter_mode || "--"} <= ${preset.max_spread_percentile ?? "--"}%`],
    ["Killzone", preset.killzone_mode || "--"],
    ["Alpha", `${preset.alpha_mode || "--"} >= ${preset.min_alpha_score ?? "--"}`],
    ["Pattern", `${preset.pattern_score_mode || "--"} >= ${preset.min_pattern_score ?? "--"}`],
    ["Regime Fails", `<= ${preset.strict_regime_max_failed_conditions ?? "--"} @ ${preset.strict_regime_min_confidence ?? "--"}`],
    ["Clean Trend", `ER ${preset.min_clean_trend_er ?? "--"} / ADX ${preset.clean_trend_adx_min ?? "--"}-${preset.clean_trend_adx_max ?? "--"}`],
    ["MT5", model],
  ];
  target.innerHTML = `<div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-9">${rows.map(([label, value]) => `
    <div>
      <div class="text-xs font-semibold uppercase text-slate-500">${escapeHtml(label)}</div>
      <div class="font-semibold text-slate-800">${escapeHtml(value)}</div>
    </div>
  `).join("")}</div>
  <p class="mt-2 text-xs text-slate-500">Preset fills the controls only. You can still manually edit any threshold before running the backtest, MT5 config, optimizer, OOS, walk-forward, Monte Carlo, or LLM review.</p>`;
}

function applyModePreset(name, announce = false) {
  const preset = modePresetByName(name);
  if (!preset) return;
  setControlValue("calibrationProfile", preset.calibration_profile);
  setControlValue("killzoneMode", preset.killzone_mode);
  setControlValue("spreadFilterMode", preset.spread_filter_mode);
  setControlValue("alphaMode", preset.alpha_mode);
  setControlValue("patternScoreMode", preset.pattern_score_mode);
  setControlValue("minAlphaScore", preset.min_alpha_score);
  setControlValue("maxSpreadPercentile", preset.max_spread_percentile);
  setControlValue("strictRegimeMaxFailed", preset.strict_regime_max_failed_conditions);
  setControlValue("strictRegimeMinConfidence", preset.strict_regime_min_confidence);
  setControlValue("minCleanTrendEr", preset.min_clean_trend_er);
  setControlValue("cleanTrendAdxMin", preset.clean_trend_adx_min);
  setControlValue("cleanTrendAdxMax", preset.clean_trend_adx_max);
  setControlValue("minPatternScore", preset.min_pattern_score);
  setControlChecked("strictCleanTrend", preset.strict_clean_trend);
  setControlChecked("strictRegimeValidation", preset.strict_regime_validation);
  setControlChecked("rejectTrendWeakening", preset.reject_trend_weakening);
  setControlChecked("rejectLowErCleanTrend", preset.reject_low_er_clean_trend);
  setControlChecked("rejectAdxOutsideCleanTrend", preset.reject_adx_outside_clean_trend);
  setControlChecked("rejectMtfConflictScore", preset.reject_mtf_conflict_score);
  setControlChecked("useRegimeHysteresis", preset.use_regime_hysteresis);
  setControlValue("hysteresisConfirmBars", preset.hysteresis_confirm_bars);
  setControlValue("hysteresisConfidenceMargin", preset.hysteresis_confidence_margin);
  setControlValue("mt5TesterModel", preset.mt5_tester_model);
  setControlChecked("mt5UsePythonSignals", preset.use_python_signals);
  setControlChecked("mt5BuildPythonSignals", preset.build_python_signals ?? false);
  renderModePresetSummary();
  if (announce) setLoading(`${name} preset applied. You can edit any value before running.`);
}

function regimeById(id) {
  return state.regimes.find((r) => r.regime_id === id) || null;
}

function strategyById(id) {
  return state.strategies.find((s) => s.strategy_id === id) || null;
}

function uniqueValues(values) {
  return [...new Set(values.filter((value) => value !== undefined && value !== null && value !== ""))];
}

function numericValues(values) {
  return uniqueValues(values.map(Number).filter((value) => Number.isFinite(value)));
}

function strategyIdsForRegime(regimeId) {
  if (!regimeId || regimeId === "ALL") return state.strategies.map((s) => s.strategy_id);
  const mapped = strategiesForRegime(regimeId).map((s) => s.strategy_id);
  return mapped.length ? mapped : state.strategies.filter((s) => String(s.regime || "").includes(regimeId)).map((s) => s.strategy_id);
}

function strategyOptionsForRegime(regimeId) {
  const ids = strategyIdsForRegime(regimeId);
  const regimeLabel = regimeId && regimeId !== "ALL" ? `${regimeId} mapped strategies` : "all strategies";
  return [
    { value: "ALL", label: `ALL - ${regimeLabel}` },
    ...ids.map((id) => {
      const strategy = strategyById(id);
      const parts = [id, strategy?.strategy_name].filter(Boolean);
      const meta = [strategy?.direction, strategy?.category].filter(Boolean).join(" / ");
      return {
        value: id,
        label: `${parts.join(" - ")}${meta ? ` (${meta})` : ""}`,
      };
    }),
  ];
}

function updateStrategyFilterForRegime(regimeId, preferred = null) {
  const values = strategyOptionsForRegime(regimeId);
  const allowed = values.map((item) => item.value);
  const current = preferred || $("strategyFilter")?.value || "ALL";
  const selected = allowed.includes(current) ? current : "ALL";
  selectOptions("strategyFilter", values, selected);
}

function updateLabStrategyOptions(preferred = null) {
  const regimeId = $("labRegimeSelect")?.value || $("regimeFilter")?.value || "R01";
  const values = strategyOptionsForRegime(regimeId);
  const allowed = values.map((item) => item.value);
  const current = preferred || $("labStrategySelect")?.value || "ALL";
  const selected = allowed.includes(current) ? current : "ALL";
  selectOptions("labStrategySelect", values, selected);
}

function parseJsonValue(id, fallback = {}) {
  const raw = String($(id)?.value || "").trim();
  if (!raw) return fallback;
  return JSON.parse(raw);
}

function deepMerge(base, override) {
  if (!override || typeof override !== "object" || Array.isArray(override)) return base;
  const merged = { ...(base || {}) };
  Object.entries(override).forEach(([key, value]) => {
    if (value && typeof value === "object" && !Array.isArray(value) && merged[key] && typeof merged[key] === "object" && !Array.isArray(merged[key])) {
      merged[key] = deepMerge(merged[key], value);
    } else if (value !== undefined) {
      merged[key] = value;
    }
  });
  return merged;
}

function parseJsonEditor(id, fallback = {}) {
  try {
    return parseJsonValue(id, fallback);
  } catch (err) {
    throw new Error(`${id} contains invalid JSON: ${err.message}`);
  }
}

function labDefaultResearchValues(regimeId) {
  const mapped = strategiesForRegime(regimeId);
  const rrValues = numericValues([...mapped.map((s) => s.default_rr), 1.5, 2.0]).filter((v) => v > 0);
  const values = {
    rr_values: rrValues.length ? rrValues : [1.5, 2.0],
    min_alpha_scores: [5, 7, 8],
    max_spread_percentiles: [65, 70],
    killzone_modes: ["score_only", "hard_filter"],
    spread_filter_modes: ["score_only", "hard_filter"],
    pattern_score_modes: ["score_only", "hard_minimum"],
    min_pattern_scores: [0, 2, 3],
    calibration_profiles: ["balanced", "conservative", "funded_style"],
    stop_atr_values: [0.25, 0.35, 0.5, 0.75, 1.0, 1.25],
    stop_override_modes: ["widen_only"],
    min_effective_stop_spread_mult_values: [10],
    use_symbol_session_stop_profile_values: [true],
    adx_min_values: [],
    adx_max_values: [],
    er_min_values: [],
    er_max_values: [],
    atr_percentile_min_values: [],
    atr_percentile_max_values: [],
    candle_range_atr_min_values: [],
    candle_range_atr_max_values: [],
    upper_wick_min_values: [],
    lower_wick_min_values: [],
    vwap_distance_atr_min_values: [],
    confidence_min_values: [],
  };
  if (["R01", "R02", "R11", "R12", "R13", "R14"].includes(regimeId)) {
    values.adx_min_values = regimeId === "R11" || regimeId === "R12" ? [14, 18] : [18, 20];
    values.adx_max_values = regimeId === "R11" || regimeId === "R12" ? [25, 28] : [35, 40];
    values.er_min_values = regimeId === "R11" || regimeId === "R12" ? [0.2, 0.25] : [0.25, 0.3];
    values.atr_percentile_min_values = [20, 25];
    values.atr_percentile_max_values = [75, 80];
  }
  if (["R03", "R15", "R16", "R22", "R36", "R37"].includes(regimeId)) {
    values.adx_max_values = [18, 20, 25];
    values.er_max_values = [0.25, 0.3];
    values.atr_percentile_min_values = [15, 25];
    values.atr_percentile_max_values = [75, 80];
    values.upper_wick_min_values = [0.35, 0.4];
    values.lower_wick_min_values = [0.35, 0.4];
  }
  if (["R04", "R05", "R19", "R20", "R21"].includes(regimeId)) {
    values.adx_min_values = [20, 22, 25];
    values.er_min_values = [0.25, 0.3];
    values.atr_percentile_min_values = [65, 75];
    values.candle_range_atr_min_values = [1.0, 1.2, 1.5];
  }
  if (["R34", "R35"].includes(regimeId)) {
    values.upper_wick_min_values = [0.35, 0.4, 0.45];
    values.lower_wick_min_values = [0.35, 0.4, 0.45];
    values.er_min_values = [0.2, 0.25, 0.3];
  }
  if (regimeId === "R36") {
    values.vwap_distance_atr_min_values = [1.25, 1.5, 1.75];
    values.rr_values = [1.2, 1.5, 1.8];
  }
  return values;
}

function labStrategyCsv(regimeId) {
  const selected = $("labStrategySelect")?.value || "ALL";
  if (selected !== "ALL") return selected;
  return strategyIdsForRegime(regimeId).join(",");
}

function renderRegimeLabResult() {
  const result = state.regimeLab || {};
  const summary = result.summary || {};
  $("labRunSummary").innerHTML = metricItems([
    ["Combos Run", summary.combinations_run],
    ["Approved", summary.approved_candidates],
    ["Watchlist", summary.watchlist_candidates],
    ["Best Score", summary.best_score],
    ["Best Regime", summary.best_regime],
    ["Best Strategy", summary.best_strategy],
    ["Min Trades", summary.min_trades],
    ["Min PF", summary.min_profit_factor],
    ["Max DD R", summary.max_drawdown_r],
    ["Validated", summary.validated_candidates],
    ["Saved Passed", summary.saved_validated_candidates],
  ]);
  $("labCandidateTable").innerHTML = table(
    [
      { label: "Rank", key: "rank" },
      { label: "Regime", key: "regime_filter" },
      { label: "Strategy", key: "strategy_filter" },
      { label: "RR", key: "rr" },
      { label: "Alpha", key: "min_alpha_score" },
      { label: "Spread", key: "max_spread_percentile" },
      { label: "KZ", key: "killzone_mode" },
      { label: "Spread Mode", key: "spread_filter_mode" },
      { label: "Pattern", render: (r) => `${r.pattern_score_mode} / ${r.min_pattern_score}` },
      { label: "Stop ATR", key: "stop_atr" },
      { label: "Stop/Spread", key: "min_effective_stop_spread_mult" },
      { label: "Trades", key: "total_trades" },
      { label: "Win", render: (r) => r.win_rate !== undefined ? `${(Number(r.win_rate) * 100).toFixed(1)}%` : "--" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "T", key: "edge_t_stat" },
      { label: "P", key: "edge_p_value_approx" },
      { label: "DD R", key: "max_drawdown_R" },
      { label: "Score", key: "optimizer_score" },
      { label: "OOS", render: (r) => r.oos_status ? `${r.oos_status} PF:${fmt(r.oos_pf)}` : "--" },
      { label: "WF", render: (r) => r.wf_pass_rate !== undefined ? `${(Number(r.wf_pass_rate) * 100).toFixed(0)}% / ${fmt(r.wf_efficiency)}` : "--" },
      { label: "MC", render: (r) => r.mc_status ? `${r.mc_status} loss:${r.mc_loss_probability !== undefined ? `${(Number(r.mc_loss_probability) * 100).toFixed(0)}%` : "--"}` : "--" },
      { label: "Validated", render: (r) => r.validation_status ? statusBadge(r.validation_status) : "--" },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    (result.results || []).slice(0, 12),
    "Run Regime Lab to see ranked strategy/pattern/filter candidates."
  );
  if ((result.warnings || []).length) {
    $("labCandidateTable").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Warnings:</b> ${escapeHtml(result.warnings.join(" "))}</div>`;
  }
}

function renderRegimeLab(resetValues = false) {
  if (!$("labRegimeSelect")) return;
  const regimeId = $("labRegimeSelect").value || $("regimeFilter")?.value || "R01";
  const regime = regimeById(regimeId) || state.regimes[0];
  if (!regime) return;
  updateLabStrategyOptions();
  const mapped = strategiesForRegime(regime.regime_id);
  const focus = $("labStrategySelect").value;
  const strategies = focus && focus !== "ALL" ? [strategyById(focus)].filter(Boolean) : mapped;
  $("labRegimeOverview").innerHTML = metricItems([
    ["Name", `${regime.regime_id} ${regime.regime_name}`],
    ["Direction", regime.direction],
    ["Risk", regime.risk?.funded_suggested || regime.risk?.research_default],
    ["Strategies", mapped.map((s) => s.strategy_id).join(", ") || "--"],
  ]);
  $("labRegimeRules").innerHTML = `
    <p class="mb-2">${escapeHtml(regime.meaning || "")}</p>
    <div class="lab-list-title">Conditions</div>
    <ul class="lab-list">${(regime.conditions || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
    <div class="lab-list-title mt-3">Rules</div>
    <ul class="lab-list">${(regime.rules || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>`;
  $("labStrategyRules").innerHTML = table(
    [
      { label: "ID", key: "strategy_id" },
      { label: "Name", key: "strategy_name" },
      { label: "Direction", key: "direction" },
      { label: "Category", key: "category" },
      { label: "RR", key: "default_rr" },
    ],
    strategies,
    "No strategy mapped to this regime."
  );
  if (resetValues || $("labResearchValuesJson").dataset.regimeId !== regime.regime_id || !String($("labResearchValuesJson").value || "").trim()) {
    $("labResearchValuesJson").value = JSON.stringify(labDefaultResearchValues(regime.regime_id), null, 2);
    $("labResearchValuesJson").dataset.regimeId = regime.regime_id;
  }
  if (resetValues || $("labStrategiesCsv").dataset.regimeId !== regime.regime_id || !String($("labStrategiesCsv").value || "").trim()) {
    $("labStrategiesCsv").value = labStrategyCsv(regime.regime_id);
    $("labStrategiesCsv").dataset.regimeId = regime.regime_id;
  }
  renderRegimeLabResult();
}

function currentRegimeLabPayload() {
  const base = currentPayload();
  const regimeId = $("labRegimeSelect").value || base.regime_filter;
  const researchValues = parseJsonValue("labResearchValuesJson", labDefaultResearchValues(regimeId));
  const strategies = parseCsv("labStrategiesCsv", strategyIdsForRegime(regimeId));
  const grid = {
    regime_filters: [regimeId],
    strategy_filters: strategies.length ? strategies : strategyIdsForRegime(regimeId),
    rr_values: researchValues.rr_values || [base.rr],
    min_alpha_scores: researchValues.min_alpha_scores || [base.filters.min_alpha_score],
    max_spread_percentiles: researchValues.max_spread_percentiles || [base.filters.max_spread_percentile],
    killzone_modes: researchValues.killzone_modes || [base.filters.killzone_mode],
    alpha_modes: researchValues.alpha_modes || [base.filters.alpha_mode],
    spread_filter_modes: researchValues.spread_filter_modes || [base.filters.spread_filter_mode],
    pattern_score_modes: researchValues.pattern_score_modes || [base.pattern_engine.pattern_score_mode],
    min_pattern_scores: researchValues.min_pattern_scores || [base.pattern_engine.min_pattern_score],
    calibration_profiles: researchValues.calibration_profiles || [base.calibration.profile || "balanced"],
  };
  [
    "adx_min_values",
    "adx_max_values",
    "er_min_values",
    "er_max_values",
    "atr_percentile_min_values",
    "atr_percentile_max_values",
    "candle_range_atr_min_values",
    "candle_range_atr_max_values",
    "upper_wick_min_values",
    "lower_wick_min_values",
    "vwap_distance_atr_min_values",
    "macro_confidence_min_values",
    "confidence_min_values",
    "max_spread_percentile_values",
    "range_edge_tolerance_values",
    "stop_atr_values",
    "stop_override_modes",
    "min_effective_stop_spread_mult_values",
    "use_symbol_session_stop_profile_values",
  ].forEach((key) => {
    if (Array.isArray(researchValues[key]) && researchValues[key].length) grid[key] = researchValues[key];
  });
  return {
    ...base,
    regime_filter: regimeId,
    strategy_filter: "ALL",
    max_combinations: Number($("labMaxCombos").value || 48),
    min_trades: Number($("labMinTrades").value || 20),
    min_profit_factor: Number($("labMinPf").value || 1.15),
    max_drawdown_r: Number($("labMaxDd").value || 12),
    validate_top_n: Number($("labValidateTopN")?.value || 0),
    persist_validated_candidates: $("labPersistValidated")?.checked ?? true,
    validation: optimizerValidationSettings(),
    grid,
  };
}

function currentMonthlyResearchPayload() {
  const base = currentPayload();
  const regimes = parseCsv("monthlySweepRegimes", ["ALL"]);
  return {
    ...base,
    timeframe: "M15",
    start_date: null,
    end_date: base.end_date,
    months_back: Number($("monthlySweepMonthsBack")?.value || 6),
    regime_filters: regimes.length ? regimes : "ALL",
    strategy_filters: "ALL",
    stop_atr_grid: parseNumberCsv("monthlySweepStopGrid", [0.25, 0.35, 0.5, 0.75, 1.0, 1.25]),
    min_effective_stop_spread_mult: parseNumberCsv("monthlySweepMinStopSpread", [10]),
    use_symbol_session_stop_profile: $("monthlySweepUseProfiles")?.checked ?? true,
    stop_override_mode: "widen_only",
    min_effective_stop_mode: "widen",
    max_combinations_per_regime_month: Number($("monthlySweepMaxCombos")?.value || 24),
    top_candidates_per_regime_month: Number($("monthlySweepTopN")?.value || 3),
    min_monthly_trades: Number($("monthlySweepMinTrades")?.value || 1),
    min_monthly_profit_factor: Number($("monthlySweepMinPf")?.value || 1.05),
    max_monthly_drawdown_r: Number($("monthlySweepMaxDd")?.value || 8),
    require_positive_monthly_profit: true,
    save_only_working: $("monthlySweepSaveOnlyWorking")?.checked ?? true,
    strategy_controls: {
      ...base.strategy_controls,
      use_stop_realism: true,
      use_symbol_session_stop_profile: $("monthlySweepUseProfiles")?.checked ?? true,
      min_effective_stop_mode: "widen",
    },
  };
}

function abDefaultVariants() {
  const base = currentPayload();
  return [
    {
      label: "Hard killzone + alpha 8",
      changes: {
        killzone_mode: "hard_filter",
        filters: {
          killzone_mode: "hard_filter",
          min_alpha_score: Math.max(Number(base.filters?.min_alpha_score || 5), 8),
        },
      },
    },
    {
      label: "Spread max 65 + conservative calibration",
      changes: {
        filters: { max_spread_percentile: 65 },
        calibration: { ...base.calibration, profile: "conservative" },
      },
    },
    {
      label: "Pattern hard minimum",
      changes: {
        pattern_engine: {
          ...base.pattern_engine,
          use_patterns: true,
          pattern_score_mode: "hard_minimum",
          min_pattern_score: Math.max(Number(base.pattern_engine?.min_pattern_score || 0), 3),
        },
      },
    },
  ];
}

function ensureAbDefaults(force = false) {
  if (!$("abVariantsJson")) return;
  if (force || !String($("abVariantsJson").value || "").trim()) {
    $("abVariantsJson").value = JSON.stringify(abDefaultVariants(), null, 2);
  }
}

function currentAbExperimentPayload() {
  ensureAbDefaults(false);
  return {
    name: $("abName").value || "Regime variant test",
    hypothesis: $("abHypothesis").value || "",
    baseline_label: $("abBaselineLabel").value || "Current controls",
    base_payload: currentPayload(),
    variants: parseJsonValue("abVariantsJson", abDefaultVariants()),
    decision_rules: {
      min_trades: Number($("abMinTrades").value || 30),
      min_profit_factor: Number($("abMinPf").value || 1.2),
      min_expectancy_R: Number($("abMinExp").value || 0),
      min_expectancy_improvement_R: Number($("abMinExpGain").value || 0.02),
      max_drawdown_R: Number($("abMaxDd").value || 12),
      max_drawdown_worsening_R: Number($("abMaxDdWorsen").value || 2),
    },
    persist: true,
  };
}

function renderAbExperiment() {
  ensureAbDefaults(false);
  const result = state.abExperiment || {};
  const summary = result.summary || {};
  const baseline = result.baseline?.metrics || {};
  $("abSummary").innerHTML = metricItems([
    ["Status", summary.status],
    ["Baseline", summary.baseline_label],
    ["Baseline Trades", summary.baseline_trades ?? baseline.total_trades],
    ["Baseline PF", baseline.profit_factor],
    ["Baseline Exp R", baseline.expectancy_R],
    ["Variants", summary.variants_tested],
    ["Accepted", summary.accepted_variants],
    ["Watchlist", summary.watchlist_variants],
    ["Best Variant", summary.best_variant_label],
    ["Best Exp Gain", summary.best_delta_expectancy_R],
    ["Best PF Gain", summary.best_delta_profit_factor],
  ]);
  $("abComparisonTable").innerHTML = table(
    [
      { label: "Rank", key: "rank" },
      { label: "Variant", key: "label" },
      { label: "Trades", key: "total_trades" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "DD R", key: "max_drawdown_R" },
      { label: "Net", render: (r) => r.net_profit !== undefined ? `$${fmt(r.net_profit)}` : "--" },
      { label: "dTrades", key: "delta_trades" },
      { label: "dPF", key: "delta_profit_factor" },
      { label: "dExp", key: "delta_expectancy_R" },
      { label: "dDD", key: "delta_max_drawdown_R" },
      { label: "Status", render: (r) => statusBadge(r.status) },
      { label: "Reason", render: (r) => escapeHtml((r.reasons || []).slice(0, 2).join(" ")) },
    ],
    result.comparison || [],
    "Run an A/B experiment to compare baseline and variant research settings."
  );
  if ((result.warnings || []).length) {
    $("abComparisonTable").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Warnings:</b> ${escapeHtml(result.warnings.join(" "))}</div>`;
  }
  $("savedExperimentsPanel").innerHTML = table(
    [
      { label: "", render: (r) => favoriteButton("experiment", r.experiment_id, Number(r.is_favorite) === 1) },
      { label: "ID", render: (r) => `<button class="text-sky-700 underline" data-experiment-id="${escapeHtml(r.experiment_id)}">${escapeHtml(r.experiment_id)}</button>` },
      { label: "Name", key: "name" },
      { label: "Status", render: (r) => statusBadge(r.status) },
      { label: "Best", key: "best_variant_label" },
      { label: "Accepted", key: "accepted_variants" },
    ],
    state.savedExperiments || [],
    "Saved A/B experiments will appear here."
  );
}

function applyCandidateToControls(candidate) {
  if (!candidate) return;
  if (candidate.regime_filter) {
    $("regimeFilter").value = candidate.regime_filter;
    updateStrategyFilterForRegime(candidate.regime_filter, candidate.strategy_filter || "ALL");
  }
  if (candidate.strategy_filter && $("strategyFilter")) $("strategyFilter").value = candidate.strategy_filter;
  if (candidate.rr !== undefined && $("rr")) $("rr").value = String(candidate.rr);
  if (candidate.min_alpha_score !== undefined && $("minAlphaScore")) $("minAlphaScore").value = candidate.min_alpha_score;
  if (candidate.max_spread_percentile !== undefined && $("maxSpreadPercentile")) $("maxSpreadPercentile").value = candidate.max_spread_percentile;
  if (candidate.killzone_mode && $("killzoneMode")) $("killzoneMode").value = candidate.killzone_mode;
  if (candidate.spread_filter_mode && $("spreadFilterMode")) $("spreadFilterMode").value = candidate.spread_filter_mode;
  if (candidate.pattern_score_mode && $("patternScoreMode")) $("patternScoreMode").value = candidate.pattern_score_mode;
  if (candidate.min_pattern_score !== undefined && $("minPatternScore")) $("minPatternScore").value = candidate.min_pattern_score;
  if (candidate.calibration_profile && $("calibrationProfile")) $("calibrationProfile").value = candidate.calibration_profile;
  renderCalibration();
}

function renderSummary(summary = {}) {
  const modePreset = state.backtest?.mode_preset || {};
  const applied = modePreset.applied || {};
  const cards = [
    ["Mode Preset", modePreset.selected || summary.strict_thresholds?.mode_preset || $("modePreset")?.value || "--"],
    ["Preset MT5", applied.mt5_backtest?.test_model || "--"],
    ["Preset Alpha", applied.filters?.min_alpha_score !== undefined ? applied.filters.min_alpha_score : summary.strict_thresholds?.min_alpha_score],
    ["Preset Spread", applied.filters?.max_spread_percentile !== undefined ? applied.filters.max_spread_percentile : summary.strict_thresholds?.max_spread_percentile],
    ["Initial Equity", summary.initial_equity !== undefined ? `$${fmt(summary.initial_equity, 0)}` : "--"],
    ["Ending Equity", summary.ending_equity !== undefined ? `$${fmt(summary.ending_equity, 0)}` : "--"],
    ["Net Profit", summary.net_profit !== undefined ? `$${fmt(summary.net_profit)}` : "--"],
    ["Gross Loss", summary.gross_loss !== undefined ? `$${fmt(summary.gross_loss)}` : "--"],
    ["Total Trades", summary.total_trades],
    ["Win Rate", summary.win_rate !== undefined ? `${(summary.win_rate * 100).toFixed(1)}%` : "--"],
    ["Break-even Win", summary.break_even_win_rate !== undefined ? `${(summary.break_even_win_rate * 100).toFixed(1)}%` : "--"],
    ["Actual - BE", summary.actual_vs_break_even !== undefined ? `${(summary.actual_vs_break_even * 100).toFixed(1)}%` : "--"],
    ["Profit Factor", summary.profit_factor],
    ["Expectancy R", summary.expectancy_R],
    ["Average R", summary.average_R],
    ["Pattern Score", summary.average_pattern_score],
    ["Final Score", summary.average_final_score],
    ["Avg Win R", summary.average_win_R],
    ["Avg Loss R", summary.average_loss_R],
    ["Payoff", summary.payoff_ratio],
    ["Avg Cost R", summary.average_cost_R],
    ["Cost R", summary.total_cost_R],
    ["Max DD R", summary.max_drawdown_R],
    ["Losing Streak", summary.max_losing_streak],
    ["ROI %", summary.roi_percent],
    ["Best Session", summary.best_session],
    ["Worst Session", summary.worst_session],
    ["Skipped", summary.skipped_setups],
    ["Best Regime", summary.best_regime],
    ["Worst Regime", summary.worst_regime],
    ["Best Strategy", summary.best_strategy],
    ["Worst Strategy", summary.worst_strategy],
  ];
  $("summaryCards").innerHTML = cards
    .map(([label, value]) => `<div class="summary-card"><div class="summary-label">${label}</div><div class="summary-value">${fmt(value)}</div></div>`)
    .join("");
}

function renderResearchPanels() {
  const h = state.backtest?.data_health || {};
  const dq = state.backtest?.institutional_data_quality || {};
  $("institutionalDataPanel").innerHTML = metricItems([
    ["Source", dq.source_type || "--"],
    ["Provider", dq.provider || "--"],
    ["Grade", dq.data_grade || "--"],
    ["Score", dq.data_score],
    ["Validation", dq.validation_status || "--"],
    ["Semi Manual", dq.semi_manual_readiness === undefined ? "--" : dq.semi_manual_readiness ? "Ready for demo review" : "Not ready"],
    ["Order Flow", dq.institutional_order_flow_available === undefined ? "--" : dq.institutional_order_flow_available ? "Yes" : "No"],
    ["L2 Book", dq.level2_order_book_available === undefined ? "--" : dq.level2_order_book_available ? "Yes" : "No"],
    ["External Tick", dq.external_tick_available === undefined ? "--" : dq.external_tick_available ? "Yes" : "No"],
    ["MT5 Real Tick", dq.mt5_real_tick_validated === undefined ? "--" : dq.mt5_real_tick_validated ? "Yes" : "No"],
    ["Spread Coverage", dq.coverage ? `${(Number(dq.coverage.spread || 0) * 100).toFixed(1)}%` : "--"],
    ["Real Volume", dq.coverage ? `${(Number(dq.coverage.real_volume || 0) * 100).toFixed(1)}%` : "--"],
  ]);
  const dqWarnings = [...(dq.limitations || []), ...(dq.warnings || [])];
  $("institutionalDataWarnings").innerHTML = dqWarnings.length
    ? `<div class="rounded border border-amber-200 bg-amber-50 p-3 text-amber-950"><b>Data limitations:</b><ul class="mt-2 list-disc pl-5">${dqWarnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`
    : `<div class="rounded border border-slate-200 bg-white p-3">Run a backtest to grade data provenance and order-flow readiness.</div>`;
  $("dataHealthPanel").innerHTML = metricItems([
    ["Source", h.source],
    ["Bars Loaded", h.bars_loaded],
    ["Expected Bars", h.bars_expected_calendar],
    ["Missing Est.", h.candles_missing_estimate],
    ["Duplicates", h.duplicate_candles],
    ["First Candle", h.first_candle_time],
    ["Last Candle", h.last_candle_time],
    ["Spread", h.spread_available === undefined ? "--" : h.spread_available ? "Yes" : "No"],
    ["HTF Resampled", h.htf_derived_by_resampling === undefined ? "--" : h.htf_derived_by_resampling ? "Yes" : "No"],
    ["NaN Rows", h.feature_rows_with_nan],
    ["R40 Warmup", h.warmup_rows],
    ["R40 Bad Data", h.bad_data_rows],
    ["Raw Switches", h.raw_regime_switches],
    ["Stable Switches", h.stable_regime_switches],
    ["Hysteresis Holds", h.hysteresis_suppressed_flips],
    ["Feature Cache", h.feature_cache_status ? `${h.feature_cache_status}${h.feature_cache_hit ? " hit" : ""}` : "--"],
    ["Tradable Rows", h.tradable_rows_after_filters],
  ]);

  const f = state.backtest?.feature_summary || {};
  $("featureSummaryPanel").innerHTML = metricItems([
    ["Rows", f.rows],
    ["ADX Avg", f.adx?.avg],
    ["ADX Min/Max", f.adx ? `${fmt(f.adx.min)} / ${fmt(f.adx.max)}` : "--"],
    ["ER Avg", f.er?.avg],
    ["EMA Slope Avg", f.ema_slope?.avg],
    ["Stat Vote", f.latest_stat_regime_vote],
    ["Stat Confidence", f.latest_stat_regime_confidence],
    ["Hurst Avg", f.hurst_exponent?.avg],
    ["Fractal Dim Avg", f.fractal_dimension?.avg],
    ["Kalman Slope", f.kalman_slope?.avg],
    ["GARCH Vol %", f.garch_vol_percentile?.avg],
    ["Break Score Avg", f.structural_break_score?.avg],
    ["Break Flags", f.structural_break_count],
    ["HMM State", f.latest_hmm_state],
    ["HMM Prob", f.hmm_state_probability?.avg],
    ["Stat Disagree", f.stat_regime_disagreement_count],
    ["MTF Agreement", f.mtf_agreement_count],
    ["MTF Conflict", f.mtf_conflict_count],
    ["Sweep High", f.sweep_high_count],
    ["Sweep Low", f.sweep_low_count],
    ["Trend Weakening", f.trend_weakening_count],
    ["Bull Pullback Fail", f.bull_pullback_failure_count],
    ["Bear Pullback Fail", f.bear_pullback_failure_count],
    ["VWAP High Extreme", f.vwap_extreme_high_count],
    ["VWAP Low Extreme", f.vwap_extreme_low_count],
    ["Post-Stress", f.post_stress_normalization_count],
    ["Gap Flags", f.gap_count],
    ["Data Quality Issues", f.data_quality_issue_count],
    ["R40 Warmup", f.r40_warmup_count ?? f.data_quality_warmup_count],
    ["R40 Bad Data", f.r40_bad_data_count ?? f.data_quality_bad_data_count],
    ["Raw Switches", f.raw_regime_switches],
    ["Stable Switches", f.stable_regime_switches],
    ["Hysteresis Holds", f.hysteresis_suppressed_flips],
    ["ATR Normal", f.atr_percentile_distribution?.normal_25_75],
    ["Spread Normal", f.spread_percentile_distribution?.normal_0_70],
  ]);

  const c = state.backtest?.cost_summary || {};
  $("costSummaryPanel").innerHTML = metricItems([
    ["Mode", c.cost_mode],
    ["Total Cost R", c.total_cost_R],
    ["Avg Cost R", c.average_cost_R],
    ["Cost $", c.total_cost_currency],
    ["Spread Cost R", c.spread_cost_R],
    ["Commission R", c.commission_R],
    ["Slippage R", c.slippage_R],
    ["News Multiplier", c.news_cost_multiplier],
    ["Rollover Block", c.rollover_block === undefined ? "--" : c.rollover_block ? "Yes" : "No"],
  ]);

  const d = state.backtest?.spread_slippage_diagnostics || {};
  const selectedId = state.selectedRegimeId;
  const regimeDiagRows = selectedId ? (d.regime || []).filter((r) => r.regime_id === selectedId) : (d.regime || []);
  $("spreadSessionDiagnostics").innerHTML = table(
    [
      { label: "Session", key: "session" },
      { label: "Rows", key: "feature_rows" },
      { label: "Trades", key: "trade_count" },
      { label: "Avg Spread", key: "avg_spread" },
      { label: "Spread P90", key: "spread_p90" },
      { label: "Slip Est R", key: "slippage_estimate_R" },
      { label: "Slip Points", key: "slippage_estimate_points" },
      { label: "Cost R", key: "avg_cost_R" },
    ],
    d.session || [],
    "Run a backtest to show spread and slippage by session."
  );
  $("spreadRegimeDiagnostics").innerHTML = table(
    [
      { label: "Regime", render: (r) => `${r.regime_id} ${r.regime_name}` },
      { label: "Trades", key: "trade_count" },
      { label: "Avg Spread", key: "avg_spread" },
      { label: "Stress Count", key: "spread_stress_count" },
      { label: "Cost Blocks", key: "cost_blocked_setups" },
      { label: "Failed Cost %", render: (r) => `${fmt(r.failed_cost_percent)}%` },
      { label: "Avg Cost R", key: "avg_cost_R" },
    ],
    regimeDiagRows,
    selectedId ? "No spread/cost diagnostics for selected regime." : "Run a backtest to show regime cost diagnostics."
  );
  $("spreadSymbolDiagnostics").innerHTML = table(
    [
      { label: "Symbol", key: "symbol" },
      { label: "Trades", key: "trade_count" },
      { label: "Avg Spread", key: "avg_spread" },
      { label: "Avg Cost R", key: "avg_cost_R" },
      { label: "Best Session", key: "best_session" },
      { label: "Worst Session", key: "worst_session" },
    ],
    d.symbol || [],
    "Run a backtest to show symbol spread diagnostics."
  );
  const failure = state.backtest?.execution_failure_summary || {};
  $("executionFailureDiagnostics").innerHTML = table(
    [
      { label: "Failure Type", key: "failure_type" },
      { label: "Trade Checks", key: "trade_checks" },
      { label: "Trade Warnings", key: "trade_warnings" },
      { label: "Skipped Blocks", key: "skipped_blocks" },
      { label: "Status", render: (r) => statusBadge(r.status || "INFO") },
    ],
    failure.rows || [],
    "Run a backtest with stop/execution realism to show live-market failure diagnostics."
  );

  const rows = selectedId ? (state.backtest?.regime_confidence || []).filter((r) => r.regime_id === selectedId) : [];
  $("regimeConfidencePanel").innerHTML = table(
    [
      { label: "Regime", render: (r) => `${r.regime_id} ${r.regime_name}` },
      { label: "Candles", key: "candles_detected" },
      { label: "Active %", key: "active_percent" },
      { label: "Avg Conf", key: "average_confidence" },
      { label: "Min", key: "min_confidence" },
      { label: "Max", key: "max_confidence" },
      { label: "Common Mod", key: "most_common_modifier" },
    ],
    rows,
    selectedId ? "No confidence rows for selected regime." : "Click a regime card to show its confidence summary."
  );
}

function renderWalkForward() {
  const result = state.walkForward || {};
  const summary = result.summary || {};
  $("walkForwardSummary").innerHTML = metricItems([
    ["Windows", summary.windows],
    ["Passed", summary.passed_windows],
    ["Watchlist", summary.watchlist_windows],
    ["Failed", summary.failed_windows],
    ["Pass Rate", summary.pass_rate !== undefined ? `${(Number(summary.pass_rate) * 100).toFixed(1)}%` : "--"],
    ["Avg WFE", summary.average_walk_forward_efficiency],
    ["Agg WFE", summary.aggregate_walk_forward_efficiency],
    ["Train R", summary.total_train_R],
    ["Test R", summary.total_test_R],
    ["Stable", summary.stable === undefined ? "--" : summary.stable ? "Yes" : "No"],
  ]);
  const rows = result.windows || [];
  $("walkForwardTable").innerHTML = table(
    [
      { label: "Win", key: "window" },
      { label: "Train", render: (r) => `${r.train_start} to ${r.train_end}` },
      { label: "Test", render: (r) => `${r.test_start} to ${r.test_end}` },
      { label: "Train Trades", render: (r) => r.train?.total_trades },
      { label: "Test Trades", render: (r) => r.test?.total_trades },
      { label: "Train PF", render: (r) => r.train?.profit_factor },
      { label: "Test PF", render: (r) => r.test?.profit_factor },
      { label: "Train Exp", render: (r) => r.train?.expectancy_R },
      { label: "Test Exp", render: (r) => r.test?.expectancy_R },
      { label: "Test DD", render: (r) => r.test?.max_drawdown_R },
      { label: "WFE", key: "walk_forward_efficiency" },
      { label: "Status", render: (r) => statusBadge(r.status) },
      { label: "Reason", render: (r) => escapeHtml((r.reasons || []).join("; ")) },
    ],
    rows,
    "Run walk-forward to compare train windows against future out-of-sample test windows."
  );
  if ((result.warnings || []).length) {
    $("walkForwardTable").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Warnings:</b> ${escapeHtml(result.warnings.join(" "))}</div>`;
  }
  const diagnostics = result.diagnostics || {};
  const suggestions = diagnostics.suggestions || [];
  if (suggestions.length || Object.keys(diagnostics.failure_reason_counts || {}).length) {
    const reasonRows = Object.entries(diagnostics.failure_reason_counts || {}).map(([reason, count]) => ({ reason, count }));
    $("walkForwardTable").innerHTML += `
      <div class="mt-3 border border-slate-200 bg-slate-50 p-3 text-sm">
        <div class="mb-2 font-semibold text-slate-700">Walk-forward failure review</div>
        ${reasonRows.length ? table([{ label: "Count", key: "count" }, { label: "Reason", key: "reason" }], reasonRows) : ""}
        ${suggestions.length ? `<ul class="mt-2 list-disc space-y-1 pl-5">${suggestions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
      </div>`;
  }
}

function renderOutOfSample() {
  const result = state.outOfSample || {};
  const summary = result.summary || {};
  const inSample = result.in_sample || {};
  const outSample = result.out_of_sample || {};
  const comparison = result.comparison || {};
  $("outOfSampleSummary").innerHTML = metricItems([
    ["Status", summary.status],
    ["Stable", summary.stable === undefined ? "--" : summary.stable ? "Yes" : "No"],
    ["Split", summary.split_date],
    ["IS Trades", inSample.total_trades],
    ["OOS Trades", outSample.total_trades],
    ["IS PF", inSample.profit_factor],
    ["OOS PF", outSample.profit_factor],
    ["IS Exp R", inSample.expectancy_R],
    ["OOS Exp R", outSample.expectancy_R],
    ["Exp Retention", summary.expectancy_retention],
    ["PF Retention", summary.profit_factor_retention],
    ["R Efficiency", summary.total_R_efficiency],
    ["DD Expansion", summary.drawdown_expansion],
  ]);
  const rows = [
    { sample: "In Sample", ...inSample },
    { sample: "Out of Sample", ...outSample },
  ].filter((row) => Object.keys(row).length > 1);
  $("outOfSampleTable").innerHTML = table(
    [
      { label: "Sample", key: "sample" },
      { label: "Trades", key: "total_trades" },
      { label: "Win", render: (r) => r.win_rate !== undefined ? `${(Number(r.win_rate) * 100).toFixed(1)}%` : "--" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Avg R", key: "average_R" },
      { label: "Total R", key: "total_R" },
      { label: "Max DD", key: "max_drawdown_R" },
      { label: "Net P/L", render: (r) => r.net_profit !== undefined ? `$${fmt(r.net_profit)}` : "--" },
      { label: "Best Session", key: "best_session" },
    ],
    rows,
    "Run out-of-sample to compare the earlier research period with a future unseen period."
  );
  if (Object.keys(comparison).length) {
    $("outOfSampleTable").innerHTML += `<div class="mt-3 rounded border border-slate-200 bg-slate-50 p-3 text-sm"><b>Delta:</b> ${escapeHtml(JSON.stringify(comparison))}</div>`;
  }
  const reasonList = Array.isArray(result.reasons) ? result.reasons : result.reasons ? [result.reasons] : [];
  const warningList = Array.isArray(result.warnings) ? result.warnings : result.warnings ? [result.warnings] : [];
  const messages = [...reasonList, ...warningList];
  if (messages.length) {
    $("outOfSampleTable").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Review:</b> ${escapeHtml(messages.join(" "))}</div>`;
  }
}

function renderValidationCockpit() {
  const result = state.validation || {};
  const summary = result.summary || {};
  $("validationSummary").innerHTML = metricItems([
    ["Status", summary.status || "--"],
    ["Score", summary.validation_score !== undefined ? `${fmt(summary.validation_score)} / 100` : "--"],
    ["Passed", summary.passed_required !== undefined ? `${summary.passed_required}/${summary.total_required}` : "--"],
    ["Failed", summary.failed_required],
    ["Regime", summary.regime_filter || $("regimeFilter")?.value || "--"],
    ["Strategy", summary.strategy_filter || $("strategyFilter")?.value || "--"],
    ["MT5 Required", summary.mt5_required === undefined ? "--" : summary.mt5_required ? "Yes" : "No"],
    ["Portfolio", summary.portfolio_run === undefined ? "--" : summary.portfolio_run ? "Run" : "Skipped"],
  ]);
  $("validationScorecard").innerHTML = table(
    [
      { label: "Layer", key: "layer" },
      { label: "Status", render: (r) => statusBadge(r.status) },
      { label: "Required", render: (r) => (r.required ? "yes" : "no") },
      { label: "Weight", key: "weight" },
      { label: "Value", key: "value" },
      { label: "Rule", key: "rule" },
    ],
    result.scorecard || [],
    "Run full validation to produce one scorecard across backtest, OOS, walk-forward, Monte Carlo, portfolio, and MT5 model comparison."
  );
  const tone = summary.status === "DEMO_REVIEW_READY" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : summary.status ? "border-amber-200 bg-amber-50 text-amber-900" : "border-slate-200 bg-white text-slate-600";
  $("validationDecision").innerHTML = summary.status
    ? `<div class="rounded border ${tone} p-3"><b>Decision:</b> ${escapeHtml(summary.decision || summary.status)}</div>`
    : "";
  if ((result.next_actions || []).length) {
    $("validationDecision").innerHTML += `<div class="mt-3 rounded border border-slate-200 bg-white p-3"><b>Next:</b><ul class="mt-2 list-disc pl-5">${result.next_actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`;
  }
  if ((result.warnings || []).length) {
    $("validationDecision").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-amber-900"><b>Warnings:</b> ${escapeHtml(result.warnings.slice(0, 5).join(" "))}</div>`;
  }
}

function renderPortfolio() {
  const result = state.portfolio || {};
  const summary = result.summary || {};
  const risk = result.risk_diagnostics || {};
  $("portfolioSummary").innerHTML = metricItems([
    ["Status", summary.status],
    ["Risk Status", summary.portfolio_risk_status || risk.status],
    ["Risk Score", summary.portfolio_risk_score ?? risk.risk_score],
    ["Legs", summary.legs_completed !== undefined ? `${summary.legs_completed}/${summary.legs_requested}` : "--"],
    ["No Data", summary.legs_no_data],
    ["Trades", summary.trade_count],
    ["Win Rate", summary.win_rate !== undefined ? `${(Number(summary.win_rate) * 100).toFixed(1)}%` : "--"],
    ["PF", summary.profit_factor],
    ["Exp R", summary.expectancy_R],
    ["Total R", summary.total_R],
    ["Portfolio DD R", summary.max_drawdown_R],
    ["Net P/L", summary.net_profit !== undefined ? `$${fmt(summary.net_profit)}` : "--"],
    ["ROI", summary.roi_percent !== undefined ? `${fmt(summary.roi_percent)}%` : "--"],
    ["Best Symbol", summary.best_symbol],
    ["Worst Symbol", summary.worst_symbol],
    ["Best TF", summary.best_timeframe],
    ["Worst TF", summary.worst_timeframe],
    ["Robust Regimes", summary.robust_regime_count],
    ["Avg Corr", summary.average_symbol_correlation],
    ["Dominant Currency", summary.dominant_currency],
    ["Max Symbol Share", summary.max_symbol_trade_share !== undefined ? `${(Number(summary.max_symbol_trade_share) * 100).toFixed(1)}%` : "--"],
    ["Max Currency Share", summary.max_currency_exposure_share !== undefined ? `${(Number(summary.max_currency_exposure_share) * 100).toFixed(1)}%` : "--"],
  ]);
  $("portfolioLegsTable").innerHTML = table(
    [
      { label: "Symbol", key: "symbol" },
      { label: "TF", key: "timeframe" },
      { label: "Status", render: (r) => statusBadge(r.status || "--") },
      { label: "Trades", render: (r) => r.summary?.total_trades ?? r.trades ?? 0 },
      { label: "PF", render: (r) => r.summary?.profit_factor ?? "--" },
      { label: "Exp R", render: (r) => r.summary?.expectancy_R ?? "--" },
      { label: "Net P/L", render: (r) => r.summary?.net_profit !== undefined ? `$${fmt(r.summary.net_profit)}` : "--" },
      { label: "Error", key: "error" },
    ],
    result.legs || [],
    "Run portfolio backtest to see each symbol/timeframe leg."
  );
  $("portfolioSymbolTable").innerHTML = table(
    [
      { label: "Symbol", key: "symbol" },
      { label: "Trades", key: "trade_count" },
      { label: "Win", render: (r) => r.win_rate !== undefined ? `${(Number(r.win_rate) * 100).toFixed(1)}%` : "--" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Total R", key: "total_R" },
      { label: "DD R", key: "max_drawdown_R" },
      { label: "Net P/L", render: (r) => r.net_profit !== undefined ? `$${fmt(r.net_profit)}` : "--" },
    ],
    result.symbol_performance || [],
    "Symbol-wise performance appears after portfolio run."
  );
  $("portfolioTimeframeTable").innerHTML = table(
    [
      { label: "TF", key: "timeframe" },
      { label: "Trades", key: "trade_count" },
      { label: "Win", render: (r) => r.win_rate !== undefined ? `${(Number(r.win_rate) * 100).toFixed(1)}%` : "--" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Total R", key: "total_R" },
      { label: "DD R", key: "max_drawdown_R" },
      { label: "Net P/L", render: (r) => r.net_profit !== undefined ? `$${fmt(r.net_profit)}` : "--" },
    ],
    result.timeframe_performance || [],
    "Timeframe-wise performance appears after portfolio run."
  );
  $("portfolioMatrixTable").innerHTML = table(
    [
      { label: "Symbol", key: "symbol" },
      { label: "TF", key: "timeframe" },
      { label: "Status", render: (r) => statusBadge(r.status || "--") },
      { label: "Trades", key: "trade_count" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "DD R", key: "max_drawdown_R" },
      { label: "Best Regime", key: "best_regime" },
    ],
    result.symbol_timeframe_matrix || [],
    "Symbol/timeframe matrix appears after portfolio run."
  );
  $("portfolioRegimeTable").innerHTML = table(
    [
      { label: "Regime", key: "regime_id" },
      { label: "Name", key: "regime_name" },
      { label: "Symbols", key: "symbols_with_trades" },
      { label: "TFs", key: "timeframes_with_trades" },
      { label: "Trades", key: "trade_count" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Robust", render: (r) => statusBadge(r.robust_across_instruments ? "ROBUST" : "RESEARCH") },
    ],
    result.regime_robustness || [],
    "Regime robustness appears after portfolio run."
  );
  $("portfolioRiskChecksTable").innerHTML = table(
    [
      { label: "Check", key: "check" },
      { label: "Status", render: (r) => statusBadge(r.passed ? "PASS" : "FAIL") },
      { label: "Value", key: "value" },
      { label: "Limit", key: "limit" },
      { label: "Severity", key: "severity" },
      { label: "Reason", key: "reason" },
    ],
    risk.checks || [],
    "Portfolio risk checks appear after portfolio run."
  );
  $("portfolioCurrencyExposureTable").innerHTML = table(
    [
      { label: "Currency", key: "currency" },
      { label: "Direction", key: "direction" },
      { label: "Share", render: (r) => r.share !== undefined ? `${(Number(r.share) * 100).toFixed(1)}%` : "--" },
      { label: "Net Weight", key: "net_weight" },
      { label: "Gross Weight", key: "gross_weight" },
      { label: "Trades", key: "trades" },
    ],
    risk.currency_exposure || [],
    "Currency exposure appears after portfolio run."
  );
  $("portfolioDailyRiskTable").innerHTML = table(
    [
      { label: "Date", key: "date" },
      { label: "Trades", key: "trades" },
      { label: "Net R", key: "net_R" },
      { label: "Net P/L", render: (r) => r.net_profit !== undefined ? `$${fmt(r.net_profit)}` : "--" },
    ],
    risk.daily_risk?.rows || [],
    "Daily portfolio risk appears after portfolio run."
  );
  $("portfolioRiskRecommendations").innerHTML = (risk.recommendations || []).length
    ? `<ul class="list-disc pl-5">${risk.recommendations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : `<span class="text-slate-500">Run portfolio backtest to see portfolio risk recommendations.</span>`;
  const messages = [...(result.concentration_warnings || []), ...(result.correlation?.warnings || []), ...(result.warnings || [])];
  if (messages.length) {
    $("portfolioLegsTable").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Portfolio Notes:</b> ${escapeHtml(messages.join(" "))}</div>`;
  }
}

function parseCsv(id, fallback = []) {
  const raw = String($(id)?.value || "").trim();
  if (!raw) return fallback;
  return raw.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseNumberCsv(id, fallback = []) {
  const values = parseCsv(id).map(Number).filter((value) => Number.isFinite(value));
  return values.length ? values : fallback;
}

function selectedCalibrationRegime() {
  const regime = $("regimeFilter")?.value || state.selectedRegimeId || "ALL";
  return regime === "ALL" && state.selectedRegimeId ? state.selectedRegimeId : regime;
}

function currentCalibrationPayload() {
  const profile = $("calibrationProfile")?.value || "balanced";
  const regimeId = selectedCalibrationRegime();
  const raw = {
    adx_min: $("calAdxMin")?.value,
    adx_max: $("calAdxMax")?.value,
    er_min: $("calErMin")?.value,
    er_max: $("calErMax")?.value,
    atr_percentile_min: $("calAtrMin")?.value,
    atr_percentile_max: $("calAtrMax")?.value,
    max_spread_percentile: $("calSpreadMax")?.value,
    min_alpha_score: $("calMinAlpha")?.value,
    range_edge_tolerance_atr: $("calRangeEdge")?.value,
    candle_range_atr_min: $("calCandleMin")?.value,
    candle_range_atr_max: $("calCandleMax")?.value,
    upper_wick_min: $("calUpperWick")?.value,
    lower_wick_min: $("calLowerWick")?.value,
    vwap_distance_atr_min: $("calVwapDistance")?.value,
    macro_confidence_min: $("calMacroConfidence")?.value,
    confidence_min: $("calConfidenceMin")?.value,
  };
  const override = {};
  Object.entries(raw).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      override[key] = Number(value);
    }
  });
  const overrides = {};
  if (regimeId && regimeId !== "ALL" && Object.keys(override).length) {
    overrides[regimeId] = override;
  }
  return {
    profile,
    target_regime: regimeId,
    overrides,
  };
}

function profileForCalibration() {
  const profile = $("calibrationProfile")?.value || "balanced";
  return (state.calibrationProfiles || []).find((item) => item.profile === profile) || {};
}

function renderCalibration() {
  const profile = profileForCalibration();
  const target = selectedCalibrationRegime();
  const profileValues = target !== "ALL" ? profile.regimes?.[target] : null;
  const latest = state.backtest?.calibration_summary || null;
  const payload = currentCalibrationPayload();
  $("calibrationPreview").innerHTML = `
    <div class="grid gap-3 xl:grid-cols-3">
      <div>
        <div class="text-xs font-bold uppercase text-emerald-700">Active Profile</div>
        <div class="font-semibold">${escapeHtml(profile.name || payload.profile)}</div>
        <p class="mt-1 text-slate-600">${escapeHtml(profile.meaning || "Profile loaded from API.")}</p>
      </div>
      <div>
        <div class="text-xs font-bold uppercase text-emerald-700">Target Regime</div>
        <div class="font-semibold">${escapeHtml(target || "ALL")}</div>
        <p class="mt-1 text-slate-600">${profileValues ? escapeHtml(JSON.stringify(profileValues)) : "ALL run: profile values apply per detector where supported."}</p>
      </div>
      <div>
        <div class="text-xs font-bold uppercase text-emerald-700">Last Backtest Calibration</div>
        <div class="font-semibold">${escapeHtml(latest?.name || "--")}</div>
        <p class="mt-1 text-slate-600">${escapeHtml(latest?.meaning || "Run a backtest to confirm resolved calibration in the response.")}</p>
      </div>
    </div>
    <details class="mt-3">
      <summary class="cursor-pointer font-semibold text-emerald-800">Request calibration JSON</summary>
      <pre class="mt-2 overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-100">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
    </details>`;
}

function setJsonEditor(id, value) {
  const el = $(id);
  if (el) el.value = JSON.stringify(value || {}, null, 2);
}

function splitRiskCostPayload(payload) {
  return {
    costs: payload.costs || {},
    risk_controls: payload.risk_controls || {},
    execution_assumption: payload.execution_assumption || {},
    statistical_regime: payload.statistical_regime || {},
    data_source_controls: payload.data_source_controls || {},
  };
}

function loadCurrentValuesIntoProfileEditor(payload = currentPayload()) {
  $("valueProfileName").value = `${payload.regime_filter || "ALL"} ${payload.strategy_filter || "ALL"} ${payload.symbol || ""} ${payload.timeframe || ""}`.trim();
  setJsonEditor("valueProfileFiltersJson", payload.filters || {});
  setJsonEditor("valueProfilePatternJson", payload.pattern_engine || {});
  setJsonEditor("valueProfileRegimeControlsJson", payload.regime_controls || {});
  setJsonEditor("valueProfileStrategyControlsJson", payload.strategy_controls || {});
  setJsonEditor("valueProfileCalibrationJson", payload.calibration || {});
  setJsonEditor("valueProfileRiskCostJson", splitRiskCostPayload(payload));
  renderValueProfiles();
}

function editedValueProfilePayload() {
  const base = currentPayload();
  const riskCost = parseJsonEditor("valueProfileRiskCostJson", {});
  return {
    ...base,
    filters: parseJsonEditor("valueProfileFiltersJson", base.filters || {}),
    pattern_engine: parseJsonEditor("valueProfilePatternJson", base.pattern_engine || {}),
    regime_controls: parseJsonEditor("valueProfileRegimeControlsJson", base.regime_controls || {}),
    strategy_controls: parseJsonEditor("valueProfileStrategyControlsJson", base.strategy_controls || {}),
    calibration: parseJsonEditor("valueProfileCalibrationJson", base.calibration || {}),
    costs: riskCost.costs || base.costs || {},
    risk_controls: riskCost.risk_controls || base.risk_controls || {},
    execution_assumption: riskCost.execution_assumption || base.execution_assumption || {},
    statistical_regime: riskCost.statistical_regime || base.statistical_regime || {},
    data_source_controls: riskCost.data_source_controls || base.data_source_controls || {},
  };
}

function profileMetricsSnapshot() {
  return {
    backtest_summary: state.backtest?.summary || {},
    optimizer_summary: state.optimizer?.summary || {},
    monthly_sweep_summary: state.monthlyResearch?.summary || {},
    final_approval: state.finalApproval?.summary || state.finalApproval || {},
  };
}

function applyProfilePayloadToVisibleControls(payload) {
  if (!payload || typeof payload !== "object") return;
  if (payload.symbol && $("symbol")) $("symbol").value = payload.symbol;
  if (payload.timeframe && $("timeframe")) $("timeframe").value = payload.timeframe;
  if (payload.start_date && $("startDate")) $("startDate").value = String(payload.start_date).slice(0, 10);
  if (payload.end_date && $("endDate")) $("endDate").value = String(payload.end_date).slice(0, 10);
  if (payload.regime_filter && $("regimeFilter")) {
    $("regimeFilter").value = payload.regime_filter;
    updateStrategyFilterForRegime(payload.regime_filter, payload.strategy_filter || "ALL");
  }
  if (payload.strategy_filter && $("strategyFilter")) $("strategyFilter").value = payload.strategy_filter;
  if (payload.rr !== undefined && $("rr")) $("rr").value = String(payload.rr);
  if (payload.risk_percent !== undefined && $("riskPercent")) $("riskPercent").value = String(payload.risk_percent);
  if (payload.initial_equity !== undefined && $("initialEquity")) $("initialEquity").value = String(payload.initial_equity);
  if (payload.sentiment && $("sentiment")) $("sentiment").value = payload.sentiment;
  if (payload.usd_bias && $("usdBias")) $("usdBias").value = payload.usd_bias;
  if (payload.risk_sentiment && $("riskSentiment")) $("riskSentiment").value = payload.risk_sentiment;
  if (payload.cb_divergence && $("cbDivergence")) $("cbDivergence").value = payload.cb_divergence;

  const f = payload.filters || {};
  if (f.use_killzone !== undefined) $("useKillzone").checked = Boolean(f.use_killzone);
  if (f.killzone_mode && $("killzoneMode")) $("killzoneMode").value = f.killzone_mode;
  if (f.use_spread_filter !== undefined) $("useSpreadFilter").checked = Boolean(f.use_spread_filter);
  if (f.spread_filter_mode && $("spreadFilterMode")) $("spreadFilterMode").value = f.spread_filter_mode;
  if (f.max_spread_percentile !== undefined) $("maxSpreadPercentile").value = f.max_spread_percentile;
  if (f.use_alpha !== undefined) $("useAlpha").checked = Boolean(f.use_alpha);
  if (f.alpha_mode && $("alphaMode")) $("alphaMode").value = f.alpha_mode;
  if (f.min_alpha_score !== undefined) $("minAlphaScore").value = f.min_alpha_score;
  if (f.strict_regime_validation !== undefined) $("strictRegimeValidation").checked = Boolean(f.strict_regime_validation);
  if (f.strict_regime_max_failed_conditions !== undefined) $("strictRegimeMaxFailed").value = f.strict_regime_max_failed_conditions;
  if (f.strict_regime_min_confidence !== undefined) $("strictRegimeMinConfidence").value = f.strict_regime_min_confidence;
  if (f.min_clean_trend_er !== undefined) $("minCleanTrendEr").value = f.min_clean_trend_er;
  if (f.clean_trend_adx_min !== undefined) $("cleanTrendAdxMin").value = f.clean_trend_adx_min;
  if (f.clean_trend_adx_max !== undefined) $("cleanTrendAdxMax").value = f.clean_trend_adx_max;

  const p = payload.pattern_engine || {};
  if (p.use_patterns !== undefined) $("usePatterns").checked = Boolean(p.use_patterns);
  if (p.use_ict !== undefined) $("useIct").checked = Boolean(p.use_ict);
  if (p.use_fvg !== undefined) $("useFvg").checked = Boolean(p.use_fvg);
  if (p.use_order_blocks !== undefined) $("useOrderBlocks").checked = Boolean(p.use_order_blocks);
  if (p.use_bos !== undefined) $("useBos").checked = Boolean(p.use_bos);
  if (p.use_mss !== undefined) $("useMss").checked = Boolean(p.use_mss);
  if (p.use_liquidity_pools !== undefined) $("useLiquidityPools").checked = Boolean(p.use_liquidity_pools);
  if (p.use_round_numbers !== undefined) $("useRoundNumbers").checked = Boolean(p.use_round_numbers);
  if (p.use_vwap !== undefined) $("useVwap").checked = Boolean(p.use_vwap);
  if (p.use_mvwap !== undefined || p.use_moving_vwap !== undefined) $("useMvwap").checked = Boolean(p.use_mvwap ?? p.use_moving_vwap);
  if (p.use_session_vwap !== undefined) $("useSessionVwap").checked = Boolean(p.use_session_vwap);
  if (p.pattern_score_mode && $("patternScoreMode")) $("patternScoreMode").value = p.pattern_score_mode;
  if (p.min_pattern_score !== undefined) $("minPatternScore").value = p.min_pattern_score;
  if (p.fvg_min_size_atr !== undefined) $("fvgMinSizeAtr").value = p.fvg_min_size_atr;
  if (p.fvg_max_age_bars !== undefined) $("fvgMaxAgeBars").value = p.fvg_max_age_bars;

  const rc = payload.regime_controls || {};
  if (rc.use_regime_hysteresis !== undefined) $("useRegimeHysteresis").checked = Boolean(rc.use_regime_hysteresis);
  if (rc.hysteresis_confirm_bars !== undefined) $("hysteresisConfirmBars").value = rc.hysteresis_confirm_bars;
  if (rc.hysteresis_confidence_margin !== undefined) $("hysteresisConfidenceMargin").value = rc.hysteresis_confidence_margin;

  const sc = payload.strategy_controls || {};
  if (sc.use_stop_realism !== undefined) $("useStopRealism").checked = Boolean(sc.use_stop_realism);
  if (sc.use_symbol_session_stop_profile !== undefined) $("useSymbolSessionStopProfile").checked = Boolean(sc.use_symbol_session_stop_profile);
  if (sc.stop_atr_override !== undefined && sc.stop_atr_override !== null) $("stopAtrOverride").value = sc.stop_atr_override;
  if (sc.stop_override_mode && $("stopOverrideMode")) $("stopOverrideMode").value = sc.stop_override_mode;
  if (sc.min_effective_stop_spread_mult !== undefined) $("minEffectiveStopSpreadMult").value = sc.min_effective_stop_spread_mult;
  if (sc.min_effective_stop_mode && $("minEffectiveStopMode")) $("minEffectiveStopMode").value = sc.min_effective_stop_mode;

  const c = payload.costs || {};
  if (c.cost_mode && $("costMode")) $("costMode").value = c.cost_mode;
  if (c.cost_r_per_trade !== undefined) $("fixedCostR").value = c.cost_r_per_trade;
  if (c.commission_R !== undefined) $("commissionR").value = c.commission_R;
  if (c.slippage_points !== undefined) $("slippagePoints").value = c.slippage_points;
  if (c.spread_round_trip_factor !== undefined) $("spreadRoundTripFactor").value = c.spread_round_trip_factor;
  if (c.news_cost_multiplier !== undefined) $("newsCostMultiplier").value = c.news_cost_multiplier;
  if (c.mt5_imported_cost_R !== undefined) $("mt5ImportedCostR").value = c.mt5_imported_cost_R;
  if (c.rollover_block !== undefined) $("rolloverCostBlock").checked = Boolean(c.rollover_block);

  const cal = payload.calibration || {};
  if (cal.profile && $("calibrationProfile")) $("calibrationProfile").value = cal.profile;
  renderCalibration();
}

function renderValueProfiles() {
  const active = state.activeValueProfile;
  $("activeValueProfileBadge").innerHTML = active
    ? `<b>Active:</b> ${escapeHtml(active.name || active.profile_id)}<br><span class="text-xs">${escapeHtml(active.profile_id || "")}</span>`
    : "No active saved values profile.";
  let preview = {};
  try {
    preview = editedValueProfilePayload();
  } catch (err) {
    $("valueProfilePayloadPreview").innerHTML = `<div class="text-red-700">${escapeHtml(err.message)}</div>`;
    return;
  }
  $("valueProfilePayloadPreview").innerHTML = jsonBlock(preview);
  $("savedValueProfilesPanel").innerHTML = table(
    [
      { label: "Profile", render: (r) => `<button class="text-blue-700 underline" data-value-profile-id="${escapeHtml(r.profile_id)}">${escapeHtml(r.name || String(r.profile_id || "").slice(0, 8))}</button>` },
      { label: "Regime", key: "regime_filter" },
      { label: "Strategy", key: "strategy_filter" },
      { label: "Symbol", key: "symbol" },
      { label: "TF", key: "timeframe" },
      { label: "Source", key: "source_type" },
      { label: "Updated", key: "updated_at" },
    ],
    state.savedValueProfiles || [],
    "Save or load research value profiles to reuse edited strategy/regime/pattern values."
  );
}

function renderOptimizer() {
  const result = state.optimizer || {};
  const summary = result.summary || {};
  $("optimizerSummary").innerHTML = metricItems([
    ["Requested", summary.combinations_requested],
    ["Run", summary.combinations_run],
    ["Approved", summary.approved_candidates],
    ["Watchlist", summary.watchlist_candidates],
    ["Best Score", summary.best_score],
    ["Best Regime", summary.best_regime],
    ["Best Strategy", summary.best_strategy],
    ["Min Trades", summary.min_trades],
    ["Min PF", summary.min_profit_factor],
    ["Max DD R", summary.max_drawdown_r],
    ["Validated", summary.validated_candidates],
    ["Validation Runs", summary.validation_runs],
    ["Saved Passed", summary.saved_validated_candidates],
    ["Cache Hits", summary.feature_cache_hits],
    ["Cache Misses", summary.feature_cache_misses],
    ["Cache Hit Rate", summary.feature_cache_hit_rate !== undefined ? `${(Number(summary.feature_cache_hit_rate) * 100).toFixed(1)}%` : "--"],
  ]);
  $("optimizerTable").innerHTML = table(
    [
      { label: "Rank", key: "rank" },
      { label: "Regime", key: "regime_filter" },
      { label: "Strategy", key: "strategy_filter" },
      { label: "RR", key: "rr" },
      { label: "Alpha", key: "min_alpha_score" },
      { label: "Spread", key: "max_spread_percentile" },
      { label: "Cal", key: "calibration_profile" },
      { label: "Cache", render: (r) => r.feature_cache_status ? `${r.feature_cache_status}${r.feature_cache_hit ? " hit" : ""}` : "--" },
      { label: "KZ", key: "killzone_mode" },
      { label: "Pattern", render: (r) => `${r.pattern_score_mode} / ${r.min_pattern_score}` },
      { label: "Trades", key: "total_trades" },
      { label: "Win", render: (r) => r.win_rate !== undefined ? `${(Number(r.win_rate) * 100).toFixed(1)}%` : "--" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "T", key: "edge_t_stat" },
      { label: "P", key: "edge_p_value_approx" },
      { label: "Wilson", render: (r) => r.win_rate_wilson_lower_95 !== undefined ? `${(Number(r.win_rate_wilson_lower_95) * 100).toFixed(1)}%` : "--" },
      { label: "Stat", key: "statistical_edge" },
      { label: "Total R", key: "total_R" },
      { label: "DD", key: "max_drawdown_R" },
      { label: "Score", key: "optimizer_score" },
      { label: "OOS", render: (r) => r.oos_status ? `${r.oos_status} PF:${fmt(r.oos_pf)} E:${fmt(r.oos_expectancy_R)}` : "--" },
      { label: "WF", render: (r) => r.wf_pass_rate !== undefined ? `${(Number(r.wf_pass_rate) * 100).toFixed(0)}% / ${fmt(r.wf_efficiency)}` : "--" },
      { label: "MC", render: (r) => r.mc_status ? `${r.mc_status} loss:${r.mc_loss_probability !== undefined ? `${(Number(r.mc_loss_probability) * 100).toFixed(0)}%` : "--"} dd:${r.mc_drawdown_breach_probability !== undefined ? `${(Number(r.mc_drawdown_breach_probability) * 100).toFixed(0)}%` : "--"}` : "--" },
      { label: "Validated", render: (r) => r.validation_status ? statusBadge(r.validation_status) : "--" },
      { label: "Failed Checks", render: (r) => (r.validation_failed_check_names || []).join(", ") || fmt(r.failed_validation_checks) },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    result.results || [],
    "Run optimizer grid to rank candidate regime/strategy/filter combinations."
  );
  if ((result.warnings || []).length) {
    $("optimizerTable").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Warnings:</b> ${escapeHtml(result.warnings.join(" "))}</div>`;
  }
}

function renderMonthlyResearch() {
  const result = state.monthlyResearch || {};
  const summary = result.summary || {};
  $("monthlySweepSummary").innerHTML = metricItems([
    ["DB Run", result.monthly_sweep_run_id ? String(result.monthly_sweep_run_id).slice(0, 8) : "--"],
    ["DB Saved", result.monthly_sweep_saved === undefined ? "--" : result.monthly_sweep_saved ? "Yes" : "No"],
    ["Saved Rows", result.saved_candidate_count],
    ["Status", summary.status],
    ["Symbol", summary.symbol],
    ["TF", summary.timeframe],
    ["Months", summary.months_tested],
    ["Regimes", summary.regimes_tested],
    ["Optimizer Runs", summary.optimizer_runs],
    ["Worked", summary.worked_candidates],
    ["Failed", summary.failed_regime_months],
    ["Best Month", summary.best_month],
    ["Best Regime", summary.best_regime],
    ["Best Strategy", summary.best_strategy],
    ["Best Profit", summary.best_net_profit],
  ]);
  $("monthlySweepWorkedTable").innerHTML = table(
    [
      { label: "Month", key: "month" },
      { label: "Regime", render: (r) => `${r.regime_id} ${r.regime_name || ""}` },
      { label: "Strategy", render: (r) => `${r.strategy_id} ${r.strategy_name || ""}` },
      { label: "Trades", key: "total_trades" },
      { label: "Win", render: (r) => r.win_rate !== undefined ? `${(Number(r.win_rate) * 100).toFixed(1)}%` : "--" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "DD R", key: "max_drawdown_R" },
      { label: "Net", key: "net_profit" },
      { label: "Stop ATR", key: "stop_atr" },
      { label: "Stop/Spread", key: "min_effective_stop_spread_mult" },
      { label: "Pattern", render: (r) => `${r.pattern_mode || "--"} / ${r.min_pattern_score ?? "--"}` },
      { label: "Profile", key: "calibration_profile" },
      { label: "Status", render: (r) => statusBadge(r.status || r.optimizer_status) },
    ],
    (result.worked_candidates || []).slice(0, 80),
    "Run Monthly Sweep to save and display only month/regime candidates that passed profitability and sample gates."
  );
  $("monthlySweepFailureTable").innerHTML = table(
    [
      { label: "Failure", key: "failure_bucket" },
      { label: "Count", key: "count" },
    ],
    result.failure_diagnostics || [],
    "No failure diagnostics yet."
  );
  $("monthlySweepRobustnessTable").innerHTML = table(
    [
      { label: "Regime", render: (r) => `${r.regime_id} ${r.regime_name || ""}` },
      { label: "Worked Months", key: "months_with_candidate" },
      { label: "Failed Months", key: "months_failed" },
      { label: "Pass Rate", render: (r) => `${(Number(r.monthly_pass_rate || 0) * 100).toFixed(1)}%` },
    ],
    (result.regime_robustness || []).slice(0, 80),
    "Run Monthly Sweep to see month-by-month robustness by regime."
  );
  if ((result.warnings || []).length) {
    $("monthlySweepWorkedTable").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Warnings:</b> ${escapeHtml(result.warnings.join(" "))}</div>`;
  }
  $("savedMonthlySweepsPanel").innerHTML = table(
    [
      { label: "Run", render: (r) => `<button class="text-blue-700 underline" data-monthly-sweep-run-id="${escapeHtml(r.monthly_sweep_run_id)}">${escapeHtml(String(r.monthly_sweep_run_id || "").slice(0, 8))}</button>` },
      { label: "Status", render: (r) => statusBadge(r.status || r.summary?.status) },
      { label: "Symbol", key: "symbol" },
      { label: "TF", key: "timeframe" },
      { label: "Dates", render: (r) => `${r.start_date || "--"} -> ${r.end_date || "--"}` },
      { label: "Months", key: "months_back" },
      { label: "Regimes", key: "regimes_tested" },
      { label: "Worked", key: "worked_candidate_count" },
      { label: "Failed", key: "failed_regime_months" },
      { label: "Created", key: "created_at" },
    ],
    state.savedMonthlySweeps || [],
    "Run or load saved monthly sweeps to review persisted DB research rows."
  );
}

function renderMonteCarlo() {
  const result = state.monteCarlo || {};
  const summary = result.summary || {};
  const observed = result.observed || {};
  const risk = result.risk_of_ruin || {};
  $("monteCarloSummary").innerHTML = metricItems([
    ["Status", summary.status],
    ["Trades", summary.source_trades],
    ["Sims", summary.simulations],
    ["Mode", summary.sample_mode],
    ["Risk %", summary.risk_percent],
    ["P05 Equity", summary.p05_ending_equity !== undefined ? `$${fmt(summary.p05_ending_equity)}` : "--"],
    ["Median Equity", summary.median_ending_equity !== undefined ? `$${fmt(summary.median_ending_equity)}` : "--"],
    ["P95 Equity", summary.p95_ending_equity !== undefined ? `$${fmt(summary.p95_ending_equity)}` : "--"],
    ["P05 Total R", summary.p05_total_R],
    ["Median Total R", summary.median_total_R],
    ["Median DD %", summary.median_max_drawdown_percent],
    ["Worst 5% DD %", summary.worst_5pct_max_drawdown_percent],
    ["Profit Prob", summary.probability_profit !== undefined ? `${(Number(summary.probability_profit) * 100).toFixed(1)}%` : "--"],
    ["Loss Prob", summary.probability_loss !== undefined ? `${(Number(summary.probability_loss) * 100).toFixed(1)}%` : "--"],
    ["DD Breach", summary.probability_drawdown_breach !== undefined ? `${(Number(summary.probability_drawdown_breach) * 100).toFixed(1)}%` : "--"],
    ["Streak Breach", summary.probability_losing_streak_breach !== undefined ? `${(Number(summary.probability_losing_streak_breach) * 100).toFixed(1)}%` : "--"],
  ]);
  const rows = [
    { metric: "Observed", total_R: observed.total_R, max_drawdown_R: observed.max_drawdown_R, max_losing_streak: observed.max_losing_streak, ending_equity: observed.ending_equity, probability: "--" },
    { metric: "Risk of Loss", total_R: "--", max_drawdown_R: "--", max_losing_streak: "--", ending_equity: "--", probability: risk.loss_probability !== undefined ? `${(Number(risk.loss_probability) * 100).toFixed(1)}%` : "--" },
    { metric: "Drawdown Breach", total_R: "--", max_drawdown_R: "--", max_losing_streak: "--", ending_equity: "--", probability: risk.drawdown_breach_probability !== undefined ? `${(Number(risk.drawdown_breach_probability) * 100).toFixed(1)}%` : "--" },
    { metric: "Streak Breach", total_R: "--", max_drawdown_R: "--", max_losing_streak: "--", ending_equity: "--", probability: risk.losing_streak_breach_probability !== undefined ? `${(Number(risk.losing_streak_breach_probability) * 100).toFixed(1)}%` : "--" },
  ];
  $("monteCarloTable").innerHTML = table(
    [
      { label: "Metric", key: "metric" },
      { label: "Total R", key: "total_R" },
      { label: "Max DD R", key: "max_drawdown_R" },
      { label: "Max Loss Streak", key: "max_losing_streak" },
      { label: "Ending Equity", render: (r) => typeof r.ending_equity === "number" ? `$${fmt(r.ending_equity)}` : fmt(r.ending_equity) },
      { label: "Probability", key: "probability" },
    ],
    result.summary ? rows : [],
    "Run Monte Carlo to stress-test the selected setup's trade-order and drawdown risk."
  );
  const messages = [...(result.reasons || []), ...(result.warnings || [])];
  if (messages.length) {
    $("monteCarloTable").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Review:</b> ${escapeHtml(messages.join(" "))}</div>`;
  }
  renderMonteCarloChart();
}

function renderMt5Import() {
  const result = state.mt5Import || {};
  const summary = result.summary || {};
  const comparison = result.model_comparison_row || {};
  $("mt5ImportSummary").innerHTML = metricItems([
    ["Import", result.import_id ? String(result.import_id).slice(0, 8) : "--"],
    ["Model", result.test_model],
    ["Symbol", result.symbol],
    ["TF", result.timeframe],
    ["Raw Rows", summary.raw_deal_rows],
    ["Trades", summary.trade_count],
    ["Win Rate", summary.win_rate !== undefined ? `${(Number(summary.win_rate) * 100).toFixed(1)}%` : "--"],
    ["PF", summary.profit_factor],
    ["Net P/L", summary.net_profit !== undefined ? `$${fmt(summary.net_profit)}` : "--"],
    ["Max DD $", summary.max_drawdown_currency !== undefined ? `$${fmt(summary.max_drawdown_currency)}` : "--"],
    ["Max Loss Streak", summary.max_losing_streak],
    ["Exp R", summary.expectancy_R ?? summary.approx_expectancy_R],
    ["Total R", summary.total_R ?? summary.approx_total_R],
    ["Max DD R", summary.max_drawdown_R ?? summary.approx_max_drawdown_R],
    ["R Source", summary.result_r_source],
    ["Exact R Rows", summary.exact_r_count],
    ["Avg Alpha", summary.average_alpha_score],
    ["Avg Pattern", summary.average_pattern_score],
    ["Avg Final", summary.average_final_score],
    ["Pattern Rows", summary.pattern_detail_rows],
    ["Python Matches", result.python_enrichment?.matched],
  ]);
  $("mt5ImportTable").innerHTML = table(
    [
      { label: "Model", render: (r) => r.model_name || r.model },
      { label: "Trades", key: "trade_count" },
      { label: "Win", render: (r) => r.win_rate !== undefined ? `${(Number(r.win_rate) * 100).toFixed(1)}%` : "--" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Net P/L", render: (r) => r.net_profit !== undefined ? `$${fmt(r.net_profit)}` : "--" },
      { label: "Py Trades", key: "python_trade_count" },
      { label: "PF Delta", key: "profit_factor_delta" },
      { label: "Exp Delta", key: "expectancy_R_delta" },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    result.model_comparison_row ? [comparison] : [],
    "Import an MT5 Strategy Tester report to create a real-tick/model-comparison row."
  );
  $("mt5ImportDeals").innerHTML = table(
    [
      { label: "Time", key: "time" },
      { label: "Symbol", key: "symbol" },
      { label: "Type", key: "deal_type" },
      { label: "Dir", key: "direction" },
      { label: "Volume", key: "volume" },
      { label: "Price", render: (r) => formatPrice(r.symbol, r.price) },
      { label: "Commission", key: "commission" },
      { label: "Swap", key: "swap" },
      { label: "Profit", render: (r) => `$${fmt(r.profit)}` },
      { label: "R", key: "result_R" },
      { label: "R Source", key: "result_R_source" },
      { label: "Initial Risk", render: (r) => r.initial_risk !== undefined ? `$${fmt(r.initial_risk)}` : "--" },
      { label: "Regime", key: "regime_id" },
      { label: "Strategy", key: "strategy_id" },
      { label: "Alpha", key: "alpha_score" },
      { label: "Pattern Score", key: "pattern_score" },
      { label: "Final Score", key: "final_score" },
      { label: "Patterns", render: (r) => compactPatterns(r.patterns_detected || []) },
      { label: "Balance", render: (r) => r.balance !== undefined ? `$${fmt(r.balance)}` : "--" },
      { label: "Reason", key: "setup_reason" },
      { label: "Comment", key: "comment" },
    ],
    (result.deals || []).slice(0, 200),
    "Imported deals will appear here."
  );
  if ((result.warnings || []).length) {
    $("mt5ImportTable").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Import Notes:</b> ${escapeHtml(result.warnings.join(" "))}</div>`;
  }
  if ((summary.top_patterns || []).length) {
    $("mt5ImportTable").innerHTML += `<div class="mt-4">${table(
      [
        { label: "Pattern", key: "pattern_id" },
        { label: "Imported Rows", key: "count" },
      ],
      summary.top_patterns,
      "No imported pattern rows yet."
    )}</div>`;
  }
}

function renderMt5Tester() {
  const result = state.mt5Tester || {};
  const config = result.tester_config || {};
  const pySignals = result.python_signal_source || {};
  $("mt5TesterSummary").innerHTML = metricItems([
    ["Status", result.status || "--"],
    ["Run", result.run_id ? String(result.run_id).slice(0, 8) : "--"],
    ["Model", config.test_model || "--"],
    ["Expert", config.expert || "--"],
    ["Python Signals", pySignals.expected_trade_count !== undefined ? pySignals.expected_trade_count : "--"],
    ["Terminal", result.terminal_path ? "configured" : "missing"],
    ["Process", result.process_id || "--"],
    ["Report Import", result.report_import ? "yes" : "no"],
    ["Order Execution", result.order_execution ? "yes" : "no"],
  ]);
  const rows = [
    { item: "EA source", value: config.ea_source_path },
    { item: "Compiled EA expected", value: config.compiled_ea_expected },
    { item: "INI file", value: config.ini_path },
    { item: "SET file", value: config.set_path },
    { item: "Python signal CSV", value: pySignals.file_path },
    { item: "MT5 Common signal copy", value: pySignals.common_file_path },
    { item: "Python run id", value: pySignals.python_run_id },
    { item: "Report path", value: config.report_path },
    { item: "MT5 command", value: (result.command || []).join(" ") },
    { item: "Terminal path", value: result.terminal_path },
  ].filter((row) => row.value);
  $("mt5TesterConfig").innerHTML = table(
    [
      { label: "Item", key: "item" },
      { label: "Value", render: (r) => `<code class="break-all">${escapeHtml(r.value)}</code>` },
    ],
    rows,
    "Run MT5 Tester to generate the tester .ini/.set files."
  );
  if ((result.warnings || []).length) {
    $("mt5TesterConfig").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>MT5 Tester Notes:</b> ${escapeHtml(result.warnings.join(" "))}</div>`;
  }
}

function renderMt5Parity() {
  const packet = state.mt5ParityPacket || {};
  const parity = state.mt5Parity || {};
  const completion = state.mt5ParityCompletion || {};
  const verdict = completion.institutional_verdict || {};
  const summary = parity.summary || {};
  $("mt5ParityCompletionSummary").innerHTML = metricItems([
    ["Proof Status", completion.status || "--"],
    ["Proved", verdict.proved === true ? "yes" : verdict.proved === false ? "no" : "--"],
    ["Proof Run", completion.python_run_id || "--"],
    ["Candidate", completion.candidate ? `${completion.candidate.symbol || "--"} ${completion.candidate.timeframe || "--"}` : "--"],
    ["Tester", completion.tester_run?.status || "--"],
    ["Report", completion.mt5_import?.import_id || "--"],
  ]);
  $("mt5ParityChecklist").innerHTML = table(
    [
      { label: "Check", key: "check" },
      { label: "Passed", render: (r) => statusBadge(r.passed ? "PASS" : "WAITING") },
      { label: "Detail", key: "detail" },
    ],
    completion.checklist || [],
    "Run Complete Parity Proof to see the institutional checklist."
  );
  $("mt5ParitySummary").innerHTML = metricItems([
    ["Packet", packet.packet_id || "--"],
    ["Expected Trades", packet.expected_trade_count],
    ["Parity Status", parity.status || "--"],
    ["Python Trades", summary.python_trade_count],
    ["MT5 Trades", summary.mt5_trade_count],
    ["Matched", summary.matched_trade_count],
    ["Mismatches", summary.mismatch_count],
    ["Pass Rate", summary.pass_rate !== undefined ? `${(Number(summary.pass_rate) * 100).toFixed(1)}%` : "--"],
  ]);
  const rows = parity.mismatches?.length
    ? parity.mismatches
    : (packet.expected_signals || []).slice(0, 25).map((r) => ({ ...r, type: "EXPECTED_SIGNAL" }));
  $("mt5ParityTable").innerHTML = table(
    [
      { label: "Type", render: (r) => r.type || "MISMATCH" },
      { label: "Index", render: (r) => r.parity_index ?? r.index ?? "--" },
      { label: "Hash", render: (r) => r.parity_hash || r.python_trade?.parity_hash || r.mt5_trade?.parity_hash || "--" },
      { label: "Regime", render: (r) => r.regime_id || r.python_trade?.regime_id || r.mt5_trade?.regime_id || "--" },
      { label: "Strategy", render: (r) => r.strategy_id || r.python_trade?.strategy_id || r.mt5_trade?.strategy_id || "--" },
      { label: "Direction", render: (r) => r.direction || r.python_trade?.direction || r.mt5_trade?.direction || "--" },
      { label: "Entry", render: (r) => formatPrice(r.symbol || r.python_trade?.raw?.symbol || r.mt5_trade?.symbol, r.entry || r.python_trade?.entry || r.mt5_trade?.entry) },
      { label: "Failed Fields", render: (r) => (r.failed_fields || []).map((f) => f.field).join(", ") || "--" },
      { label: "Comment", render: (r) => r.comment || r.mt5_trade?.comment || "--" },
    ],
    rows,
    "Build a parity packet after a saved Python run, then import/check MT5 tester output with PYIDX/PYHASH columns."
  );
  const notes = [...(packet.warnings || []), ...(parity.warnings || [])];
  if ((completion.next_actions || []).length) {
    $("mt5ParityTable").innerHTML += `<div class="mt-3 rounded border border-sky-200 bg-sky-50 p-3 text-sm text-sky-950"><b>Next actions:</b> ${escapeHtml(completion.next_actions.join(" "))}</div>`;
  }
  if (notes.length) {
    $("mt5ParityTable").innerHTML += `<div class="mt-3 rounded border border-indigo-200 bg-white p-3 text-sm text-indigo-950"><b>Parity Notes:</b> ${escapeHtml(notes.join(" "))}</div>`;
  }
}

function renderMt5ComparisonImport() {
  const result = state.mt5Comparison || {};
  const stability = result.stability || {};
  const diagnostics = result.diagnostics || {};
  const decision = result.decision || {};
  $("mt5ComparisonSummary").innerHTML = metricItems([
    ["Status", result.status || "--"],
    ["Verdict", decision.status || diagnostics.verdict || "--"],
    ["Final Review", decision.can_promote_to_final_review === undefined ? "--" : decision.can_promote_to_final_review ? "yes" : "no"],
    ["Comparison", result.comparison_id ? String(result.comparison_id).slice(0, 8) : "--"],
    ["Imported", result.imports ? Object.keys(result.imports).length : 0],
    ["Missing", (result.missing_models || []).join(", ") || "--"],
    ["PF Drift", stability.profit_factor_drift_1m_to_real_ticks],
    ["Exp Drift", stability.expectancy_drift_1m_to_real_ticks],
    ["Trade Drift", stability.trade_count_drift_pct_1m_to_real_ticks],
    ["Net Drift", stability.net_profit_drift_pct_1m_to_real_ticks],
  ]);
  const decisionTone = decision.can_promote_to_final_review
    ? "border-emerald-200 bg-emerald-50 text-emerald-950"
    : decision.status || diagnostics.verdict
      ? "border-amber-200 bg-amber-50 text-amber-950"
      : "border-slate-200 bg-white text-slate-600";
  $("mt5ComparisonDecision").innerHTML = `
    <div class="rounded border ${decisionTone} p-3 text-sm">
      <div class="flex flex-wrap items-center gap-2">
        <b>Real Tick Verdict:</b> ${statusBadge(decision.status || diagnostics.verdict || "WAITING")}
        <span>Real Tick Trades: <b>${escapeHtml(diagnostics.real_tick_trade_count ?? "--")}</b></span>
        <span>Real Tick PF: <b>${escapeHtml(diagnostics.real_tick_profit_factor ?? "--")}</b></span>
        <span>Real Tick Exp R: <b>${escapeHtml(diagnostics.real_tick_expectancy_R ?? "--")}</b></span>
      </div>
      ${decision.message ? `<div class="mt-2">${escapeHtml(decision.message)}</div>` : ""}
      ${(result.next_actions || []).length ? `<ul class="mt-2 list-disc pl-5">${result.next_actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
    </div>
  `;
  $("mt5ComparisonModels").innerHTML = table(
    [
      { label: "Model", render: (r) => r.model_name || r.model },
      { label: "Role", key: "model_role" },
      { label: "Trades", key: "trade_count" },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Net", render: (r) => `$${fmt(r.net_profit)}` },
      { label: "PF Drift", key: "profit_factor_delta_vs_1m" },
      { label: "Trade Delta", key: "trade_count_delta_vs_1m" },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    result.rows || [],
    "Paste 1-Min OHLC, Every Tick, and Real Tick reports from the same setup to compare execution models."
  );
  $("mt5ComparisonChecks").innerHTML = table(
    [
      { label: "Check", key: "check" },
      { label: "Passed", render: (r) => statusBadge(r.passed ? "PASS" : "FAIL") },
      { label: "Detail", key: "detail" },
    ],
    result.checks || [],
      "Import all three MT5 reports to validate model stability."
    );
  if ((diagnostics.drift_checks || []).length) {
    $("mt5ComparisonChecks").innerHTML += `<div class="mt-4">${table(
      [
        { label: "Drift Metric", key: "metric" },
        { label: "Observed", key: "observed" },
        { label: "Limit", key: "limit" },
        { label: "Passed", render: (r) => statusBadge(r.passed ? "PASS" : "FAIL") },
        { label: "Why It Matters", key: "institutional_reason" },
      ],
      diagnostics.drift_checks,
      "Drift diagnostics appear after importing model reports."
    )}</div>`;
  }
  if ((result.errors || []).length) {
    $("mt5ComparisonChecks").innerHTML += `<div class="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800"><b>Import Errors:</b> ${escapeHtml(result.errors.map((e) => `${e.model}: ${e.error}`).join(" "))}</div>`;
  }
  if ((result.warnings || []).length) {
    $("mt5ComparisonChecks").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Comparison Notes:</b> ${escapeHtml(result.warnings.join(" "))}</div>`;
  }
}

function renderMacroEvidence() {
  const result = state.macroEvidence || state.backtest?.macro_context || {};
  const activation = result.activation_allowed || {};
  $("macroEvidencePanel").innerHTML = metricItems([
    ["Mode", result.mode || $("macroMode")?.value || "manual"],
    ["Source", result.source || "--"],
    ["USD Bias", result.usd_bias || "--"],
    ["Risk Tone", result.risk_sentiment || "--"],
    ["CB Div", result.cb_divergence || "--"],
    ["News", result.news_flag ? "active" : "off"],
    ["USD Conf", result.confidence?.usd_bias ?? result.usd_confidence],
    ["Risk Conf", result.confidence?.risk_sentiment ?? result.risk_confidence],
    ["CB Conf", result.confidence?.cb_divergence ?? result.cb_confidence],
    ["R25/R26 Gate", `${activation.R25 ? "R25 " : ""}${activation.R26 ? "R26" : ""}` || "blocked"],
    ["R27/R28 Gate", `${activation.R27 ? "R27 " : ""}${activation.R28 ? "R28" : ""}` || "blocked"],
    ["R29 Gate", activation.R29 ? "allowed" : "blocked"],
  ]);
  if (result.quality_status || result.input_coverage) {
    $("macroEvidencePanel").innerHTML += `<div class="mt-3 rounded border border-indigo-200 bg-white p-3 text-sm text-indigo-950">
      <b>Evidence Quality:</b> ${statusBadge(result.quality_status || "UNKNOWN")}
      <span class="ml-2">Coverage: <b>${escapeHtml(result.input_coverage?.coverage_percent ?? "--")}%</b></span>
      <span class="ml-2">Inputs: <b>${escapeHtml(result.input_coverage?.available_count ?? "--")}/${escapeHtml(result.input_coverage?.required_count ?? "--")}</b></span>
    </div>`;
  }
  const messages = [...(result.reasons || []), ...(result.warnings || [])];
  if (messages.length) {
    $("macroEvidencePanel").innerHTML += `<div class="mt-3 rounded border border-indigo-200 bg-white p-3 text-sm text-indigo-900"><b>Macro Evidence:</b> ${escapeHtml(messages.join(" "))}</div>`;
  }
}

function renderMacroDiagnostics() {
  const result = state.macroDiagnostics || {};
  const el = $("macroDiagnosticsPanel");
  if (!el) return;
  if (!Object.keys(result).length) {
    el.innerHTML = `<div class="rounded border border-indigo-100 bg-white/70 p-3 text-sm text-indigo-900">Click <b>Review Macro Pipeline</b> to audit R25-R29 evidence coverage, missing inputs, and activation gates.</div>`;
    return;
  }
  const coverage = result.input_coverage || {};
  const groups = coverage.groups || {};
  const latest = result.latest_row || {};
  const activationRows = result.activation_table || [];
  const groupRows = Object.entries(groups).map(([group, item]) => ({
    group,
    available: (item.available || []).join(", ") || "--",
    missing: (item.missing || []).join(", ") || "--",
    coverage_percent: item.coverage_percent,
  }));
  const historyRows = (result.rows || []).slice(0, 8).map((row) => ({
    timestamp: row.timestamp,
    symbol: row.symbol,
    scope: row.scope,
    source: row.source,
    usd: row.resolved?.usd_bias || "--",
    risk: row.resolved?.risk_sentiment || "--",
    cb: row.resolved?.cb_divergence || "--",
    status: row.resolved?.quality_status || "--",
  }));
  el.innerHTML = `
    <div class="rounded border border-indigo-200 bg-white p-3">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h4 class="text-sm font-black uppercase text-indigo-950">R25-R29 Macro Pipeline Diagnostics</h4>
          <p class="text-xs text-slate-600">Evidence-based macro regimes are allowed only when the imported/database evidence passes confidence gates.</p>
        </div>
        ${statusBadge(result.status || "NO_EVIDENCE")}
      </div>
      <div class="metric-grid text-sm">
        ${metricItems([
          ["Pipeline", result.pipeline_ready ? "ready" : "not ready"],
          ["Symbol", result.symbol || "--"],
          ["Rows", result.history_count ?? 0],
          ["Latest", latest.timestamp || "--"],
          ["Coverage", `${coverage.coverage_percent ?? 0}%`],
          ["Inputs", `${coverage.available_count ?? 0}/${coverage.required_count ?? 0}`],
        ])}
      </div>
      <div class="mt-3 grid gap-3 xl:grid-cols-2">
        <div>
          <h5 class="mb-2 text-xs font-black uppercase text-slate-600">Activation Gates</h5>
          ${table([
            { label: "Regime", render: (r) => `${r.regime_id} ${r.regime_name}` },
            { label: "Observed", key: "observed_evidence" },
            { label: "Conf", render: (r) => fmt(r.confidence, 2) },
            { label: "Gate", render: (r) => statusBadge(r.status) },
            { label: "Reason", key: "reason" },
          ], activationRows, "No macro activation rows yet.")}
        </div>
        <div>
          <h5 class="mb-2 text-xs font-black uppercase text-slate-600">Evidence Coverage</h5>
          ${table([
            { label: "Group", key: "group" },
            { label: "Coverage", render: (r) => `${fmt(r.coverage_percent, 1)}%` },
            { label: "Available", key: "available" },
            { label: "Missing", key: "missing" },
          ], groupRows, "No macro evidence fields found.")}
        </div>
      </div>
      ${(result.recommendations || []).length ? `<div class="mt-3 rounded border border-sky-200 bg-sky-50 p-3 text-sm text-sky-950"><b>Next Macro Data Steps</b><ul class="mt-2 list-disc pl-5">${result.recommendations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
      <details class="mt-3 rounded border border-slate-200 bg-slate-50 p-3">
        <summary class="cursor-pointer text-sm font-semibold text-slate-800">Recent Imported Macro Rows</summary>
        <div class="mt-3">${table([
          { label: "Time", key: "timestamp" },
          { label: "Symbol", key: "symbol" },
          { label: "Scope", key: "scope" },
          { label: "Source", key: "source" },
          { label: "USD", key: "usd" },
          { label: "Risk", key: "risk" },
          { label: "CB", key: "cb" },
          { label: "Quality", render: (r) => statusBadge(r.status) },
        ], historyRows, "No imported macro rows found for the selected symbol/date.")}</div>
      </details>
    </div>
  `;
}

function renderBrokerCostCalibration() {
  const result = state.brokerCostCalibration || {};
  const el = $("brokerCostCalibrationPanel");
  if (!el) return;
  if (!Object.keys(result).length) {
    el.innerHTML = `<div class="rounded border border-cyan-200 bg-white p-3 text-sm text-cyan-950">Import MT5 tester reports, then click <b>Calibrate From MT5 Reports</b> to estimate broker-realistic cost R.</div>`;
    return;
  }
  const summary = result.summary || {};
  const rec = result.recommended_costs || {};
  el.innerHTML = `
    <div class="rounded border border-cyan-200 bg-white p-3">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h4 class="text-sm font-black uppercase text-cyan-950">Broker Cost Calibration</h4>
          <p class="text-xs text-slate-600">Derived from imported MT5 tester reports. Apply only after checking sample count and report model quality.</p>
        </div>
        ${statusBadge(result.status || "WAITING")}
      </div>
      <div class="metric-grid text-sm">
        ${metricItems([
          ["Samples", result.sample_count ?? 0],
          ["Reports", result.report_count ?? 0],
          ["Real Tick Reports", result.real_tick_report_count ?? 0],
          ["Avg Cost R", summary.avg_cost_R],
          ["P75 Cost R", summary.p75_cost_R],
          ["P90 Cost R", summary.p90_cost_R],
          ["Avg Commission R", summary.avg_commission_R],
          ["Avg Swap R", summary.avg_swap_R],
          ["Avg Spread Pts", summary.avg_spread_points],
          ["P90 Spread Pts", summary.p90_spread_points],
          ["Avg Slip Pts", summary.avg_slippage_points],
          ["Recommended R", rec.mt5_imported_cost_R],
        ])}
      </div>
      <div class="mt-3 grid gap-3 xl:grid-cols-2">
        <div>
          <h5 class="mb-2 text-xs font-black uppercase text-slate-600">Session Cost Curve</h5>
          ${table([
            { label: "Session", key: "session" },
            { label: "Samples", key: "samples" },
            { label: "Avg Cost R", key: "avg_cost_R" },
            { label: "P75 Cost R", key: "p75_cost_R" },
            { label: "Avg Spread", key: "avg_spread_points" },
            { label: "Avg Slip Pts", key: "avg_slippage_points" },
          ], result.session_curve || [], "No session curve available from imported reports.")}
        </div>
        <div>
          <h5 class="mb-2 text-xs font-black uppercase text-slate-600">MT5 Reports Used</h5>
          ${table([
            { label: "Model", key: "test_model" },
            { label: "Symbol", key: "symbol" },
            { label: "Trades", key: "trade_count" },
            { label: "Net", key: "net_profit" },
            { label: "R Source", key: "result_r_source" },
          ], result.reports || [], "No matching MT5 report imports found.")}
        </div>
      </div>
      ${(result.warnings || []).length ? `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Calibration Notes:</b> ${escapeHtml(result.warnings.join(" "))}</div>` : ""}
      ${(result.next_actions || []).length ? `<div class="mt-3 rounded border border-sky-200 bg-sky-50 p-3 text-sm text-sky-950"><b>Next:</b><ul class="mt-2 list-disc pl-5">${result.next_actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
    </div>
  `;
}

function renderMacroImportResult(result, label = "macro rows") {
  const latest = result.latest || {};
  const summary = result.cross_pair_summary || null;
  const cotSummary = result.cot_summary || null;
  let html = `<span class="font-semibold text-emerald-700">Saved ${result.saved ?? 0} ${escapeHtml(label)}.</span> Latest: ${escapeHtml(latest.timestamp || "--")} ${escapeHtml(latest.symbol || "")}`;
  if (summary) {
    html += `<div class="mt-2 rounded border border-indigo-200 bg-indigo-50 p-2 text-indigo-950">
      <b>Cross-Pair Summary:</b>
      USD basket ${escapeHtml(summary.usd_basket_change_percent ?? "--")} |
      JPY strength ${escapeHtml(summary.jpy_strength_score ?? "--")} |
      CHF strength ${escapeHtml(summary.chf_strength_score ?? "--")} |
      Risk proxy ${escapeHtml(summary.risk_proxy_change_percent ?? "--")} |
      Used ${escapeHtml(summary.symbols_used ?? 0)}/${escapeHtml((summary.symbols_requested || []).length || 0)}
    </div>`;
  }
  if ((result.cross_pair_components || []).length) {
    const ok = result.cross_pair_components.filter((item) => item.status === "ok").slice(0, 8);
    const missing = result.cross_pair_components.filter((item) => item.status !== "ok").slice(0, 8);
    html += `<div class="mt-2 text-xs text-slate-600">Pairs used: ${escapeHtml(ok.map((item) => `${item.symbol} ${item.change_percent}%`).join(", ") || "--")}</div>`;
    if (missing.length) html += `<div class="mt-1 text-xs text-amber-800">Missing/insufficient: ${escapeHtml(missing.map((item) => item.symbol).join(", "))}</div>`;
  }
  if (cotSummary) {
    html += `<div class="mt-2 rounded border border-emerald-200 bg-emerald-50 p-2 text-emerald-950">
      <b>COT Summary:</b>
      ${escapeHtml(cotSummary.report_type || "--")} |
      Imported ${escapeHtml(cotSummary.symbols_imported ?? 0)} symbols |
      Currencies ${escapeHtml((cotSummary.currencies_requested || []).join(", ") || "--")}
    </div>`;
  }
  if ((result.cot_components || []).length) {
    const rows = result.cot_components.slice(0, 10);
    html += `<div class="mt-2 text-xs text-slate-600">COT pairs: ${escapeHtml(rows.map((item) => `${item.symbol} pair=${item.pair_score} usd=${item.usd_score}`).join(", "))}</div>`;
  }
  if ((result.warnings || []).length) {
    html += `<div class="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-amber-900">${escapeHtml(result.warnings.join(" "))}</div>`;
  }
  $("macroImportResult").innerHTML = html;
}

function renderRealTickWorkflow() {
  const result = state.realTickWorkflow || {};
  const comparison = result.model_comparison || {};
  const candidate = result.candidate || {};
  const readiness = result.readiness || {};
  const quickStart = result.quick_start?.length ? result.quick_start : [
    { step: "1", title: "Run Python backtest", detail: "Create a candidate and run_id." },
    { step: "2", title: "Prepare MT5 configs", detail: "Generate one tester config per model." },
    { step: "3", title: "Run/import reports", detail: "Use 1-Min OHLC, Every Tick, and Real Ticks." },
    { step: "4", title: "Compare and approve", detail: "Review drift, parity, and final gates." },
  ];
  $("realTickQuickStart").innerHTML = quickStart.map((item) => `
    <div class="workflow-step-card">
      <div class="workflow-step-number">${escapeHtml(item.step || "")}</div>
      <div>
        <div class="workflow-step-title">${escapeHtml(item.title || "")}</div>
        <div class="workflow-step-detail">${escapeHtml(item.detail || "")}</div>
      </div>
    </div>
  `).join("");
  const blockers = readiness.blockers || [];
  $("realTickReadiness").innerHTML = `
    <div class="rounded border ${blockers.length ? "border-amber-300 bg-amber-50 text-amber-950" : "border-emerald-300 bg-white text-emerald-950"} p-3 text-sm">
      <div class="flex flex-wrap items-center gap-2">
        <b>Readiness:</b> ${statusBadge(readiness.stage || result.status || "WAITING")}
        <span>Configs: <b>${readiness.configs_ready ? "ready" : "pending"}</b></span>
        <span>Reports: <b>${readiness.reports_supplied_count ?? 0}/${readiness.reports_required_count ?? 3}</b></span>
        <span>Comparison: <b>${escapeHtml(readiness.comparison_status || "--")}</b></span>
        <span>Parity: <b>${escapeHtml(readiness.parity_status || "--")}</b></span>
      </div>
      ${blockers.length ? `<ul class="mt-2 list-disc pl-5">${blockers.map((b) => `<li>${escapeHtml(b)}</li>`).join("")}</ul>` : `<div class="mt-2">No workflow blockers reported yet.</div>`}
    </div>
  `;
  $("realTickWorkflowSummary").innerHTML = metricItems([
    ["Workflow", result.workflow_id ? String(result.workflow_id).slice(0, 8) : "--"],
    ["Status", result.status || "--"],
    ["Symbol", candidate.symbol || "--"],
    ["TF", candidate.timeframe || "--"],
    ["Regime", candidate.regime_filter || "--"],
    ["Strategy", candidate.strategy_filter || "--"],
    ["Reports", result.reports_supplied ? Object.values(result.reports_supplied).filter(Boolean).length : 0],
    ["Generated Reports", result.generated_report_sources ? Object.keys(result.generated_report_sources).length : 0],
    ["Comparison", comparison.status || "--"],
    ["Parity", result.parity_check?.status || "--"],
    ["Order Execution", result.order_execution ? "yes" : "no"],
  ]);
  const modelCards = (result.model_cards || []).length ? result.model_cards : [
    { model: "one_min_ohlc", model_name: "1-Min OHLC", purpose: "fast research filter", status: "WAITING", next_action: "Prepare workflow to generate config." },
    { model: "every_tick", model_name: "Every Tick", purpose: "intrabar validation", status: "WAITING", next_action: "Prepare workflow to generate config." },
    { model: "every_tick_real_ticks", model_name: "Real Ticks", purpose: "final broker/tick validation", status: "WAITING", next_action: "Prepare workflow to generate config." },
  ];
  $("realTickModelCards").innerHTML = modelCards.map((card) => `
    <div class="workflow-model-card">
      <div class="flex items-start justify-between gap-2">
        <div>
          <div class="text-xs font-black uppercase text-slate-500">${escapeHtml(card.model || "")}</div>
          <div class="text-base font-bold text-slate-950">${escapeHtml(card.model_name || "")}</div>
          <div class="text-xs text-slate-600">${escapeHtml(card.purpose || "")}</div>
        </div>
        ${statusBadge(card.report_supplied ? "REPORT_READY" : card.status || "WAITING")}
      </div>
      <div class="mt-3 space-y-2 text-xs text-slate-700">
        <div><b>Next:</b> ${escapeHtml(card.next_action || "--")}</div>
        <div><b>INI:</b> <code class="break-all">${escapeHtml(card.ini_path || "--")}</code></div>
        <div><b>Report:</b> <code class="break-all">${escapeHtml(card.generated_report_source || card.report_path || "--")}</code></div>
      </div>
    </div>
  `).join("");
  $("realTickNextActions").innerHTML = (result.next_actions || []).length
    ? `<div class="rounded border border-sky-200 bg-sky-50 p-3 text-sm text-sky-950"><b>Next Actions</b><ol class="mt-2 list-decimal pl-5">${result.next_actions.map((a) => `<li>${escapeHtml(a)}</li>`).join("")}</ol></div>`
    : "";
  $("realTickWorkflowSteps").innerHTML = table(
    [
      { label: "#", key: "step" },
      { label: "Workflow Step", key: "name" },
      { label: "Status", render: (r) => statusBadge(r.status || "--") },
      { label: "Detail", key: "detail" },
    ],
    result.steps || [],
    "Prepare the real-tick workflow to see the five-step validation path."
  );
  const runRows = Object.entries(result.tester_runs || {}).map(([model, run]) => ({
    model,
    status: run.status,
    ini: run.tester_config?.ini_path,
    set: run.tester_config?.set_path,
    report: run.tester_config?.report_path,
    found: run.report_found_path,
    imported: run.report_import ? "yes" : "no",
  }));
  if (runRows.length) {
    $("realTickWorkflowSteps").innerHTML += table(
      [
        { label: "Model", key: "model" },
        { label: "Status", render: (r) => statusBadge(r.status || "--") },
        { label: "INI", render: (r) => `<code class="break-all">${escapeHtml(r.ini || "--")}</code>` },
        { label: "SET", render: (r) => `<code class="break-all">${escapeHtml(r.set || "--")}</code>` },
        { label: "Report Path", render: (r) => `<code class="break-all">${escapeHtml(r.report || "--")}</code>` },
        { label: "Found", render: (r) => `<code class="break-all">${escapeHtml(r.found || "--")}</code>` },
        { label: "Imported", key: "imported" },
      ],
      runRows,
      ""
    );
  }
  if (result.parity_check) {
    state.mt5Parity = result.parity_check;
    renderMt5Parity();
  }
  if ((result.warnings || []).length) {
    $("realTickWorkflowSteps").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><b>Workflow Notes:</b> ${escapeHtml(result.warnings.join(" "))}</div>`;
  }
}

function renderSavedData() {
  $("savedRunsPanel").innerHTML = table(
    [
      { label: "", render: (r) => favoriteButton("backtest", r.run_id, Number(r.is_favorite) === 1) },
      { label: "Run", render: (r) => `<button class="text-blue-700 underline" data-run-id="${escapeHtml(r.run_id)}">${escapeHtml(String(r.run_id || "").slice(0, 8))}</button>` },
      { label: "Created", render: (r) => String(r.created_at || "").slice(0, 19) },
      { label: "Symbol", key: "symbol" },
      { label: "TF", key: "timeframe" },
      { label: "Regime", key: "regime_filter" },
      { label: "Strategy", key: "strategy_filter" },
      { label: "Trades", key: "total_trades" },
      { label: "Win", render: (r) => `${(Number(r.win_rate || 0) * 100).toFixed(1)}%` },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Net", render: (r) => `$${fmt(r.net_profit)}` },
      { label: "Regimes", key: "regimes_detected" },
    ],
    state.savedRuns || [],
    "Load saved runs to review previous local research results."
  );

  const savedValidationEl = $("savedValidationPanel");
  if (savedValidationEl) {
    savedValidationEl.innerHTML = table(
      [
        { label: "", render: (r) => favoriteButton("validation", r.validation_run_id, Number(r.is_favorite) === 1) },
        { label: "Run", render: (r) => `<button class="text-blue-700 underline" data-validation-run-id="${escapeHtml(r.validation_run_id)}">${escapeHtml(String(r.validation_run_id || "").slice(0, 8))}</button>` },
        { label: "Created", render: (r) => String(r.created_at || "").slice(0, 19) },
        { label: "Type", key: "validation_type" },
        { label: "Status", render: (r) => statusBadge(r.status || r.summary?.status || "--") },
        { label: "Symbol", key: "symbol" },
        { label: "TF", key: "timeframe" },
        { label: "Regime", key: "regime_filter" },
        { label: "Strategy", key: "strategy_filter" },
        { label: "Trades", render: (r) => r.summary?.total_trades ?? r.summary?.source_trades ?? r.summary?.oos_trades ?? "--" },
        { label: "PF", render: (r) => r.summary?.profit_factor ?? r.summary?.oos_profit_factor ?? r.summary?.oos_pf ?? "--" },
        { label: "Stable", render: (r) => r.summary?.stable === undefined ? "--" : statusBadge(r.summary.stable ? "YES" : "NO") },
      ],
      state.savedValidationRuns || [],
      "Load validation runs to review saved OOS, walk-forward, Monte Carlo, portfolio, and MT5 tester evidence."
    );
  }

  $("savedFeaturesPanel").innerHTML = table(
    [
      { label: "", render: (r) => favoriteButton("feature", r.favorite_id, Number(r.is_favorite) === 1) },
      { label: "Time", render: (r) => String(r.timestamp || "").slice(0, 19) },
      { label: "Session", key: "session" },
      { label: "ADX", key: "adx" },
      { label: "ER", key: "er" },
      { label: "ATR %", key: "atr_percentile" },
      { label: "Spread %", key: "spread_percentile" },
      { label: "HTF", key: "htf_bias" },
      { label: "LTF", key: "ltf_bias" },
      { label: "Sweep H/L", render: (r) => `${fmt(r.sweep_high_flag, 0)} / ${fmt(r.sweep_low_flag, 0)}` },
      { label: "VWAP ATR", key: "distance_from_vwap_atr" },
      { label: "Gap ATR", key: "gap_atr" },
      { label: "DQ Type", key: "data_quality_category" },
      { label: "DQ", render: (r) => r.data_quality_reasons ? escapeHtml(r.data_quality_reasons) : "--" },
    ],
    state.savedFeatures || [],
    "Load saved features to see calculated data that otherwise stays hidden in SQLite."
  );
}

function performanceForRegime(id) {
  return state.backtest?.regime_performance?.find((r) => r.regime_id === id);
}

function strategiesForRegime(id) {
  const regime = state.regimes.find((r) => r.regime_id === id);
  return (regime?.allowed_strategies || []).map((sid) => state.strategies.find((s) => s.strategy_id === sid)).filter(Boolean);
}

function tradesFor(regimeId, strategyId = null) {
  return (state.backtest?.trades || []).filter((t) => t.regime_id === regimeId && (!strategyId || t.strategy_id === strategyId));
}

function tradeStats(trades) {
  const count = trades.length;
  const wins = trades.filter((t) => Number(t.result_R) > 0);
  const losses = trades.filter((t) => Number(t.result_R) < 0);
  const grossProfit = trades.filter((t) => Number(t.profit) > 0).reduce((a, t) => a + Number(t.profit || 0), 0);
  const grossLoss = trades.filter((t) => Number(t.profit) < 0).reduce((a, t) => a + Number(t.profit || 0), 0);
  const resultSum = trades.reduce((a, t) => a + Number(t.result_R || 0), 0);
  return {
    count,
    wins: wins.length,
    losses: losses.length,
    winRate: count ? wins.length / count : 0,
    avgR: count ? resultSum / count : 0,
    netProfit: grossProfit + grossLoss,
    grossProfit,
    grossLoss,
    pf: Math.abs(grossLoss) > 0 ? grossProfit / Math.abs(grossLoss) : grossProfit > 0 ? 999 : 0,
  };
}

function groupedTradePerformance(trades, keyFn, labelKey) {
  const groups = {};
  trades.forEach((t) => {
    const key = keyFn(t) || "Unknown";
    groups[key] ||= [];
    groups[key].push(t);
  });
  return Object.entries(groups).map(([key, group]) => {
    const stats = tradeStats(group);
    return {
      [labelKey]: key,
      trade_count: stats.count,
      win_rate: stats.winRate,
      profit_factor: Number(stats.pf.toFixed(4)),
      expectancy_R: Number(stats.avgR.toFixed(4)),
      net_profit: Number(stats.netProfit.toFixed(2)),
      status: stats.count >= 100 && stats.avgR > 0 && stats.pf >= 1.2 ? "APPROVED" : stats.count >= 50 ? "WATCHLIST" : stats.count ? "INSUFFICIENT DATA" : "NOT ENOUGH DATA",
    };
  });
}

function groupedPatternPerformance(trades) {
  const expanded = [];
  trades.forEach((trade) => {
    const positive = (trade.patterns_detected || []).filter((p) => Number(p.score || 0) > 0);
    if (!positive.length) {
      expanded.push({ ...trade, pattern_id: "NO_PATTERN", pattern_name: "No Positive Pattern" });
      return;
    }
    positive.forEach((pattern) => {
      expanded.push({
        ...trade,
        pattern_id: pattern.pattern_id || "UNKNOWN_PATTERN",
        pattern_name: pattern.pattern_name || pattern.pattern_id || "Unknown Pattern",
      });
    });
  });
  return groupedTradePerformance(expanded, (t) => `${t.pattern_id} ${t.pattern_name}`, "pattern");
}

function finalApprovalPassed() {
  return state.finalApproval?.status === "FINAL_APPROVED_FOR_DEMO_REVIEW";
}

function finalApprovalCandidateFilters() {
  const candidate = state.finalApproval?.candidate || {};
  const optimizerCandidate = candidate.optimizer_candidate || {};
  return {
    regime: candidate.regime_filter || optimizerCandidate.regime_filter || currentPayload().regime_filter || "ALL",
    strategy: candidate.strategy_filter || optimizerCandidate.strategy_filter || currentPayload().strategy_filter || "ALL",
  };
}

function latestRegimeId() {
  return state.latestMarket?.active_regime?.regime_id || null;
}

function latestAllowedStrategies() {
  return (state.latestMarket?.allowed_strategies || []).map((s) => s.strategy_id || s.strategy_name).filter(Boolean);
}

function focusedHistoryTrades(regimeId, strategyIds) {
  const ids = new Set(strategyIds || []);
  return (state.backtest?.trades || [])
    .filter((trade) => trade.regime_id === regimeId && (!ids.size || ids.has(trade.strategy_id)))
    .slice()
    .sort((a, b) => String(b.entry_time || "").localeCompare(String(a.entry_time || "")));
}

function renderSemiManualWatchlist() {
  const gateBadge = $("semiManualGateBadge");
  if (!gateBadge) return;
  const latest = state.latestMarket || {};
  const active = latest.active_regime || {};
  const features = latest.latest_features || {};
  const currentId = active.regime_id || "--";
  const finalPass = finalApprovalPassed();
  const filters = finalApprovalCandidateFilters();
  const hardReasons = latest.modifiers?.hard_block_reasons || [];
  const allowedLatest = latestAllowedStrategies();
  const finalRegimeOk = !filters.regime || filters.regime === "ALL" || filters.regime === currentId;
  const finalStrategyIds = filters.strategy && filters.strategy !== "ALL" ? [filters.strategy] : allowedLatest;
  const strategyIds = finalStrategyIds.filter((sid) => allowedLatest.includes(sid) || filters.strategy === "ALL");
  const hasLatest = Boolean(state.latestMarket);
  const hasBacktest = Boolean(state.backtest?.summary);
  const hasHistory = focusedHistoryTrades(currentId, strategyIds).length > 0;
  const dataQuality = state.backtest?.institutional_data_quality || {};
  const blocked = [];
  if (!hasBacktest) blocked.push("Run a local Python backtest so the panel can show historical evidence.");
  if (!hasLatest) blocked.push("Run Detect Latest so the panel can compare current regime with the validated setup.");
  if (!finalPass) blocked.push("Run Final Approval and pass all required gates before watchlist candidates are shown.");
  if (hasBacktest && !dataQuality.semi_manual_readiness) blocked.push(`Data provenance is ${dataQuality.validation_status || "not graded"}; import/compare MT5 real ticks before semi-manual watchlist review.`);
  if (hardReasons.length) blocked.push(`Current market has hard block: ${hardReasons.join("; ")}.`);
  if (hasLatest && !active.is_active) blocked.push("Current regime is not active enough for a watchlist candidate.");
  if (hasLatest && !finalRegimeOk) blocked.push(`Validated regime is ${filters.regime}, but current regime is ${currentId}.`);
  if (hasLatest && finalRegimeOk && !strategyIds.length) blocked.push("No validated strategy is currently allowed by the active regime.");
  if (hasLatest && finalRegimeOk && strategyIds.length && !hasHistory) blocked.push("No past backtest trades found for this current regime/strategy focus.");

  const gateStatus = blocked.length ? "WAITING" : "WATCHLIST_READY";
  gateBadge.outerHTML = statusBadge(gateStatus).replace("<span", '<span id="semiManualGateBadge"');
  $("semiManualGatePanel").innerHTML = blocked.length
    ? `<div class="signal-block-card"><b>No semi-manual candidate shown.</b><ul class="mt-2 list-disc pl-5">${blocked.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`
    : `<div class="signal-watch-card border-emerald-300 bg-white text-emerald-950"><b>Watchlist only:</b> final validation passed, current regime matches the validated setup, and historical evidence is available. No order execution is available from this panel.</div>`;

  $("semiManualCurrentPanel").innerHTML = metricItems([
    ["Current Regime", `${currentId} ${active.regime_name || ""}`],
    ["Confidence", active.confidence],
    ["Direction", active.direction || "--"],
    ["Session", features.session || "--"],
    ["ADX / ER", `${fmt(features.adx)} / ${fmt(features.er)}`],
    ["Spread %", features.spread_percentile],
    ["HTF / LTF", `${features.htf_bias || "--"} / ${features.ltf_bias || "--"}`],
    ["Final Gate", state.finalApproval?.status || "--"],
    ["Data Grade", dataQuality.data_grade || "--"],
    ["Data Status", dataQuality.validation_status || "--"],
  ]);

  if (blocked.length) {
    $("semiManualCandidates").innerHTML = `<p class="text-sm text-emerald-900">When gates pass, candidate cards will appear here with strategy focus and historical evidence.</p>`;
    $("semiManualHistory").innerHTML = table([], [], "No focused history until the watchlist gate passes.");
    return;
  }

  const candidates = strategyIds.map((sid) => {
    const strategy = state.strategies.find((item) => item.strategy_id === sid) || { strategy_id: sid, strategy_name: sid };
    const trades = tradesFor(currentId, sid);
    const stats = tradeStats(trades);
    const perf = (state.backtest?.strategy_performance || []).find((row) => row.strategy_id === sid) || {};
    return { strategy, stats, perf };
  });
  $("semiManualCandidates").innerHTML = candidates.map(({ strategy, stats, perf }) => `
    <div class="signal-watch-card">
      <div class="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div class="text-xs font-black uppercase text-emerald-700">Watchlist Candidate</div>
          <div class="text-lg font-bold text-slate-950">${escapeHtml(strategy.strategy_id)} ${escapeHtml(strategy.strategy_name || "")}</div>
          <div class="text-sm text-slate-600">${escapeHtml(strategy.category || "strategy")} | ${escapeHtml(strategy.direction || "direction from regime")}</div>
        </div>
        ${statusBadge("WATCHLIST_ONLY")}
      </div>
      <div class="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div class="metric-mini"><b>Trades</b><span>${stats.count}</span></div>
        <div class="metric-mini"><b>Win</b><span>${(stats.winRate * 100).toFixed(1)}%</span></div>
        <div class="metric-mini"><b>PF</b><span>${fmt(stats.pf)}</span></div>
        <div class="metric-mini"><b>Avg R</b><span>${fmt(stats.avgR)}</span></div>
      </div>
      <div class="mt-2 text-xs text-slate-600">Research status: ${escapeHtml(perf.status || "history only")} | Entry logic must still be manually reviewed on MT5 chart.</div>
    </div>
  `).join("");

  const history = focusedHistoryTrades(currentId, strategyIds).slice(0, 15);
  $("semiManualHistory").innerHTML = table(
    [
      { label: "Entry", key: "entry_time" },
      { label: "Strategy", render: (r) => `${r.strategy_id} ${r.strategy_name || ""}` },
      { label: "Dir", key: "direction" },
      { label: "Session", render: (r) => r.session || r.modifiers || "--" },
      { label: "Entry", render: (r) => formatPrice(r.symbol, r.entry) },
      { label: "Exit", render: (r) => formatPrice(r.symbol, r.exit_price) },
      { label: "R", key: "result_R" },
      { label: "Profit", render: (r) => `$${fmt(r.profit)}` },
      { label: "Alpha", key: "alpha_score" },
      { label: "Reason", render: (r) => escapeHtml(r.entry_reason || "--") },
    ],
    history,
    "No recent focused trades for the current validated regime/strategy."
  );
}

function strategyJsonPair(regime, strategy) {
  const payload = currentPayload();
  const strategyTrades = tradesFor(regime.regime_id, strategy.strategy_id);
  const stats = tradeStats(strategyTrades);
  const comboRows = (state.backtest?.unique_combination_performance || []).filter((item) =>
    String(item.combination_key || "").startsWith(`${regime.regime_id}_${strategy.strategy_id}_`)
  );
  const input = {
    endpoint: "POST /api/backtest/run",
    purpose: "Research this specific regime + strategy against MT5 candle data saved in SQLite.",
    payload: {
      ...payload,
      regime_filter: regime.regime_id,
      strategy_filter: strategy.strategy_id,
    },
    regime: {
      regime_id: regime.regime_id,
      regime_name: regime.regime_name,
      direction: regime.direction,
      conditions: regime.conditions,
      rules: regime.rules,
      risk: regime.risk,
    },
    strategy: strategy,
    controls_applied: {
      investment_amount: Number($("initialEquity").value || 100000),
      risk_percent: Number($("riskPercent").value),
      rr: Number($("rr").value),
      sentiment: $("sentiment").value,
      usd_bias: $("usdBias").value,
      risk_sentiment: $("riskSentiment").value,
      cb_divergence: $("cbDivergence").value,
      macro_evidence: currentMacroEvidencePayload(),
      killzone: $("useKillzone").checked,
      spread_filter: $("useSpreadFilter").checked,
      sweeps: $("useSweeps").checked,
      alpha: $("useAlpha").checked,
      killzone_mode: $("killzoneMode").value,
      spread_filter_mode: $("spreadFilterMode").value,
      alpha_mode: $("alphaMode").value,
      strict_clean_trend: $("strictCleanTrend").checked,
      pattern_engine: {
        use_patterns: $("usePatterns").checked,
        use_ict: $("useIct").checked,
        use_fvg: $("useFvg").checked,
        use_order_blocks: $("useOrderBlocks").checked,
        use_bos: $("useBos").checked,
        use_mss: $("useMss").checked,
        use_liquidity_pools: $("useLiquidityPools").checked,
        use_round_numbers: $("useRoundNumbers").checked,
        use_vwap: $("useVwap").checked,
        use_mvwap: $("useMvwap").checked,
        use_session_vwap: $("useSessionVwap").checked,
        pattern_score_mode: $("patternScoreMode").value,
        min_pattern_score: Number($("minPatternScore").value || 2),
      },
    },
  };
  const output = state.backtest
    ? {
        source: "MT5 candles stored in SQLite",
        run_id: state.backtest.run_id,
        regime_id: regime.regime_id,
        strategy_id: strategy.strategy_id,
        performance: {
          trades: stats.count,
          wins: stats.wins,
          losses: stats.losses,
          win_rate: Number(stats.winRate.toFixed(4)),
          average_R: Number(stats.avgR.toFixed(4)),
          net_profit: Number(stats.netProfit.toFixed(2)),
          gross_profit: Number(stats.grossProfit.toFixed(2)),
          gross_loss: Number(stats.grossLoss.toFixed(2)),
          profit_factor: Number(stats.pf.toFixed(4)),
        },
        combinations: comboRows,
        first_5_trades: strategyTrades.slice(0, 5),
        full_trade_count: strategyTrades.length,
        note: strategyTrades.length > 5 ? "Showing first 5 trades here. Use the trade table for the full filtered list." : "Showing all trades for this regime + strategy.",
      }
    : {
        source: "MT5 candles stored in SQLite",
        message: "Run Backtest to generate output for this regime + strategy input.",
      };
  return { input, output };
}

function compactBacktestOutput(result, regimeId, strategyId) {
  const strategyTrades = (result.trades || []).filter((t) => t.regime_id === regimeId && t.strategy_id === strategyId);
  const strategyPerf = (result.strategy_performance || []).find((s) => s.strategy_id === strategyId);
  const regimePerf = (result.regime_performance || []).find((r) => r.regime_id === regimeId);
  const confidence = (result.regime_confidence || []).find((r) => r.regime_id === regimeId);
  return {
    run_id: result.run_id,
    request: {
      regime_filter: regimeId,
      strategy_filter: strategyId,
    },
    summary: result.summary,
    data_health: result.data_health,
    pattern_summary: result.pattern_summary,
    regime_confidence: confidence || null,
    regime_performance: regimePerf || null,
    strategy_performance: strategyPerf || null,
    pattern_performance: result.pattern_performance || [],
    skipped_setups: (result.skipped_setups || []).filter((s) => String(s.regime_candidate || "").startsWith(regimeId) && String(s.strategy_candidate || "").startsWith(strategyId)).slice(0, 20),
    first_20_trades: strategyTrades.slice(0, 20),
    trade_count_for_pair: strategyTrades.length,
    note: strategyTrades.length > 20 ? "Showing first 20 trades for this regime + strategy pair." : "Showing all trades for this regime + strategy pair.",
  };
}

function endpointPath(endpointValue, fallback = "/api/backtest/run") {
  const raw = String(endpointValue || fallback).trim();
  const parts = raw.split(/\s+/);
  const path = parts.length > 1 ? parts[1] : parts[0];
  return path.startsWith("/") ? path : fallback;
}

function renderRegimeCards() {
  const q = $("regimeSearch").value.trim().toLowerCase();
  const regimes = state.regimes.filter((r) => !q || `${r.regime_id} ${r.regime_name} ${r.meaning}`.toLowerCase().includes(q));
  $("regimeCards").innerHTML = regimes
    .map((r) => {
      const perf = performanceForRegime(r.regime_id);
      return `
        <article class="regime-card ${state.selectedRegimeId === r.regime_id ? "active" : ""}" data-regime="${r.regime_id}">
          <div class="mb-2 flex items-start justify-between gap-2">
            <div>
              <div class="text-xs font-bold text-slate-500">${r.regime_id}</div>
              <h3 class="text-base font-semibold">${r.regime_name}</h3>
            </div>
            ${statusBadge(perf?.status || "REFERENCE")}
          </div>
          <p class="mb-3 text-sm text-slate-600">${r.meaning}</p>
          <div class="grid grid-cols-2 gap-2 text-xs text-slate-600">
            <div><b>Trades:</b> ${fmt(perf?.trade_count, 0)}</div>
            <div><b>PF:</b> ${fmt(perf?.profit_factor)}</div>
            <div><b>Win:</b> ${perf?.win_rate !== undefined ? `${(perf.win_rate * 100).toFixed(1)}%` : "--"}</div>
            <div><b>Exp:</b> ${fmt(perf?.expectancy_R)}</div>
          </div>
        </article>`;
    })
    .join("");
  document.querySelectorAll("[data-regime]").forEach((el) => {
    el.addEventListener("click", () => {
      state.selectedRegimeId = el.dataset.regime;
      renderRegimeCards();
      renderResearchPanels();
      renderRegimeDetail();
      renderPerformanceTables();
      renderTrades();
      renderSkippedAndApproval();
      renderCharts();
      renderExplanation();
    });
  });
}

function renderRegimeDetail() {
  if (!state.selectedRegimeId) {
    $("regimeDetail").innerHTML = "Click a regime card to inspect only that regime's conditions, rules, mapped strategies, trades, and analysis.";
    return;
  }
  const regime = state.regimes.find((r) => r.regime_id === state.selectedRegimeId);
  if (!regime) {
    $("regimeDetail").innerHTML = "Selected regime was not found.";
    return;
  }
  const perf = performanceForRegime(regime.regime_id);
  const mapped = strategiesForRegime(regime.regime_id);
  const regimeTrades = tradesFor(regime.regime_id);
  const regimeStats = tradeStats(regimeTrades);
  const regimeStrategyCount = new Set(regimeTrades.map((t) => t.strategy_id)).size;
  const strategyRows = mapped
    .map((s) => {
      const stats = tradeStats(tradesFor(regime.regime_id, s.strategy_id));
      const combo = state.backtest?.combination_performance?.find((item) => String(item.combination_key || "").startsWith(`${regime.regime_id}_${s.strategy_id}_`));
      return `<tr>
        <td>${s.strategy_id}</td>
        <td>${s.strategy_name}</td>
        <td>${s.direction}</td>
        <td>${fmt(stats.count, 0)}</td>
        <td>${fmt(stats.wins, 0)} / ${fmt(stats.losses, 0)}</td>
        <td>${(stats.winRate * 100).toFixed(1)}%</td>
        <td>${fmt(stats.avgR)}</td>
        <td>$${fmt(stats.netProfit)}</td>
        <td>$${fmt(stats.grossProfit)}</td>
        <td>$${fmt(stats.grossLoss)}</td>
        <td>${fmt(stats.pf)}</td>
        <td>${statusBadge(combo?.status || (stats.count ? "TESTED" : "REFERENCE"))}</td>
      </tr>`;
    })
    .join("");
  const strategyJsonBlocks = mapped
    .map((s) => {
      const pair = strategyJsonPair(regime, s);
      const key = `${regime.regime_id}_${s.strategy_id}`;
      const liveResponse = state.jsonTesterResponses[key] || pair.output;
      return `
        <details class="border border-slate-200 p-3" ${mapped.length <= 3 ? "open" : ""} data-json-block="${key}">
          <summary class="cursor-pointer font-semibold">${s.strategy_id} ${s.strategy_name}</summary>
          <div class="mt-3 grid gap-3 xl:grid-cols-2">
            <div>
              <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div class="text-xs font-bold uppercase text-slate-500">Editable Input JSON</div>
                <button class="action-btn primary-btn json-send-btn" data-regime-id="${regime.regime_id}" data-strategy-id="${s.strategy_id}" type="button">Send Request</button>
              </div>
              <textarea class="json-editor" data-json-input="${key}" spellcheck="false">${jsonText(pair.input)}</textarea>
              <p class="mt-2 text-xs text-slate-500">Edit values, then send. If this wrapper contains a payload field, only payload is posted to the backend.</p>
            </div>
            <div>
              <div class="mb-1 text-xs font-bold uppercase text-slate-500">Response JSON</div>
              <div class="json-response" data-json-output="${key}">${jsonBlock(liveResponse)}</div>
            </div>
          </div>
        </details>`;
    })
    .join("");
  $("regimeDetail").innerHTML = `
    <div class="space-y-4">
      <div>
        <div class="text-xs font-bold text-slate-500">${regime.regime_id}</div>
        <h3 class="text-lg font-semibold">${regime.regime_name}</h3>
        <p class="mt-1 text-slate-600">${regime.meaning}</p>
      </div>
      <div class="grid grid-cols-2 gap-2 text-sm">
        <div><b>Status:</b> ${statusBadge(perf?.status || "REFERENCE")}</div>
        <div><b>Direction:</b> ${regime.direction}</div>
        <div><b>Trades:</b> ${fmt(perf?.trade_count, 0)}</div>
        <div><b>Strategies Came:</b> ${regimeStrategyCount || "--"}</div>
        <div><b>Expectancy:</b> ${fmt(perf?.expectancy_R)}</div>
        <div><b>Win Rate:</b> ${perf?.win_rate !== undefined ? `${(perf.win_rate * 100).toFixed(1)}%` : "--"}</div>
        <div><b>Max DD:</b> ${fmt(perf?.max_drawdown_R)}</div>
        <div><b>Net P/L:</b> $${fmt(regimeStats.netProfit)}</div>
        <div><b>Gross Profit:</b> $${fmt(regimeStats.grossProfit)}</div>
        <div><b>Gross Loss:</b> $${fmt(regimeStats.grossLoss)}</div>
      </div>
      <div>
        <h4 class="mb-1 font-semibold">Conditions</h4>
        <ul class="list-disc space-y-1 pl-5">${regime.conditions.map((x) => `<li>${x}</li>`).join("")}</ul>
      </div>
      <div>
        <h4 class="mb-1 font-semibold">Rules</h4>
        <ul class="list-disc space-y-1 pl-5">${regime.rules.map((x) => `<li>${x}</li>`).join("")}</ul>
      </div>
      <div>
        <h4 class="mb-2 font-semibold">Mapped Strategies</h4>
        <div class="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Dir</th><th>Trades</th><th>W/L</th><th>Win</th><th>Avg R</th><th>Net P/L</th><th>Profit</th><th>Loss</th><th>PF</th><th>Status</th></tr></thead><tbody>${strategyRows || "<tr><td colspan='12'>No mapped strategies.</td></tr>"}</tbody></table></div>
      </div>
      <div>
        <h4 class="mb-2 font-semibold">Regime + Strategy JSON Input / Output</h4>
        <p class="mb-3 text-sm text-slate-500">Each block shows the exact input shape for testing this regime with one strategy, plus the matching output from the latest backtest run.</p>
        <div class="space-y-3">${strategyJsonBlocks || "<p class='text-sm text-slate-500'>No mapped strategy JSON available.</p>"}</div>
      </div>
    </div>`;
}

function table(headers, rows, empty = "No data yet.") {
  if (!rows || rows.length === 0) return `<p class="text-sm text-slate-500">${empty}</p>`;
  return `<table><thead><tr>${headers.map((h) => `<th>${h.label}</th>`).join("")}</tr></thead><tbody>${rows
    .map((r) => `<tr>${headers.map((h) => `<td>${h.render ? h.render(r) : fmt(r[h.key])}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

function renderPerformanceTables() {
  const selectedId = state.selectedRegimeId;
  const selectedStrategyIds = new Set(strategiesForRegime(selectedId).map((s) => s.strategy_id));
  const regimeRows = selectedId
    ? (state.backtest?.regime_performance || []).filter((r) => r.regime_id === selectedId)
    : [];
  const strategyRows = selectedId
    ? (state.backtest?.strategy_performance || []).filter((s) => selectedStrategyIds.has(s.strategy_id))
    : [];
  const combinationRows = selectedId
    ? (state.backtest?.unique_combination_performance || []).filter((c) => String(c.combination_key || "").startsWith(`${selectedId}_`))
    : [];
  const modifierRows = selectedId
    ? (state.backtest?.modifier_impact || state.backtest?.combination_performance || []).filter((c) => String(c.combination_key || "").startsWith(`${selectedId}_`))
    : [];
  const selectedTrades = selectedId ? tradesFor(selectedId) : [];
  const selectedSessionRows = groupedTradePerformance(selectedTrades, (t) => t.session, "session");
  const selectedMonthlyRows = groupedTradePerformance(selectedTrades, (t) => String(t.entry_time || "").slice(0, 7), "month");
  const selectedPatternRows = selectedId ? groupedPatternPerformance(selectedTrades) : (state.backtest?.pattern_performance || []).map((r) => ({ ...r, pattern: `${r.pattern_id} ${r.pattern_name}` }));
  const maeMfe = state.backtest?.mae_mfe_analysis || {};
  const maeMfeRegimeRows = selectedId
    ? (maeMfe.by_regime || []).filter((r) => r.regime_id === selectedId)
    : [];
  const maeMfeStrategyRows = selectedId
    ? (maeMfe.by_strategy || []).filter((r) => selectedStrategyIds.has(r.strategy_id))
    : [];
  const maeMfeComboRows = selectedId
    ? (maeMfe.by_regime_strategy || []).filter((r) => r.regime_id === selectedId)
    : [];
  $("regimePerformance").innerHTML = table(
    [
      { label: "Regime", render: (r) => `${r.regime_id} ${r.regime_name}` },
      { label: "Trades", key: "trade_count" },
      { label: "Win", render: (r) => `${(Number(r.win_rate || 0) * 100).toFixed(1)}%` },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Net P/L", render: (r) => `$${fmt(r.net_profit)}` },
      { label: "Profit", render: (r) => `$${fmt(r.gross_profit)}` },
      { label: "Loss", render: (r) => `$${fmt(r.gross_loss)}` },
      { label: "Avg R", key: "average_R" },
      { label: "Max DD", key: "max_drawdown_R" },
      { label: "Streak", key: "max_losing_streak" },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    regimeRows,
    "Click a regime card to show performance for that regime only."
  );

  $("strategyPerformance").innerHTML = table(
    [
      { label: "Strategy", render: (r) => `${r.strategy_id} ${r.strategy_name}` },
      { label: "Trades", key: "trade_count" },
      { label: "Win", render: (r) => `${(Number(r.win_rate || 0) * 100).toFixed(1)}%` },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Net P/L", render: (r) => `$${fmt(r.net_profit)}` },
      { label: "Max DD", key: "max_drawdown_R" },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    strategyRows,
    "Click a regime card to show only its mapped strategy performance."
  );

  $("combinationPerformance").innerHTML = table(
    [
      { label: "Combination", key: "combination_key" },
      { label: "Trades", key: "trade_count" },
      { label: "Win", render: (r) => `${(Number(r.win_rate || 0) * 100).toFixed(1)}%` },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Net P/L", render: (r) => `$${fmt(r.net_profit)}` },
      { label: "3 Loss Prob", key: "probability_of_3_losses" },
      { label: "5 Loss Prob", key: "probability_of_5_losses" },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    combinationRows,
    "Click a regime card to show only its unique regime + strategy + session + modifier-set combinations."
  );
  $("modifierImpact").innerHTML = table(
    [
      { label: "Overlapping Modifier Row", key: "combination_key" },
      { label: "Trades", key: "trade_count" },
      { label: "Win", render: (r) => `${(Number(r.win_rate || 0) * 100).toFixed(1)}%` },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Net P/L", render: (r) => `$${fmt(r.net_profit)}` },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    modifierRows,
    "Click a regime card to show modifier impact. Rows can overlap because one trade can carry several modifiers."
  );
  $("sessionPerformance").innerHTML = table(
    [
      { label: "Session", key: "session" },
      { label: "Trades", key: "trade_count" },
      { label: "Win", render: (r) => `${(Number(r.win_rate || 0) * 100).toFixed(1)}%` },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Net P/L", render: (r) => `$${fmt(r.net_profit)}` },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    selectedSessionRows,
    "Click a regime card to show session context for the latest run."
  );
  $("monthlyPerformance").innerHTML = table(
    [
      { label: "Month", key: "month" },
      { label: "Trades", key: "trade_count" },
      { label: "Win", render: (r) => `${(Number(r.win_rate || 0) * 100).toFixed(1)}%` },
      { label: "PF", key: "profit_factor" },
      { label: "Exp R", key: "expectancy_R" },
      { label: "Net P/L", render: (r) => `$${fmt(r.net_profit)}` },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    selectedMonthlyRows,
    "Click a regime card to show monthly consistency for the latest run."
  );
  const maeHeaders = [
    { label: "Scope", render: (r) => r.regime_id ? `${r.regime_id} ${r.regime_name || ""}` : r.strategy_id ? `${r.strategy_id} ${r.strategy_name || ""}` : `${r.regime_strategy || r.scope || "--"}` },
    { label: "Trades", key: "trade_count" },
    { label: "Avg MAE R", key: "avg_mae_R" },
    { label: "P75 MAE R", key: "p75_mae_R" },
    { label: "Winner P75 MAE", key: "winner_p75_mae_R" },
    { label: "Avg MFE R", key: "avg_mfe_R" },
    { label: "P75 MFE R", key: "p75_mfe_R" },
    { label: "Loser P75 MFE", key: "loser_p75_mfe_R" },
    { label: "Stop Out", render: (r) => `${(Number(r.stop_out_rate || 0) * 100).toFixed(1)}%` },
    { label: "Near-Stop Winners", render: (r) => `${(Number(r.near_stop_winner_rate || 0) * 100).toFixed(1)}%` },
    { label: "Inefficient Loss", render: (r) => `${(Number(r.inefficient_loss_rate || 0) * 100).toFixed(1)}%` },
    { label: "Capture", key: "avg_winner_capture_ratio" },
    { label: "Decision", render: (r) => statusBadge(r.decision || "UNKNOWN") },
    { label: "Recommendation", key: "recommendation" },
  ];
  $("maeMfeRegimeTable").innerHTML = table(
    maeHeaders,
    maeMfeRegimeRows,
    "Click a regime card after a backtest to inspect stop quality for that regime."
  );
  $("maeMfeStrategyTable").innerHTML = table(
    maeHeaders,
    maeMfeStrategyRows,
    "Click a regime card after a backtest to inspect stop quality for its mapped strategies."
  );
  $("maeMfeComboTable").innerHTML = table(
    maeHeaders,
    maeMfeComboRows,
    "Click a regime card after a backtest to inspect regime + strategy stop quality."
  );
  const maeSummary = maeMfe.summary || {};
  const maeNotes = maeMfe.notes || [];
  $("maeMfeNotes").innerHTML = `
    <div class="rounded border border-slate-200 bg-slate-50 p-3">
      <div class="text-xs uppercase text-slate-500">Overall Decision</div>
      <div class="mt-1">${statusBadge(maeSummary.decision || "NO TRADES")}</div>
      <div class="mt-2 text-slate-700">${escapeHtml(maeSummary.recommendation || "Run a backtest with trades to calculate MAE/MFE.")}</div>
      <div class="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div><b>Avg MAE R:</b> ${fmt(maeSummary.avg_mae_R)}</div>
        <div><b>Avg MFE R:</b> ${fmt(maeSummary.avg_mfe_R)}</div>
        <div><b>Winner P75 MAE:</b> ${fmt(maeSummary.winner_p75_mae_R)}</div>
        <div><b>Loser P75 MFE:</b> ${fmt(maeSummary.loser_p75_mfe_R)}</div>
      </div>
    </div>
    ${(maeNotes || []).map((note) => `<p>${escapeHtml(note)}</p>`).join("")}
  `;
  $("patternPerformance").innerHTML = table(
    [
      { label: "Pattern", key: "pattern" },
      { label: "Trades", key: "trade_count" },
      { label: "Win %", render: (r) => `${(Number(r.win_rate || 0) * 100).toFixed(1)}%` },
      { label: "PF", key: "profit_factor" },
      { label: "Expectancy", key: "expectancy_R" },
      { label: "Net P/L", render: (r) => `$${fmt(r.net_profit)}` },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    selectedPatternRows,
    selectedId ? "No pattern performance for selected regime." : "Run a backtest or click a regime card to inspect pattern performance."
  );
  const mt5Rows = [...(state.backtest?.mt5_model_comparison || [])];
  if (state.mt5Import?.model_comparison_row) {
    const imported = state.mt5Import.model_comparison_row;
    const existingIndex = mt5Rows.findIndex((row) => row.model === imported.model);
    if (existingIndex >= 0) mt5Rows[existingIndex] = imported;
    else mt5Rows.push(imported);
  }
  for (const imported of state.mt5Comparison?.rows || []) {
    const existingIndex = mt5Rows.findIndex((row) => row.model === imported.model);
    if (existingIndex >= 0) mt5Rows[existingIndex] = imported;
    else mt5Rows.push(imported);
  }
  $("mt5ModelComparison").innerHTML = table(
    [
      { label: "Model", render: (r) => r.model_name || r.model },
      { label: "Trades", key: "trade_count" },
      { label: "Win %", render: (r) => `${(Number(r.win_rate || 0) * 100).toFixed(1)}%` },
      { label: "PF", key: "profit_factor" },
      { label: "Expectancy", key: "expectancy_R" },
      { label: "Net P/L", render: (r) => `$${fmt(r.net_profit)}` },
      { label: "PF Drift", key: "profit_factor_delta_vs_1m" },
      { label: "Trade Delta", key: "trade_count_delta_vs_1m" },
      { label: "Status", render: (r) => statusBadge(r.status) },
    ],
    mt5Rows,
    "No MT5 model comparison imported yet. Run/import 1-Min OHLC, Every Tick, and Real Ticks for the same setup."
  );
}

function compactContext(ctx = {}) {
  const parts = [
    `ADX:${fmt(ctx.adx)}`,
    `ER:${fmt(ctx.er)}`,
    `ATR%:${fmt(ctx.atr_percentile)}`,
    `Spread%:${fmt(ctx.spread_percentile)}`,
    `MTF:${fmt(ctx.mtf_conflict_score)}`,
    `VWAP:${fmt(ctx.distance_from_vwap_atr)}`,
    `Gap:${fmt(ctx.gap_atr)}`,
  ];
  if (ctx.data_quality_category && ctx.data_quality_category !== "OK") parts.push(`DQType:${ctx.data_quality_category}`);
  if (ctx.data_quality_reasons) parts.push(`DQ:${ctx.data_quality_reasons}`);
  return escapeHtml(parts.join(" | "));
}

function compactPatterns(patterns = []) {
  if (typeof patterns === "string") return patterns ? escapeHtml(patterns) : "--";
  if (!patterns.length) return "--";
  return escapeHtml(patterns.map((p) => `${p.pattern_id || p.pattern_name}:${fmt(p.score)}`).join(" | "));
}

function compactCost(cost = {}) {
  if (!cost || !Object.keys(cost).length) return "--";
  const parts = [
    `spreadR:${fmt(cost.spread_cost_R)}`,
    `commR:${fmt(cost.commission_R)}`,
    `slipR:${fmt(cost.slippage_R)}`,
    `sessX:${fmt(cost.session_cost_multiplier)}`,
    `volX:${fmt(cost.volatility_cost_multiplier)}`,
    `newsX:${fmt(cost.news_cost_multiplier)}`,
    `bucket:${cost.volatility_bucket || "--"}`,
  ];
  return escapeHtml(parts.join(" | "));
}

function renderTrades() {
  const selectedId = state.selectedRegimeId;
  const rows = selectedId ? tradesFor(selectedId) : [];
  $("tradeList").innerHTML = table(
    [
      { label: "Entry", key: "entry_time" },
      { label: "Exit", key: "exit_time" },
      { label: "Regime", render: (r) => `${r.regime_id} ${r.regime_name}` },
      { label: "Modifiers", render: (r) => (r.modifiers || []).join(", ") },
      { label: "Strategy", render: (r) => `${r.strategy_id} ${r.strategy_name}` },
      { label: "Dir", key: "direction" },
      { label: "Entry", render: (r) => formatPrice(r.symbol, r.entry) },
      { label: "SL", render: (r) => formatPrice(r.symbol, r.sl) },
      { label: "TP", render: (r) => formatPrice(r.symbol, r.tp) },
      { label: "Exit", render: (r) => formatPrice(r.symbol, r.exit_price) },
      { label: "Spread", key: "spread_at_entry" },
      { label: "Spread %", key: "spread_percentile" },
      { label: "Slip R", key: "estimated_slippage_R" },
      { label: "MAE R", key: "mae_R" },
      { label: "MFE R", key: "mfe_R" },
      { label: "MAE % Stop", render: (r) => `${fmt(r.mae_percent_of_stop)}%` },
      { label: "MFE/MAE", key: "mfe_to_mae_ratio" },
      { label: "Bars", key: "bars_held" },
      { label: "Max Adverse", render: (r) => formatPrice(r.symbol, r.max_adverse_price) },
      { label: "Max Favorable", render: (r) => formatPrice(r.symbol, r.max_favorable_price) },
      { label: "Gross R", key: "gross_result_R" },
      { label: "Cost R", key: "total_cost_R" },
      { label: "Result R", key: "result_R" },
      { label: "Profit", key: "profit" },
      { label: "Cost Model", key: "cost_model" },
      { label: "Cost Breakdown", render: (r) => compactCost(r.cost_breakdown || {}) },
      { label: "Alpha", key: "alpha_score" },
      { label: "Patterns", render: (r) => compactPatterns(r.patterns_detected || []) },
      { label: "Pattern Score", key: "pattern_score" },
      { label: "Final Score", key: "final_score" },
      { label: "Alpha Breakdown", render: (r) => Object.entries(r.alpha_components || {}).map(([k, v]) => `${k}:${v}`).join(" | ") },
      { label: "Setup Context", render: (r) => compactContext(r.setup_context || {}) },
      { label: "Reason", key: "entry_reason" },
    ],
    rows,
    selectedId ? "No trades for the selected regime." : "Click a regime card to show only that regime's trades."
  );
}

function renderSkippedAndApproval() {
  const selectedId = state.selectedRegimeId;
  const skippedRows = selectedId
    ? (state.backtest?.skipped_setups || []).filter((s) => String(s.regime_candidate || "").startsWith(selectedId))
    : [];
  $("skippedSetups").innerHTML = table(
    [
      { label: "Time", key: "time" },
      { label: "Regime", key: "regime_candidate" },
      { label: "Strategy", key: "strategy_candidate" },
      { label: "Block Reason", key: "block_reason" },
      { label: "Alpha", key: "alpha_score" },
      { label: "Patterns", render: (r) => compactPatterns(r.patterns_detected || []) },
      { label: "Pattern Score", key: "pattern_score" },
      { label: "Final Score", key: "final_score" },
      { label: "Session", key: "session" },
      { label: "Spread %", key: "spread_percentile" },
      { label: "DQ Type", key: "data_quality_category" },
      { label: "DQ Reason", key: "data_quality_reasons" },
      { label: "Setup Context", render: (r) => compactContext(r.setup_context || {}) },
      { label: "Modifiers", render: (r) => (r.modifiers || []).join(", ") },
    ],
    skippedRows.slice(0, 300),
    selectedId ? "No skipped setup candidates for selected regime." : "Click a regime card to show skipped/blocked setup candidates."
  );

  const strategyIds = new Set(strategiesForRegime(selectedId).map((s) => s.strategy_id));
  const checklist = selectedId
    ? (state.backtest?.approval_checklist || []).filter((item) => item.scope === selectedId || strategyIds.has(item.scope))
    : [];
  $("approvalChecklist").innerHTML = checklist.length
    ? checklist
        .map((item) => `
          <div class="border border-slate-200 p-3">
            <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
              <b>${item.scope} ${item.name}</b>
              ${statusBadge(item.status)}
            </div>
            <ul class="space-y-1">
              ${(item.checks || []).map((c) => `<li>${c.passed ? "PASS" : "FAIL"} - ${c.label}: ${fmt(c.value)}</li>`).join("")}
            </ul>
            <p class="mt-2 text-slate-600">${item.decision_reason}</p>
          </div>`)
        .join("")
    : `<p class="text-sm text-slate-500">${selectedId ? "No approval checklist for selected regime yet." : "Click a regime card to show approval checklist."}</p>`;
}

function drawChart(id, type, labels, datasets, options = {}) {
  const canvas = $(id);
  if (!canvas || typeof Chart === "undefined") return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(canvas, {
    type,
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: datasets.length > 1 } },
      scales: { x: { ticks: { maxTicksLimit: 8 } } },
      ...options,
    },
  });
}

function renderMonteCarloChart() {
  const fan = state.monteCarlo?.equity_fan || [];
  drawChart(
    "monteCarloChart",
    "line",
    fan.map((p) => p.trade),
    [
      { label: "P05 Equity", data: fan.map((p) => p.p05_equity), borderColor: "#dc2626", backgroundColor: "rgba(220,38,38,.08)", tension: 0.2 },
      { label: "P50 Equity", data: fan.map((p) => p.p50_equity), borderColor: "#2563eb", backgroundColor: "rgba(37,99,235,.08)", tension: 0.2 },
      { label: "P95 Equity", data: fan.map((p) => p.p95_equity), borderColor: "#16a34a", backgroundColor: "rgba(22,163,74,.08)", tension: 0.2 },
    ],
    { plugins: { legend: { display: true } } }
  );
}

function renderCharts() {
  const selectedId = state.selectedRegimeId;
  const selectedTrades = selectedId ? tradesFor(selectedId) : [];
  let equity = Number(state.backtest?.summary?.initial_equity || $("initialEquity")?.value || 100000);
  let cumulativeR = 0;
  let peakR = 0;
  const equityPoints = [];
  const drawdownPoints = [];
  selectedTrades.forEach((t) => {
    equity += Number(t.profit || 0);
    cumulativeR += Number(t.result_R || 0);
    peakR = Math.max(peakR, cumulativeR);
    equityPoints.push({ label: String(t.exit_time || "").slice(0, 10), value: Number(equity.toFixed(2)) });
    drawdownPoints.push({ label: String(t.exit_time || "").slice(0, 10), value: Number((cumulativeR - peakR).toFixed(4)) });
  });
  const monthly = groupedTradePerformance(selectedTrades, (t) => String(t.entry_time || "").slice(0, 7), "month");
  const sessions = groupedTradePerformance(selectedTrades, (t) => t.session, "session");
  drawChart("equityChart", "line", equityPoints.map((p) => p.label), [{ label: "Equity", data: equityPoints.map((p) => p.value), borderColor: "#2563eb", backgroundColor: "rgba(37,99,235,.12)", tension: 0.2 }]);
  drawChart("drawdownChart", "line", drawdownPoints.map((p) => p.label), [{ label: "Drawdown R", data: drawdownPoints.map((p) => p.value), borderColor: "#dc2626", backgroundColor: "rgba(220,38,38,.12)", tension: 0.2 }]);
  drawChart("monthlyChart", "bar", monthly.map((m) => m.month), [{ label: "Monthly Net P/L", data: monthly.map((m) => m.net_profit), backgroundColor: "#0ea5e9" }]);
  drawChart("sessionChart", "bar", sessions.map((s) => s.session), [{ label: "Session Expectancy R", data: sessions.map((s) => s.expectancy_R), backgroundColor: "#14b8a6" }]);
  renderMonteCarloChart();
}

function renderExplanation() {
  if (!state.selectedRegimeId) {
    $("explanationPanel").innerHTML = `<p class="text-sm text-slate-500">Click a regime card to show analysis for that regime only.</p>`;
    return;
  }
  const regime = state.regimes.find((r) => r.regime_id === state.selectedRegimeId);
  const perf = performanceForRegime(state.selectedRegimeId);
  const stats = tradeStats(tradesFor(state.selectedRegimeId));
  const exp = state.backtest?.explanation || {};
  const group = (title, items) => `
    <div>
      <h3 class="mb-1 font-semibold">${title}</h3>
      ${(items || []).length ? `<ul class="list-disc space-y-1 pl-5">${items.map((x) => `<li>${x}</li>`).join("")}</ul>` : "<p class='text-slate-500'>No items yet.</p>"}
    </div>`;
  const regimeNote = `
    <div>
      <h3 class="mb-1 font-semibold">${regime?.regime_id || ""} ${regime?.regime_name || ""}</h3>
      <p>${perf ? `This regime produced ${perf.trade_count} trade(s), ${fmt(perf.expectancy_R)}R expectancy, ${fmt(perf.profit_factor)} PF, and $${fmt(stats.netProfit)} net P/L.` : "Run a backtest to generate performance analysis for this regime."}</p>
    </div>`;
  const filteredWorked = (exp.what_worked || []).filter((x) => x.includes(state.selectedRegimeId) || x.includes(regime?.regime_name || ""));
  const filteredFailed = (exp.what_failed || []).filter((x) => x.includes(state.selectedRegimeId) || x.includes(regime?.regime_name || ""));
  $("explanationPanel").innerHTML =
    regimeNote +
    group("What Worked", filteredWorked) +
    group("What Failed", filteredFailed) +
    group("Warnings", exp.warnings) +
    group("What To Test Next", exp.what_to_test_next);
}

function renderLlmReview() {
  const result = state.llmReview || {};
  const review = result.review || {};
  $("llmReviewSummary").innerHTML = metricItems([
    ["Status", result.status || "--"],
    ["Verdict", review.verdict || "--"],
    ["Model", result.model || "--"],
    ["Ollama", result.used_ollama ? "used" : "fallback"],
    ["Review", result.review_id ? String(result.review_id).slice(-14) : "--"],
    ["Warnings", (result.warnings || []).length],
  ]);
  const block = (title, items, tone = "slate") => {
    const color = tone === "red" ? "border-red-200 bg-red-50 text-red-900" : tone === "green" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : tone === "amber" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-slate-200 bg-white text-slate-700";
    return `
      <div class="border p-3 ${color}">
        <h3 class="mb-2 font-semibold">${escapeHtml(title)}</h3>
        ${(items || []).length ? `<ul class="list-disc space-y-1 pl-5">${items.map((x) => `<li>${escapeHtml(String(x))}</li>`).join("")}</ul>` : "<p class='text-slate-500'>No items yet.</p>"}
      </div>`;
  };
  $("llmReviewPanel").innerHTML =
    block("Strengths", review.strengths, "green") +
    block("Weaknesses", review.weaknesses, "amber") +
    block("Blockers", review.blockers, "red") +
    block("Next Tests", review.next_tests) +
    block("UI Notes", review.ui_notes) +
    block("Risk Notes", [...(review.risk_notes || []), ...(result.warnings || [])], "amber");
}

function renderFinalApproval() {
  const result = state.finalApproval || {};
  const anti = result.anti_overfit_gate || {};
  const penalty = anti.thresholds?.multiple_test_penalty || {};
  $("finalApprovalSummary").innerHTML = metricItems([
    ["Status", result.status || "--"],
    ["Passed", result.passed_required !== undefined ? `${result.passed_required}/${result.total_required}` : "--"],
    ["Failed", result.failed_required],
    ["Anti-Overfit", anti.status || "--"],
    ["Test Penalty", penalty.level || "--"],
    ["Regime", result.candidate?.regime_filter || $("regimeFilter")?.value || "--"],
    ["Strategy", result.candidate?.strategy_filter || $("strategyFilter")?.value || "--"],
    ["Auto Run", result.inputs_used?.auto_run_missing ? "yes" : "no"],
  ]);
  $("finalApprovalChecks").innerHTML = table(
    [
      { label: "Gate", key: "check" },
      { label: "Required", render: (r) => (r.required ? "yes" : "no") },
      { label: "Status", render: (r) => statusBadge(r.status || (r.passed ? "PASS" : "FAIL")) },
      { label: "Value", key: "value" },
      { label: "Detail", key: "detail" },
    ],
    result.checks || [],
    "Run the final approval gate after optimizer, OOS, walk-forward, Monte Carlo, and MT5 model comparison."
  );
  $("finalApprovalWarnings").innerHTML = result.decision
    ? `<div class="rounded border ${result.status === "FINAL_APPROVED_FOR_DEMO_REVIEW" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-red-200 bg-red-50 text-red-900"} p-3"><b>Decision:</b> ${escapeHtml(result.decision)}</div>`
    : "";
  if ((result.warnings || []).length) {
    $("finalApprovalWarnings").innerHTML += `<div class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-amber-900"><b>Notes:</b> ${escapeHtml(result.warnings.join(" "))}</div>`;
  }
  if (anti.status) {
    const failed = anti.failed_checks || [];
    $("finalApprovalWarnings").innerHTML += `<div class="mt-3 rounded border ${anti.status === "PASS" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-red-200 bg-red-50 text-red-900"} p-3 text-sm"><b>Anti-overfit gate:</b> ${escapeHtml(anti.verdict || anti.status)} ${failed.length ? `Failed checks: ${escapeHtml(failed.map((row) => row.check).join(", "))}` : ""}</div>`;
  }
}

function renderReferences() {
  $("strategyLibrary").innerHTML = table(
    [
      { label: "ID", key: "strategy_id" },
      { label: "Name", key: "strategy_name" },
      { label: "Regime", key: "regime" },
      { label: "Dir", key: "direction" },
      { label: "Category", key: "category" },
      { label: "RR", key: "default_rr" },
    ],
    state.strategies
  );
  $("modifierLibrary").innerHTML = table(
    [
      { label: "ID", key: "id" },
      { label: "Name", key: "name" },
      { label: "Hard Block", render: (r) => (r.hard_block ? statusBadge("BLOCK") : statusBadge("INFO")) },
    ],
    state.modifiers
  );
  $("formulaReference").innerHTML = Object.entries(state.formulas)
    .map(([k, v]) => `<div class="border-b border-slate-200 pb-2"><div class="font-semibold">${k}</div><code class="text-slate-600">${v}</code></div>`)
    .join("");
}

function renderApiStructure() {
  const data = state.apiStructure;
  if (!data) {
    $("apiStructure").innerHTML = `<p class="text-sm text-slate-500">Click Refresh API Structure to load copy-paste request shapes.</p>`;
    return;
  }
  $("apiStructure").innerHTML = data.endpoints
    .map(
      (e) => `
      <div class="border border-slate-200 p-3">
        <div class="mb-1 flex flex-wrap items-center gap-2">
          <span class="badge badge-gray">${e.method}</span>
          <code class="text-sm font-semibold">${e.path}</code>
        </div>
        <p class="mb-2 text-sm text-slate-600">${e.purpose}</p>
        <div class="grid gap-2 md:grid-cols-2">
          <div>
            <div class="mb-1 text-xs font-bold uppercase text-slate-500">Send</div>
            <pre>${JSON.stringify(e.request_body || e.query_params || {}, null, 2)}</pre>
          </div>
          <div>
            <div class="mb-1 text-xs font-bold uppercase text-slate-500">Receive</div>
            <pre>${JSON.stringify(e.response_shape, null, 2)}</pre>
          </div>
        </div>
      </div>`
    )
    .join("");
}

async function sendRegimeStrategyJson(button) {
  const regimeId = button.dataset.regimeId;
  const strategyId = button.dataset.strategyId;
  const key = `${regimeId}_${strategyId}`;
  const input = document.querySelector(`[data-json-input="${key}"]`);
  const output = document.querySelector(`[data-json-output="${key}"]`);
  if (!input || !output) return;

  let parsed;
  try {
    parsed = JSON.parse(input.value);
  } catch (err) {
    output.innerHTML = jsonBlock({
      error: "Invalid JSON",
      detail: err.message,
    });
    return;
  }

  const path = endpointPath(parsed.endpoint);
  const payload = parsed.payload || parsed;
  payload.regime_filter = payload.regime_filter || regimeId;
  payload.strategy_filter = payload.strategy_filter || strategyId;

  button.disabled = true;
  button.textContent = "Sending...";
  output.innerHTML = jsonBlock({
    status: "sending",
    endpoint: parsed.endpoint || `POST ${path}`,
    payload: path.includes("/api/mt5/") ? parsed : payload,
  });

  try {
    const requestBody = path.includes("/api/mt5/") ? parsed : payload;
    const result = await api(path, { method: "POST", body: JSON.stringify(requestBody) });
    if (path === "/api/backtest/run") {
      state.backtest = result;
    }
    state.jsonTesterResponses[key] = {
      status: "ok",
      endpoint: `POST ${path}`,
      sent_payload: requestBody,
      response: path === "/api/backtest/run" ? compactBacktestOutput(result, regimeId, strategyId) : result,
    };
    output.innerHTML = jsonBlock(state.jsonTesterResponses[key]);
    setLoading(`JSON tester complete${result.run_id ? `. Run ID: ${result.run_id}` : `: ${path}`}`);
    if (path === "/api/backtest/run") {
      renderSummary(result.summary || {});
      renderResearchPanels();
      renderPerformanceTables();
      renderTrades();
      renderSkippedAndApproval();
      renderCharts();
      renderExplanation();
    }
  } catch (err) {
    state.jsonTesterResponses[key] = {
      status: "error",
      endpoint: `POST ${path}`,
      sent_payload: path.includes("/api/mt5/") ? parsed : payload,
      error: err.message || String(err),
    };
    output.innerHTML = jsonBlock(state.jsonTesterResponses[key]);
    setError(err);
  } finally {
    button.disabled = false;
    button.textContent = "Send Request";
  }
}

function renderLatest(data) {
  state.latestMarket = data;
  const r = data.active_regime || {};
  const mods = data.modifiers?.modifiers || [];
  const features = data.latest_features || {};
  const allowed = (data.allowed_strategies || []).map((s) => s.strategy_id || s.strategy_name).filter(Boolean);
  const hardReasons = data.modifiers?.hard_block_reasons || [];
  const status = data.hard_block ? "BLOCKED" : r.is_active ? "ACTIVE" : "WATCH";
  const badge = $("currentRegimeBadge");
  if (badge) {
    badge.outerHTML = statusBadge(status).replace("<span", '<span id="currentRegimeBadge"');
  }
  $("latestRegime").innerHTML = `
    <div class="space-y-3">
      <div>
        <div class="text-xs font-bold uppercase text-slate-500">Active Classification</div>
        <div class="text-lg font-bold text-slate-900">${escapeHtml(r.regime_id || "--")} ${escapeHtml(r.regime_name || "")}</div>
        <div class="text-sm text-slate-600">Confidence: <b>${escapeHtml(fmt(r.confidence))}</b> | Direction: <b>${escapeHtml(r.direction || "--")}</b></div>
      </div>
      <div class="grid grid-cols-2 gap-2 text-xs">
        <div class="metric-mini"><b>Session</b><span>${escapeHtml(features.session || "--")}</span></div>
        <div class="metric-mini"><b>ADX</b><span>${escapeHtml(fmt(features.adx))}</span></div>
        <div class="metric-mini"><b>ER</b><span>${escapeHtml(fmt(features.er))}</span></div>
        <div class="metric-mini"><b>Spread %</b><span>${escapeHtml(fmt(features.spread_percentile))}</span></div>
        <div class="metric-mini"><b>HTF</b><span>${escapeHtml(features.htf_bias || "--")}</span></div>
        <div class="metric-mini"><b>LTF</b><span>${escapeHtml(features.ltf_bias || "--")}</span></div>
      </div>
      <div>
        <div class="text-xs font-bold uppercase text-slate-500">Allowed Strategies</div>
        <div>${escapeHtml(allowed.length ? allowed.join(", ") : "--")}</div>
      </div>
      <div>
        <div class="text-xs font-bold uppercase text-slate-500">Modifiers</div>
        <div>${escapeHtml(mods.length ? mods.join(", ") : "--")}</div>
      </div>
      ${hardReasons.length ? `<div class="rounded border border-red-200 bg-red-50 p-2 text-red-800"><b>Hard Block:</b> ${escapeHtml(hardReasons.join("; "))}</div>` : ""}
      <p class="text-slate-600">${escapeHtml(data.explanation || "")}</p>
    </div>`;
  renderSemiManualWatchlist();
}

function renderAll() {
  renderSummary(state.backtest?.summary || {});
  renderValidationCockpit();
  renderWalkForward();
  renderOutOfSample();
  renderPortfolio();
  renderCalibration();
  renderOptimizer();
  renderMonthlyResearch();
  renderMonteCarlo();
  renderMt5Tester();
  renderMt5Parity();
  renderMt5ComparisonImport();
  renderMacroEvidence();
  renderMacroDiagnostics();
  renderBrokerCostCalibration();
  renderRealTickWorkflow();
  renderMt5Import();
  renderSavedData();
  renderResearchPanels();
  renderRegimeCards();
  renderRegimeDetail();
  renderPerformanceTables();
  renderTrades();
  renderSkippedAndApproval();
  renderCharts();
  renderExplanation();
  renderFinalApproval();
  renderSemiManualWatchlist();
  renderLlmReview();
  renderReferences();
  renderApiStructure();
  renderRegimeLab();
  renderValueProfiles();
  renderAbExperiment();
  setupSectionHelp();
  setupCollapsibleSections();
}

function setupCollapsibleSections() {
  const topLevelSections = [...document.querySelectorAll("main > section")].filter((section) => {
    const first = section.firstElementChild;
    return first && !first.classList.contains("table-panel") && !section.className.includes("grid");
  });
  const tablePanels = [...document.querySelectorAll(".table-panel")];
  [...topLevelSections, ...tablePanels].forEach((panel) => {
    if (panel.dataset.collapsibleReady === "true") return;
    const first = panel.firstElementChild;
    if (!first) return;
    const heading = first.matches("h2") ? first : first.querySelector("h2");
    if (!heading) return;
    first.classList.add("section-collapse-header");
    const setCollapsed = (collapsed) => {
      panel.classList.toggle("section-collapsed", collapsed);
      const button = first.querySelector(".section-collapse-toggle");
      if (button) {
        button.textContent = collapsed ? "Show" : "Hide";
        button.setAttribute("aria-expanded", collapsed ? "false" : "true");
      }
    };
    const button = document.createElement("button");
    button.type = "button";
    button.className = "section-collapse-toggle";
    button.setAttribute("aria-label", `Toggle ${heading.textContent.trim() || "section"}`);
    button.textContent = "Hide";
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      setCollapsed(!panel.classList.contains("section-collapsed"));
    });
    button.setAttribute("aria-expanded", "true");
    first.addEventListener("click", (event) => {
      if (event.target.closest("button, a, input, select, textarea, label")) return;
      setCollapsed(!panel.classList.contains("section-collapsed"));
    });
    first.appendChild(button);
    panel.classList.add("collapsible-section");
    panel.dataset.collapsibleReady = "true";
    setCollapsed(true);
  });
}

function currentPayload() {
  const patternEngine = {
    use_patterns: $("usePatterns").checked,
    use_ict: $("useIct").checked,
    use_fvg: $("useFvg").checked,
    use_order_blocks: $("useOrderBlocks").checked,
    use_bos: $("useBos").checked,
    use_mss: $("useMss").checked,
    use_liquidity_pools: $("useLiquidityPools").checked,
    use_round_numbers: $("useRoundNumbers").checked,
    use_vwap: $("useVwap").checked,
    use_mvwap: $("useMvwap").checked,
    use_moving_vwap: $("useMvwap").checked,
    use_session_vwap: $("useSessionVwap").checked,
    pattern_score_mode: $("patternScoreMode").value,
    min_pattern_score: Number($("minPatternScore").value || 2),
    fvg_min_size_atr: Number($("fvgMinSizeAtr").value || 0.2),
    fvg_max_age_bars: Number($("fvgMaxAgeBars").value || 30),
    ob_displacement_body_ratio_min: 0.6,
    ob_displacement_candle_range_atr_min: 1.2,
    ob_max_age_bars: 60,
    vwap_reversion_distance_atr: 1.5,
    bos_atr_buffer: 0.1,
    near_round_number_tolerance_atr: 0.25,
  };
  const filters = {
    use_killzone: $("useKillzone").checked,
    killzone_mode: $("killzoneMode").value,
    allowed_sessions: ["London", "NewYork", "Overlap"],
    use_spread_filter: $("useSpreadFilter").checked,
    spread_filter_mode: $("spreadFilterMode").value,
    max_spread_percentile: Number($("maxSpreadPercentile").value || 70),
    use_alpha: $("useAlpha").checked,
    alpha_mode: $("alphaMode").value,
    min_alpha_score: Number($("minAlphaScore").value || 5),
    strict_regime_validation: $("strictRegimeValidation").checked,
    strict_regime_max_failed_conditions: Number($("strictRegimeMaxFailed").value || 0),
    strict_regime_min_confidence: Number($("strictRegimeMinConfidence").value || 0.75),
    reject_trend_weakening: $("rejectTrendWeakening").checked,
    reject_low_er_clean_trend: $("rejectLowErCleanTrend").checked,
    reject_adx_outside_clean_trend: $("rejectAdxOutsideCleanTrend").checked,
    reject_mtf_conflict_score: $("rejectMtfConflictScore").checked,
    min_clean_trend_er: Number($("minCleanTrendEr").value || 0.25),
    clean_trend_adx_min: Number($("cleanTrendAdxMin").value || 18),
    clean_trend_adx_max: Number($("cleanTrendAdxMax").value || 35),
    max_mtf_conflict_score: 0,
    reject_m08_conflict: $("rejectMtfConflictScore").checked,
    reject_m11_exhaustion: true,
    reject_rollover: true,
    reject_news: true,
  };
  const statisticalRegime = {
    use_statistical_regime: $("useStatisticalRegime")?.checked ?? true,
    use_hurst: $("useHurst")?.checked ?? true,
    use_fractal_dimension: $("useFractalDimension")?.checked ?? true,
    use_kalman: $("useKalman")?.checked ?? true,
    use_garch: $("useGarch")?.checked ?? true,
    use_structural_break: $("useStructuralBreak")?.checked ?? true,
    use_hmm: $("useHmm")?.checked ?? true,
    mode: $("statisticalRegimeMode")?.value || "diagnostic",
    stat_min_confidence: Number($("statMinConfidence")?.value || 0.55),
    stat_block_structural_break: $("statBlockStructuralBreak")?.checked ?? true,
    stat_max_structural_break_score: Number($("statMaxStructuralBreakScore")?.value || 2.5),
  };
  const regimeControls = {
    use_regime_hysteresis: $("useRegimeHysteresis").checked,
    hysteresis_confirm_bars: Number($("hysteresisConfirmBars").value || 3),
    hysteresis_confidence_margin: Number($("hysteresisConfidenceMargin").value || 0.15),
    danger_regime_ids: ["R40", "R10", "R30", "R39", "R09", "R23", "R24", "R38", "R50"],
  };
  const costs = {
    cost_mode: $("costMode").value || "fixed_r",
    cost_r_per_trade: Number($("fixedCostR").value || 0.05),
    commission_R: Number($("commissionR").value || 0),
    slippage_points: Number($("slippagePoints").value || 0),
    spread_round_trip_factor: Number($("spreadRoundTripFactor").value || 1),
    news_cost_multiplier: Number($("newsCostMultiplier").value || 2),
    mt5_imported_cost_R: Number($("mt5ImportedCostR").value || 0.05),
    rollover_block: $("rolloverCostBlock").checked,
  };
  const strategyControls = {
    use_stop_realism: $("useStopRealism")?.checked ?? false,
    use_symbol_session_stop_profile: $("useSymbolSessionStopProfile")?.checked ?? false,
    stop_atr_override: $("useStopRealism")?.checked && $("stopAtrOverride")?.value !== "" ? Number($("stopAtrOverride").value) : null,
    stop_override_mode: $("useStopRealism")?.checked ? ($("stopOverrideMode")?.value || "widen_only") : "off",
    min_effective_stop_spread_mult: $("useStopRealism")?.checked ? Number($("minEffectiveStopSpreadMult")?.value || 0) : 0,
    min_effective_stop_mode: $("minEffectiveStopMode")?.value || "widen",
  };
  const dataSourceControls = currentDataSourceControls(false);
  const payload = {
    symbol: $("symbol").value,
    timeframe: $("timeframe").value,
    start_date: $("startDate").value,
    end_date: $("endDate").value,
    research_mode_preset: $("modePreset")?.value || state.market?.default_mode_preset || "Strict Validation",
    regime_filter: $("regimeFilter").value,
    strategy_filter: $("strategyFilter").value,
    risk_percent: Number($("riskPercent").value),
    rr: Number($("rr").value),
    initial_equity: Number($("initialEquity").value || 100000),
    sentiment: $("sentiment").value,
    usd_bias: $("usdBias").value,
    risk_sentiment: $("riskSentiment").value,
    cb_divergence: $("cbDivergence").value,
    macro_evidence: currentMacroEvidencePayload(),
    use_killzone: $("useKillzone").checked,
    use_spread_filter: $("useSpreadFilter").checked,
    use_sweeps: $("useSweeps").checked,
    use_alpha: $("useAlpha").checked,
    use_feature_cache: $("useFeatureCache")?.checked ?? true,
    killzone_mode: $("killzoneMode").value,
    spread_filter_mode: $("spreadFilterMode").value,
    alpha_mode: $("alphaMode").value,
    strict_clean_trend: $("strictCleanTrend").checked,
    pattern_engine: patternEngine,
    statistical_regime: statisticalRegime,
    data_source_controls: dataSourceControls,
    filters,
    costs,
    calibration: currentCalibrationPayload(),
    regime_controls: regimeControls,
    strategy_controls: strategyControls,
  };
  return state.activeValuePayloadOverride ? deepMerge(payload, state.activeValuePayloadOverride) : payload;
}

function currentWalkForwardPayload() {
  return {
    ...currentPayload(),
    train_months: Number($("wfTrainMonths").value || 2),
    test_months: Number($("wfTestMonths").value || 1),
    step_months: Number($("wfStepMonths").value || 1),
    min_test_trades: Number($("wfMinTestTrades").value || 20),
    min_test_profit_factor: Number($("wfMinTestPf").value || 1.1),
  };
}

function currentOutOfSamplePayload() {
  return {
    ...currentPayload(),
    split_date: $("oosSplitDate").value || null,
    oos_percent: Number($("oosPercent").value || 30),
    min_oos_trades: Number($("oosMinTrades").value || 20),
    min_oos_profit_factor: Number($("oosMinPf").value || 1.1),
  };
}

function currentPortfolioPayload() {
  return {
    ...currentPayload(),
    symbols: parseCsv("portfolioSymbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]),
    timeframes: parseCsv("portfolioTimeframes", ["M15", "M5", "H1"]),
    max_legs: Number($("portfolioMaxLegs").value || 12),
    portfolio_risk: {
      max_drawdown_R: Number($("portfolioMaxDdR")?.value || 12),
      max_symbol_trade_share: Number($("portfolioMaxSymbolShare")?.value || 50) / 100,
      max_symbol_abs_profit_share: 0.60,
      max_timeframe_trade_share: 0.60,
      max_currency_exposure_share: Number($("portfolioMaxCurrencyShare")?.value || 65) / 100,
      min_symbols_with_trades: Number($("portfolioMinSymbols")?.value || 2),
      min_robust_regimes: 1,
      max_average_correlation: 0.75,
      max_trades_per_day: 20,
    },
  };
}

function optimizerValidationSettings() {
  return {
    out_of_sample: {
      split_date: $("oosSplitDate")?.value || null,
      oos_percent: Number($("oosPercent")?.value || 30),
      min_oos_trades: Number($("oosMinTrades")?.value || 20),
      min_oos_profit_factor: Number($("oosMinPf")?.value || 1.1),
    },
    walk_forward: {
      train_months: Number($("wfTrainMonths")?.value || 2),
      test_months: Number($("wfTestMonths")?.value || 1),
      step_months: Number($("wfStepMonths")?.value || 1),
      min_test_trades: Number($("wfMinTestTrades")?.value || 20),
      min_test_profit_factor: Number($("wfMinTestPf")?.value || 1.1),
    },
    monte_carlo: {
      simulations: Number($("mcSimulations")?.value || 1000),
      sample_mode: $("mcSampleMode")?.value || "bootstrap",
      seed: $("mcSeed")?.value === "" ? null : Number($("mcSeed")?.value || 42),
      min_trades: Number($("mcMinTrades")?.value || 30),
      max_total_drawdown_percent: Number($("mcMaxDdPercent")?.value || 10),
      max_losing_streak_limit: Number($("mcMaxLosingStreak")?.value || 5),
    },
    thresholds: {
      min_backtest_trades: Number($("optMinTrades")?.value || $("labMinTrades")?.value || 30),
      min_backtest_pf: Number($("optMinPf")?.value || $("labMinPf")?.value || 1.2),
      min_oos_trades: Number($("oosMinTrades")?.value || 20),
      min_oos_pf: Number($("oosMinPf")?.value || 1.1),
      min_walk_forward_pass_rate: 0.6,
      min_walk_forward_efficiency: 0.5,
      max_mc_drawdown_breach_probability: 0.1,
      max_mc_loss_probability: 0.25,
    },
  };
}

function currentOptimizerPayload() {
  const base = currentPayload();
  const regimeFallback = base.regime_filter && base.regime_filter !== "ALL" ? [base.regime_filter] : ["ALL"];
  const strategyFallback = base.strategy_filter && base.strategy_filter !== "ALL" ? [base.strategy_filter] : ["ALL"];
  return {
    ...base,
    max_combinations: Number($("optMaxCombos").value || 32),
    min_trades: Number($("optMinTrades").value || 30),
    min_profit_factor: Number($("optMinPf").value || 1.2),
    max_drawdown_r: Number($("optMaxDd").value || 10),
    validate_top_n: Number($("optValidateTopN")?.value || 0),
    persist_validated_candidates: $("optPersistValidated")?.checked ?? true,
    validation: optimizerValidationSettings(),
    grid: {
      regime_filters: parseCsv("optRegimes", regimeFallback),
      strategy_filters: parseCsv("optStrategies", strategyFallback),
      rr_values: parseNumberCsv("optRrValues", [base.rr]),
      min_alpha_scores: parseNumberCsv("optAlphaValues", [base.filters.min_alpha_score]),
      max_spread_percentiles: parseNumberCsv("optSpreadValues", [base.filters.max_spread_percentile]),
      killzone_modes: parseCsv("optKillzoneModes", [base.filters.killzone_mode]),
      alpha_modes: [base.filters.alpha_mode],
      spread_filter_modes: [base.filters.spread_filter_mode],
      pattern_score_modes: parseCsv("optPatternModes", [base.pattern_engine.pattern_score_mode]),
      min_pattern_scores: parseNumberCsv("optPatternScores", [base.pattern_engine.min_pattern_score]),
      calibration_profiles: parseCsv("optCalibrationProfiles", [base.calibration.profile || "balanced"]),
      adx_min_values: parseNumberCsv("optCalAdxMinValues", []),
      adx_max_values: parseNumberCsv("optCalAdxMaxValues", []),
      er_min_values: parseNumberCsv("optCalErMinValues", []),
      er_max_values: parseNumberCsv("optCalErMaxValues", []),
      atr_percentile_min_values: parseNumberCsv("optCalAtrMinValues", []),
      atr_percentile_max_values: parseNumberCsv("optCalAtrMaxValues", []),
      candle_range_atr_min_values: parseNumberCsv("optCalCandleMinValues", []),
      candle_range_atr_max_values: parseNumberCsv("optCalCandleMaxValues", []),
      upper_wick_min_values: parseNumberCsv("optCalWickMinValues", []),
      lower_wick_min_values: parseNumberCsv("optCalWickMinValues", []),
      macro_confidence_min_values: parseNumberCsv("optCalMacroConfidenceValues", []),
      confidence_min_values: parseNumberCsv("optCalConfidenceValues", []),
      stop_atr_values: parseNumberCsv("monthlySweepStopGrid", []),
      stop_override_modes: ["widen_only"],
      min_effective_stop_spread_mult_values: parseNumberCsv("monthlySweepMinStopSpread", []),
      use_symbol_session_stop_profile_values: [$("monthlySweepUseProfiles")?.checked ?? true],
    },
  };
}

function currentMonteCarloPayload() {
  return {
    ...currentPayload(),
    simulations: Number($("mcSimulations").value || 1000),
    sample_mode: $("mcSampleMode").value || "bootstrap",
    seed: $("mcSeed").value === "" ? null : Number($("mcSeed").value),
    min_trades: Number($("mcMinTrades").value || 30),
    max_total_drawdown_percent: Number($("mcMaxDdPercent").value || 10),
    max_losing_streak_limit: Number($("mcMaxLosingStreak").value || 5),
  };
}

function currentValidationPayload() {
  return {
    payload: currentPayload(),
    run_backtest: $("valRunBacktest")?.checked ?? true,
    run_oos: $("valRunOos")?.checked ?? true,
    run_walk_forward: $("valRunWalkForward")?.checked ?? true,
    run_monte_carlo: $("valRunMonteCarlo")?.checked ?? true,
    run_portfolio: $("valRunPortfolio")?.checked ?? false,
    require_mt5_comparison: $("valRequireMt5")?.checked ?? false,
    out_of_sample: {
      split_date: $("oosSplitDate").value || null,
      oos_percent: Number($("oosPercent").value || 30),
      min_oos_trades: Number($("oosMinTrades").value || 20),
      min_oos_profit_factor: Number($("oosMinPf").value || 1.1),
    },
    walk_forward: {
      train_months: Number($("wfTrainMonths").value || 2),
      test_months: Number($("wfTestMonths").value || 1),
      step_months: Number($("wfStepMonths").value || 1),
      min_test_trades: Number($("wfMinTestTrades").value || 20),
      min_test_profit_factor: Number($("wfMinTestPf").value || 1.1),
    },
    monte_carlo: {
      simulations: Number($("mcSimulations").value || 1000),
      sample_mode: $("mcSampleMode").value || "bootstrap",
      seed: $("mcSeed").value === "" ? null : Number($("mcSeed").value),
      min_trades: Number($("mcMinTrades").value || 30),
      max_total_drawdown_percent: Number($("mcMaxDdPercent").value || 10),
      max_losing_streak_limit: Number($("mcMaxLosingStreak").value || 5),
    },
    portfolio: {
      symbols: parseCsv("portfolioSymbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]),
      timeframes: parseCsv("portfolioTimeframes", ["M15", "M5", "H1"]),
      max_legs: Number($("portfolioMaxLegs").value || 12),
      portfolio_risk: {
        max_drawdown_R: Number($("portfolioMaxDdR")?.value || 12),
        max_symbol_trade_share: Number($("portfolioMaxSymbolShare")?.value || 50) / 100,
        max_currency_exposure_share: Number($("portfolioMaxCurrencyShare")?.value || 65) / 100,
        min_symbols_with_trades: Number($("portfolioMinSymbols")?.value || 2),
      },
    },
    mt5_comparison: state.mt5Comparison || {},
    thresholds: {
      min_backtest_trades: Number($("valMinBacktestTrades").value || 50),
      min_backtest_pf: Number($("valMinBacktestPf").value || 1.15),
      max_backtest_drawdown_R: Number($("valMaxBacktestDdR").value || 12),
      min_oos_trades: Number($("oosMinTrades").value || 20),
      min_oos_pf: Number($("oosMinPf").value || 1.1),
      min_walk_forward_pass_rate: Number($("valMinWfPassRate").value || 0.6),
      min_walk_forward_efficiency: 0.5,
      max_mc_drawdown_breach_probability: Number($("valMaxMcDdProb").value || 0.1),
      max_mc_loss_probability: Number($("valMaxMcLossProb").value || 0.25),
      max_mc_losing_streak_breach_probability: 0.2,
      min_portfolio_legs: 3,
    },
  };
}

function currentMt5ReportPayload() {
  const base = currentPayload();
  return {
    file_name: $("mt5ReportFileName").value || "pasted_mt5_report",
    test_model: $("mt5ReportModel").value || "every_tick_real_ticks",
    run_id: $("mt5ReportRunId").value || null,
    symbol: base.symbol,
    timeframe: base.timeframe,
    start_date: base.start_date,
    end_date: base.end_date,
    initial_equity: base.initial_equity,
    risk_percent: base.risk_percent,
    max_deals_returned: Number($("mt5ReportMaxDeals").value || 500),
    report_text: $("mt5ReportText").value,
  };
}

function currentMacroEvidencePayload() {
  return {
    mode: $("macroMode").value || "manual",
    symbol: $("symbol").value || "EURUSD",
    start_date: $("startDate").value,
    end_date: $("endDate").value,
    as_of: $("endDate").value,
    dxy_change_percent: Number($("dxyChangePercent").value || 0),
    usd_basket_change_percent: Number($("usdBasketChangePercent").value || 0),
    fed_rate_expectation_change_bp: Number($("fedRateExpectationChangeBp").value || 0),
    us_yield_change_bp: Number($("usYieldChangeBp").value || 0),
    spx_change_percent: Number($("spxChangePercent").value || 0),
    vix_change_percent: Number($("vixChangePercent").value || 0),
    jpy_strength_score: Number($("jpyStrengthScore").value || 0),
    chf_strength_score: Number($("chfStrengthScore").value || 0),
    base_rate_expectation_change_bp: Number($("baseRateExpectationChangeBp").value || 0),
    quote_rate_expectation_change_bp: Number($("quoteRateExpectationChangeBp").value || 0),
    high_impact_news: $("highImpactNews").checked,
    minutes_to_news: Number($("minutesToNews").value || 9999),
    minutes_since_news: Number($("minutesSinceNews").value || 9999),
  };
}

function currentMacroEvidenceReviewPayload() {
  return {
    usd_bias: $("usdBias").value,
    risk_sentiment: $("riskSentiment").value,
    cb_divergence: $("cbDivergence").value,
    macro_evidence: currentMacroEvidencePayload(),
  };
}

function currentMacroDiagnosticsQuery() {
  const params = new URLSearchParams();
  params.set("symbol", $("symbol").value || "EURUSD");
  if ($("startDate").value) params.set("start_date", $("startDate").value);
  if ($("endDate").value) {
    params.set("end_date", $("endDate").value);
    params.set("as_of", $("endDate").value);
  }
  params.set("limit", "50");
  return params.toString();
}

function currentMt5ComparisonPayload() {
  const base = currentPayload();
  return {
    run_id: $("mt5ReportRunId").value || null,
    symbol: base.symbol,
    timeframe: base.timeframe,
    start_date: base.start_date,
    end_date: base.end_date,
    initial_equity: base.initial_equity,
    risk_percent: base.risk_percent,
    max_deals_returned: Number($("mt5ReportMaxDeals").value || 500),
    reports: {
      one_min_ohlc: $("mt5OneMinReportText").value || "",
      every_tick: $("mt5EveryTickReportText").value || "",
      every_tick_real_ticks: $("mt5RealTickReportText").value || "",
    },
    thresholds: {
      min_trades: Number($("mt5CompareMinTrades").value || 30),
      min_profit_factor: Number($("mt5CompareMinPf").value || 1.1),
      min_expectancy_R: 0,
      max_pf_drift: Number($("mt5CompareMaxPfDrift").value || 0.35),
      max_trade_count_drift_pct: Number($("mt5CompareMaxTradeDrift").value || 0.35),
      max_net_profit_degradation_pct: Number($("mt5CompareMaxNetDrop").value || 0.5),
    },
  };
}

function currentBrokerCostCalibrationPayload() {
  return {
    symbol: $("symbol").value || null,
    test_model: "every_tick_real_ticks",
    include_all_models: false,
    import_ids: [],
    limit: 50,
  };
}

function currentMt5TesterPayload() {
  const payload = currentPayload();
  const testModel = $("mt5TesterModel").value || "every_tick_real_ticks";
  payload.mt5_backtest = {
    ...(payload.mt5_backtest || {}),
    test_model: testModel,
    execution_quality: testModel === "every_tick_real_ticks" ? "strict_final_validation" : testModel === "every_tick" ? "normal_validation" : "fast_research",
    spread_mode: testModel === "every_tick_real_ticks" ? "mt5_real_spread" : "model_spread",
    use_python_signals: $("mt5UsePythonSignals")?.checked ?? true,
    require_python_signal_csv: $("mt5UsePythonSignals")?.checked ?? true,
  };
  return {
    payload,
    python_run_id: $("mt5BuildPythonSignals")?.checked ? ($("mt5ReportRunId")?.value || state.backtest?.run_id || null) : null,
    use_python_signals: $("mt5UsePythonSignals")?.checked ?? true,
    build_python_signals: $("mt5BuildPythonSignals")?.checked ?? true,
    copy_python_signals_to_common: true,
    terminal_path: $("mt5TerminalPath").value || null,
    expert: $("mt5ExpertName").value || "QuantForexV10_ResearchEA.ex5",
    launch_terminal: $("mt5LaunchTerminal").checked,
    wait_for_report: $("mt5WaitForReport").checked,
    timeout_seconds: Number($("mt5TimeoutSeconds").value || 120),
    shutdown_terminal: $("mt5ShutdownTerminal").checked,
    visual: $("mt5VisualMode").checked,
    max_deals_returned: Number($("mt5ReportMaxDeals")?.value || 500),
  };
}

function currentMt5ParityPayload() {
  return {
    python_run_id: $("mt5ReportRunId").value || state.backtest?.run_id || null,
    mt5_import_id: state.mt5Import?.import_id || null,
    report_text: $("mt5ReportText").value || null,
    file_name: $("mt5ReportFileName").value || "pasted_mt5_signal_or_report.csv",
    test_model: $("mt5ReportModel").value || "every_tick_real_ticks",
    max_mismatches_returned: 100,
    tolerances: {
      price_tolerance: undefined,
      time_tolerance_seconds: 60,
      result_R_tolerance: 0.05,
      profit_tolerance: 1.0,
    },
  };
}

function currentMt5ParityCompletionPayload() {
  return {
    payload: currentPayload(),
    python_run_id: $("mt5ReportRunId").value || state.backtest?.run_id || null,
    mt5_import_id: state.mt5Import?.import_id || null,
    report_text: $("mt5ReportText").value || null,
    file_name: $("mt5ReportFileName").value || "pasted_mt5_parity_report.csv",
    test_model: $("mt5ReportModel").value || "every_tick_real_ticks",
    prepare_tester_config: $("parityPrepareTester")?.checked ?? true,
    launch_terminal: $("parityLaunchTerminal")?.checked ?? false,
    wait_for_report: $("mt5WaitForReport")?.checked ?? false,
    terminal_path: $("mt5TerminalPath").value || null,
    expert: $("mt5ExpertName").value || "QuantForexV10_ResearchEA.ex5",
    timeout_seconds: Number($("mt5TimeoutSeconds").value || 120),
    shutdown_terminal: $("mt5ShutdownTerminal").checked,
    visual: $("mt5VisualMode").checked,
    max_deals_returned: Number($("mt5ReportMaxDeals")?.value || 5000),
    max_mismatches_returned: 100,
    required_symbol: $("parityRequiredSymbol")?.value || "EURUSD",
    required_timeframe: $("parityRequiredTimeframe")?.value || "M15",
    tolerances: currentMt5ParityPayload().tolerances,
  };
}

function currentRealTickWorkflowPayload() {
  const tester = currentMt5TesterPayload();
  const launchAll = $("realTickLaunchTerminal")?.checked || false;
  const waitForReports = $("realTickWaitForReport")?.checked || false;
  return {
    payload: currentPayload(),
    python_run_id: $("mt5ReportRunId").value || state.backtest?.run_id || null,
    terminal_path: tester.terminal_path,
    expert: tester.expert,
    launch_terminal: launchAll,
    wait_for_report: waitForReports,
    timeout_seconds: tester.timeout_seconds,
    shutdown_terminal: tester.shutdown_terminal,
    visual: tester.visual,
    use_python_signals: $("mt5UsePythonSignals")?.checked ?? true,
    copy_python_signals_to_common: true,
    max_deals_returned: Number($("mt5ReportMaxDeals")?.value || 500),
    reports: currentMt5ComparisonPayload().reports,
    thresholds: currentMt5ComparisonPayload().thresholds,
    parity_tolerances: currentMt5ParityPayload().tolerances,
    max_mismatches_returned: 100,
  };
}

function currentLlmReviewPayload() {
  return {
    payload: currentPayload(),
    backtest: state.backtest || {},
    mt5_comparison: state.mt5Comparison || {},
    mt5_tester: state.mt5Tester || {},
    optimizer: state.optimizer || {},
    walk_forward: state.walkForward || {},
    monte_carlo: state.monteCarlo || {},
    selected_regime: state.selectedRegimeId || null,
    model: $("ollamaModel").value || "llama3.1:8b",
    ollama_url: $("ollamaUrl").value || "http://127.0.0.1:11434",
    use_ollama: $("useOllama").checked,
    timeout_seconds: Number($("ollamaTimeout").value || 120),
  };
}

function currentFinalApprovalPayload() {
  return {
    payload: currentPayload(),
    backtest: state.backtest || {},
    optimizer: state.optimizer || {},
    out_of_sample: state.outOfSample || {},
    walk_forward: state.walkForward || {},
    monte_carlo: state.monteCarlo || {},
    mt5_comparison: state.mt5Comparison || {},
    auto_run_missing: $("faAutoRunMissing").checked,
    thresholds: {
      min_backtest_trades: Number($("faMinBacktestTrades").value || 50),
      min_backtest_pf: Number($("faMinBacktestPf").value || 1.15),
      max_backtest_drawdown_R: Number($("faMaxBacktestDdR").value || 12),
      min_real_tick_trades: Number($("faMinRealTickTrades").value || 30),
      min_real_tick_pf: Number($("faMinRealTickPf").value || 1.10),
      min_oos_trades: Number($("oosMinTrades").value || 20),
      min_oos_pf: Number($("oosMinPf").value || 1.10),
      min_walk_forward_pass_rate: 0.60,
      min_walk_forward_efficiency: 0.50,
      max_mc_drawdown_breach_probability: 0.10,
      max_mc_loss_probability: 0.25,
      max_mc_losing_streak_breach_probability: 0.20,
      max_pf_drift: Number($("mt5CompareMaxPfDrift").value || 0.35),
      max_trade_count_drift_pct: Number($("mt5CompareMaxTradeDrift").value || 0.35),
      max_net_profit_degradation_pct: Number($("mt5CompareMaxNetDrop").value || 0.50),
    },
  };
}

async function detectLatestMarket(showStatus = true) {
  const p = currentPayload();
  if (showStatus) setLoading("Detecting latest regime...");
  const result = await api("/api/regime/detect-latest", {
    method: "POST",
    body: JSON.stringify({
      symbol: p.symbol,
      timeframe: p.timeframe,
      sentiment: p.sentiment,
      usd_bias: p.usd_bias,
      risk_sentiment: p.risk_sentiment,
      cb_divergence: p.cb_divergence,
      macro_evidence: p.macro_evidence,
      data_source_controls: p.data_source_controls,
    }),
  });
  renderLatest(result);
  if (showStatus) setLoading("Latest regime detected.");
  return result;
}

async function hydrate() {
  const [health, market, regimes, strategies, modifiers, formulas, apiStructure, calibration, dataSources] = await Promise.all([
    api("/api/health"),
    api("/api/reference/market"),
    api("/api/reference/regimes"),
    api("/api/reference/strategies"),
    api("/api/reference/modifiers"),
    api("/api/reference/formulas"),
    api("/api/reference/api-structure"),
    api("/api/calibration/profiles"),
    api("/api/data-sources"),
  ]);
  state.market = market;
  state.regimes = regimes;
  state.strategies = strategies;
  state.modifiers = modifiers;
  state.formulas = formulas;
  state.apiStructure = apiStructure;
  state.calibrationProfiles = calibration.profiles || [];
  state.dataSources = dataSources.providers || [];
  state.selectedRegimeId = null;

  $("apiStatus").textContent = `${health.app}: ${health.status}`;
  $("apiStatus").className = "status-pill bg-emerald-50 text-emerald-700";
  selectOptions("modePreset", market.mode_presets || Object.keys(market.research_mode_presets || {}), market.default_mode_preset || "Strict Validation");
  selectOptions("symbol", market.symbols, market.default_symbol);
  selectOptions("timeframe", market.timeframes, market.default_timeframe);
  if (state.dataSources.length) {
    selectOptions("dataSourceType", state.dataSources.map((item) => item.value), dataSources.default || "mt5_retail_candles");
    for (const option of $("dataSourceType").options) {
      const meta = state.dataSources.find((item) => item.value === option.value);
      if (meta) option.textContent = meta.label;
    }
  }
  selectOptions("riskPercent", market.risk_presets.map(String), "1");
  selectOptions("rr", market.rr_presets.map(String), "2");
  selectOptions("sentiment", market.sentiments, "NEUTRAL");
  selectOptions("usdBias", market.usd_biases || ["NEUTRAL", "USD_BULLISH", "USD_BEARISH"], "NEUTRAL");
  selectOptions("riskSentiment", market.risk_sentiments || ["NEUTRAL", "RISK_ON", "RISK_OFF"], "NEUTRAL");
  selectOptions("cbDivergence", market.cb_divergences || ["NEUTRAL", "BULLISH_BASE", "BEARISH_BASE"], "NEUTRAL");
  selectOptions("killzoneMode", market.filter_modes || ["score_only", "hard_filter"], market.research_switches?.killzone_mode || "score_only");
  selectOptions("spreadFilterMode", market.filter_modes || ["score_only", "hard_filter"], market.research_switches?.spread_filter_mode || "score_only");
  selectOptions("alphaMode", market.alpha_modes || ["score_only", "hard_minimum"], market.research_switches?.alpha_mode || "hard_minimum");
  selectOptions("patternScoreMode", market.pattern_score_modes || ["score_only", "hard_minimum"], market.research_switches?.pattern_score_mode || "score_only");
  selectOptions("costMode", market.cost_modes || ["fixed_r", "spread_derived", "mt5_imported", "stress_adjusted"], market.research_switches?.cost_mode || "fixed_r");
  selectOptions("calibrationProfile", (state.calibrationProfiles || []).map((item) => item.profile), "balanced");
  selectOptions("regimeFilter", ["ALL", ...regimes.map((r) => r.regime_id)], "ALL");
  updateStrategyFilterForRegime("ALL", "ALL");
  selectOptions("labRegimeSelect", regimes.map((r) => r.regime_id), regimes[0]?.regime_id || "R01");
  updateLabStrategyOptions("ALL");
  $("initialEquity").value = market.default_initial_equity || 100000;
  $("useKillzone").checked = market.research_switches?.use_killzone ?? true;
  $("useSpreadFilter").checked = market.research_switches?.use_spread_filter ?? true;
  $("useSweeps").checked = market.research_switches?.use_sweeps ?? true;
  $("useAlpha").checked = market.research_switches?.use_alpha ?? true;
  $("useFeatureCache").checked = market.research_switches?.use_feature_cache ?? true;
  $("dataProviderName").value = selectedDataSourceMeta().provider || "MT5 / SQLite";
  renderDataProviderHint();
  $("strictCleanTrend").checked = market.research_switches?.strict_clean_trend ?? true;
  $("minAlphaScore").value = market.research_switches?.min_alpha_score ?? 8;
  $("maxSpreadPercentile").value = market.research_switches?.max_spread_percentile ?? 65;
  $("strictRegimeMaxFailed").value = market.research_switches?.strict_regime_max_failed_conditions ?? 1;
  $("strictRegimeMinConfidence").value = market.research_switches?.strict_regime_min_confidence ?? 0.72;
  $("minCleanTrendEr").value = market.research_switches?.min_clean_trend_er ?? 0.22;
  $("cleanTrendAdxMin").value = market.research_switches?.clean_trend_adx_min ?? 16;
  $("cleanTrendAdxMax").value = market.research_switches?.clean_trend_adx_max ?? 38;
  $("strictRegimeValidation").checked = market.research_switches?.strict_regime_validation ?? false;
  $("rejectTrendWeakening").checked = market.research_switches?.reject_trend_weakening ?? false;
  $("rejectLowErCleanTrend").checked = market.research_switches?.reject_low_er_clean_trend ?? false;
  $("rejectAdxOutsideCleanTrend").checked = market.research_switches?.reject_adx_outside_clean_trend ?? false;
  $("rejectMtfConflictScore").checked = market.research_switches?.reject_mtf_conflict_score ?? false;
  $("useRegimeHysteresis").checked = market.research_switches?.use_regime_hysteresis ?? true;
  $("hysteresisConfirmBars").value = market.research_switches?.hysteresis_confirm_bars ?? 3;
  $("hysteresisConfidenceMargin").value = market.research_switches?.hysteresis_confidence_margin ?? 0.15;
  $("fixedCostR").value = market.research_switches?.cost_r_per_trade ?? 0.05;
  $("commissionR").value = market.research_switches?.commission_R ?? 0;
  $("slippagePoints").value = market.research_switches?.slippage_points ?? 1;
  $("spreadRoundTripFactor").value = market.research_switches?.spread_round_trip_factor ?? 1;
  $("newsCostMultiplier").value = market.research_switches?.news_cost_multiplier ?? 2;
  $("mt5ImportedCostR").value = market.research_switches?.mt5_imported_cost_R ?? 0.05;
  $("rolloverCostBlock").checked = market.research_switches?.rollover_block ?? true;
  $("useStopRealism").checked = market.research_switches?.use_stop_realism ?? false;
  $("useSymbolSessionStopProfile").checked = market.research_switches?.use_symbol_session_stop_profile ?? false;
  $("stopAtrOverride").value = market.research_switches?.stop_atr_override ?? "";
  $("stopOverrideMode").value = market.research_switches?.stop_override_mode ?? "off";
  $("minEffectiveStopSpreadMult").value = market.research_switches?.min_effective_stop_spread_mult ?? 0;
  $("minEffectiveStopMode").value = market.research_switches?.min_effective_stop_mode ?? "widen";
  $("usePatterns").checked = market.research_switches?.use_patterns ?? true;
  $("useIct").checked = market.research_switches?.use_ict ?? true;
  $("useFvg").checked = market.research_switches?.use_fvg ?? true;
  $("useOrderBlocks").checked = market.research_switches?.use_order_blocks ?? true;
  $("useBos").checked = market.research_switches?.use_bos ?? true;
  $("useMss").checked = market.research_switches?.use_mss ?? true;
  $("useLiquidityPools").checked = market.research_switches?.use_liquidity_pools ?? true;
  $("useRoundNumbers").checked = market.research_switches?.use_round_numbers ?? true;
  $("useVwap").checked = market.research_switches?.use_vwap ?? true;
  $("useMvwap").checked = market.research_switches?.use_mvwap ?? true;
  $("useSessionVwap").checked = market.research_switches?.use_session_vwap ?? true;
  $("minPatternScore").value = market.research_switches?.min_pattern_score ?? 2;
  $("fvgMinSizeAtr").value = market.research_switches?.fvg_min_size_atr ?? 0.2;
  $("fvgMaxAgeBars").value = market.research_switches?.fvg_max_age_bars ?? 30;
  $("useStatisticalRegime").checked = market.research_switches?.use_statistical_regime ?? true;
  $("useHurst").checked = market.research_switches?.use_hurst ?? true;
  $("useFractalDimension").checked = market.research_switches?.use_fractal_dimension ?? true;
  $("useKalman").checked = market.research_switches?.use_kalman ?? true;
  $("useGarch").checked = market.research_switches?.use_garch ?? true;
  $("useStructuralBreak").checked = market.research_switches?.use_structural_break ?? true;
  $("useHmm").checked = market.research_switches?.use_hmm ?? true;
  $("statisticalRegimeMode").value = market.research_switches?.statistical_regime_mode ?? "diagnostic";
  $("statMinConfidence").value = market.research_switches?.stat_min_confidence ?? 0.55;
  $("statBlockStructuralBreak").checked = market.research_switches?.stat_block_structural_break ?? true;
  $("statMaxStructuralBreakScore").value = market.research_switches?.stat_max_structural_break_score ?? 2.5;
  applyModePreset($("modePreset")?.value || market.default_mode_preset || "Strict Validation");

  const end = new Date();
  const start = new Date();
  start.setMonth(start.getMonth() - 6);
  $("startDate").value = start.toISOString().slice(0, 10);
  $("endDate").value = end.toISOString().slice(0, 10);
  try {
    const savedSweeps = await api("/api/research/monthly-regime-sweeps?limit=25");
    state.savedMonthlySweeps = savedSweeps.monthly_sweeps || [];
  } catch {
    state.savedMonthlySweeps = [];
  }
  try {
    const savedProfiles = await api("/api/research/value-profiles?limit=25");
    state.savedValueProfiles = savedProfiles.profiles || [];
  } catch {
    state.savedValueProfiles = [];
  }
  renderAll();
  detectLatestMarket(false).catch(() => {
    setText("latestRegime", "Run Detect Latest to show the current market regime.");
  });
}

function bindEvents() {
  $("dataSourceType")?.addEventListener("change", () => {
    const meta = selectedDataSourceMeta();
    $("dataProviderName").value = meta.provider || $("dataSourceType").value;
    $("dataProviderApiKey").value = "";
    renderDataProviderHint();
  });
  $("modePreset").addEventListener("change", () => {
    applyModePreset($("modePreset").value, true);
    renderCalibration();
  });
  $("regimeSearch").addEventListener("input", renderRegimeCards);
  $("regimeFilter").addEventListener("change", () => {
    updateStrategyFilterForRegime($("regimeFilter").value, "ALL");
    renderCalibration();
  });
  $("labRegimeSelect").addEventListener("change", () => {
    renderRegimeLab(true);
  });
  $("labStrategySelect").addEventListener("change", () => {
    $("labStrategiesCsv").value = labStrategyCsv($("labRegimeSelect").value);
    renderRegimeLab(false);
  });
  $("loadRegimeLabDefaults").addEventListener("click", () => {
    renderRegimeLab(true);
    setLoading("Regime Lab defaults loaded for the selected regime.");
  });
  $("applyRegimeLabToControls").addEventListener("click", () => {
    const regimeId = $("labRegimeSelect").value;
    const strategyId = $("labStrategySelect").value;
    $("regimeFilter").value = regimeId;
    updateStrategyFilterForRegime(regimeId, strategyId);
    if (strategyId !== "ALL") $("strategyFilter").value = strategyId;
    renderCalibration();
    setLoading(`Applied ${regimeId}${strategyId !== "ALL" ? ` / ${strategyId}` : ""} to main controls.`);
  });
  $("runRegimeLab").addEventListener("click", async () => {
    try {
      setLoading("Running Regime Research Lab permutations...");
      const result = await api("/api/optimizer/grid", { method: "POST", body: JSON.stringify(currentRegimeLabPayload()) });
      state.regimeLab = result;
      state.optimizer = result;
      renderRegimeLabResult();
      renderOptimizer();
      const best = (result.results || [])[0];
      if (best && $("labRunBestCandidateBacktest").checked) {
        applyCandidateToControls(best);
        setLoading(`Regime Lab optimizer complete. Backtesting best candidate ${best.regime_filter}/${best.strategy_filter}...`);
        const backtest = await api("/api/backtest/run", { method: "POST", body: JSON.stringify(currentPayload()) });
        state.backtest = backtest;
        if ($("mt5ReportRunId")) $("mt5ReportRunId").value = backtest.run_id || "";
        const validators = [];
        if ($("labRunOos").checked) {
          setLoading("Running Regime Lab out-of-sample validation...");
          state.outOfSample = await api("/api/out-of-sample/run", { method: "POST", body: JSON.stringify(currentOutOfSamplePayload()) });
          validators.push(`OOS ${state.outOfSample.summary?.status || "--"}`);
        }
        if ($("labRunWalkForward").checked) {
          setLoading("Running Regime Lab walk-forward validation...");
          state.walkForward = await api("/api/walk-forward/run", { method: "POST", body: JSON.stringify(currentWalkForwardPayload()) });
          validators.push(`WF ${state.walkForward.summary?.status || "--"}`);
        }
        if ($("labRunMonteCarlo").checked) {
          setLoading("Running Regime Lab Monte Carlo probability test...");
          state.monteCarlo = await api("/api/monte-carlo/run", { method: "POST", body: JSON.stringify(currentMonteCarloPayload()) });
          validators.push(`MC ${state.monteCarlo.summary?.status || "--"}`);
        }
        renderAll();
        setLoading(`Regime Lab complete. Best candidate backtested. Run ID: ${backtest.run_id}${validators.length ? ` | ${validators.join(" | ")}` : ""}`);
      } else {
        const s = result.summary || {};
        setLoading(`Regime Lab complete. Run: ${s.combinations_run || 0}, approved candidates: ${s.approved_candidates || 0}.`);
      }
    } catch (err) {
      setError(err);
    }
  });
  $("runMonthlyRegimeSweep").addEventListener("click", async () => {
    try {
      setLoading("Running monthly regime sweep. This can take time when ALL regimes are selected...");
      const result = await api("/api/research/monthly-regime-sweep", { method: "POST", body: JSON.stringify(currentMonthlyResearchPayload()) });
      state.monthlyResearch = result;
      const saved = await api("/api/research/monthly-regime-sweeps?limit=25");
      state.savedMonthlySweeps = saved.monthly_sweeps || [];
      renderMonthlyResearch();
      const s = result.summary || {};
      setLoading(`Monthly sweep complete and saved to DB. Worked candidates: ${s.worked_candidates || 0}, saved rows: ${result.saved_candidate_count || 0}, failed regime-months: ${s.failed_regime_months || 0}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("loadSavedMonthlySweeps").addEventListener("click", async () => {
    try {
      setLoading("Loading saved monthly regime sweeps from SQLite...");
      const result = await api("/api/research/monthly-regime-sweeps?limit=50");
      state.savedMonthlySweeps = result.monthly_sweeps || [];
      renderMonthlyResearch();
      setLoading(`Loaded ${state.savedMonthlySweeps.length} saved monthly sweep runs.`);
    } catch (err) {
      setError(err);
    }
  });
  $("loadCurrentValueProfile").addEventListener("click", () => {
    try {
      loadCurrentValuesIntoProfileEditor(currentPayload());
      setLoading("Current research values loaded into the editable profile.");
    } catch (err) {
      setError(err);
    }
  });
  $("applyEditedValueProfile").addEventListener("click", () => {
    try {
      const payload = editedValueProfilePayload();
      state.activeValuePayloadOverride = payload;
      state.activeValueProfile = {
        profile_id: "edited_not_saved",
        name: $("valueProfileName").value || "Edited unsaved values",
        description: $("valueProfileDescription").value || "",
        payload,
      };
      applyProfilePayloadToVisibleControls(payload);
      renderValueProfiles();
      setLoading("Edited research values applied to future runs. Save the profile to reuse it later.");
    } catch (err) {
      setError(err);
    }
  });
  $("saveValueProfile").addEventListener("click", async () => {
    try {
      const payload = editedValueProfilePayload();
      const result = await api("/api/research/value-profiles", {
        method: "POST",
        body: JSON.stringify({
          name: $("valueProfileName").value || `${payload.regime_filter || "ALL"} ${payload.strategy_filter || "ALL"} values`,
          description: $("valueProfileDescription").value || "",
          payload,
          metrics: profileMetricsSnapshot(),
          source_type: state.monthlyResearch?.monthly_sweep_run_id ? "monthly_sweep" : state.backtest?.run_id ? "backtest" : "manual_ui",
          source_id: state.monthlyResearch?.monthly_sweep_run_id || state.backtest?.run_id || null,
          tags: [payload.regime_filter || "ALL", payload.strategy_filter || "ALL", payload.symbol || "SYMBOL", payload.timeframe || "TF"],
        }),
      });
      state.activeValueProfile = result.profile;
      state.activeValuePayloadOverride = result.profile?.payload || payload;
      const saved = await api("/api/research/value-profiles?limit=50");
      state.savedValueProfiles = saved.profiles || [];
      renderValueProfiles();
      setLoading(`Saved values profile ${result.profile?.profile_id || ""}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("loadSavedValueProfiles").addEventListener("click", async () => {
    try {
      setLoading("Loading saved research value profiles from SQLite...");
      const result = await api("/api/research/value-profiles?limit=50");
      state.savedValueProfiles = result.profiles || [];
      renderValueProfiles();
      setLoading(`Loaded ${state.savedValueProfiles.length} saved value profiles.`);
    } catch (err) {
      setError(err);
    }
  });
  $("savedValueProfilesPanel").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-value-profile-id]");
    if (!button) return;
    try {
      const profileId = button.getAttribute("data-value-profile-id");
      setLoading(`Loading values profile ${profileId}...`);
      const result = await api(`/api/research/value-profiles/${encodeURIComponent(profileId)}`);
      const profile = result.profile || {};
      const payload = profile.payload || {};
      state.activeValueProfile = profile;
      state.activeValuePayloadOverride = payload;
      $("valueProfileName").value = profile.name || "";
      $("valueProfileDescription").value = profile.description || "";
      loadCurrentValuesIntoProfileEditor(payload);
      applyProfilePayloadToVisibleControls(payload);
      renderValueProfiles();
      setLoading(`Loaded and applied values profile ${profile.name || profileId}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("clearActiveValueProfile").addEventListener("click", () => {
    state.activeValueProfile = null;
    state.activeValuePayloadOverride = null;
    renderValueProfiles();
    setLoading("Active research values profile cleared. Current visible controls will be used.");
  });
  $("loadAbFromLab").addEventListener("click", () => {
    const regimeId = $("labRegimeSelect")?.value || $("regimeFilter").value;
    const strategyId = $("labStrategySelect")?.value || $("strategyFilter").value;
    if (regimeId && regimeId !== "ALL") {
      $("regimeFilter").value = regimeId;
      updateStrategyFilterForRegime(regimeId, strategyId);
    }
    if (strategyId && strategyId !== "ALL" && $("strategyFilter")) $("strategyFilter").value = strategyId;
    $("abName").value = `${regimeId || "ALL"} ${strategyId || "ALL"} A/B filter test`;
    $("abHypothesis").value = "A stricter variant should improve expectancy or drawdown without reducing trade count below the decision gate.";
    ensureAbDefaults(true);
    renderAbExperiment();
    setLoading("A/B experiment loaded from the current Regime Lab and research controls.");
  });
  $("runAbExperiment").addEventListener("click", async () => {
    try {
      setLoading("Running A/B experiment baseline and variants...");
      const result = await api("/api/experiments/ab/run", { method: "POST", body: JSON.stringify(currentAbExperimentPayload()) });
      state.abExperiment = result;
      renderAbExperiment();
      const s = result.summary || {};
      setLoading(`A/B experiment complete. Status: ${s.status || "--"}. Best variant: ${s.best_variant_label || "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("loadSavedExperiments").addEventListener("click", async () => {
    try {
      setLoading("Loading saved A/B experiments...");
      const result = await api("/api/experiments?limit=25");
      state.savedExperiments = result.experiments || [];
      renderAbExperiment();
      setLoading(`Loaded ${state.savedExperiments.length} saved A/B experiments.`);
    } catch (err) {
      setError(err);
    }
  });
  $("savedExperimentsPanel").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-experiment-id]");
    if (!button) return;
    try {
      setLoading("Loading saved A/B experiment...");
      state.abExperiment = await api(`/api/experiments/${encodeURIComponent(button.dataset.experimentId)}`);
      renderAbExperiment();
      setLoading(`Loaded A/B experiment ${button.dataset.experimentId}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("calibrationProfile").addEventListener("change", renderCalibration);
  $("previewCalibration").addEventListener("click", () => {
    renderCalibration();
    setLoading("Calibration payload preview refreshed.");
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".json-send-btn");
    if (!button) return;
    sendRegimeStrategyJson(button);
  });
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-favorite-type][data-favorite-id]");
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    const itemType = button.getAttribute("data-favorite-type");
    const itemId = button.getAttribute("data-favorite-id");
    const isFavorite = button.getAttribute("data-favorite-value") === "1";
    try {
      await api("/api/favorites", {
        method: "POST",
        body: JSON.stringify({ item_type: itemType, item_id: itemId, is_favorite: isFavorite }),
      });
      if (itemType === "backtest") {
        state.savedRuns = applyFavoriteState(state.savedRuns, "run_id", itemId, isFavorite);
        renderSavedData();
      } else if (itemType === "validation") {
        state.savedValidationRuns = applyFavoriteState(state.savedValidationRuns, "validation_run_id", itemId, isFavorite);
        renderSavedData();
      } else if (itemType === "experiment") {
        state.savedExperiments = applyFavoriteState(state.savedExperiments, "experiment_id", itemId, isFavorite);
        renderAbExperiment();
      } else if (itemType === "feature") {
        state.savedFeatures = applyFavoriteState(state.savedFeatures, "favorite_id", itemId, isFavorite);
        renderSavedData();
      }
      setLoading(`${isFavorite ? "Starred" : "Unstarred"} ${itemType} ${String(itemId).slice(0, 8)}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("clearResults").addEventListener("click", () => {
    state.backtest = null;
    setText("lastAction", "Results cleared.");
    renderAll();
  });
  $("loadSavedRuns").addEventListener("click", async () => {
    try {
      setLoading("Loading saved backtest runs...");
      const result = await api("/api/backtests?limit=25");
      state.savedRuns = result.runs || [];
      renderSavedData();
      setLoading(`Loaded ${state.savedRuns.length} saved runs.`);
    } catch (err) {
      setError(err);
    }
  });
  $("savedRunsPanel").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-run-id]");
    if (!button) return;
    try {
      const runId = button.getAttribute("data-run-id");
      setLoading(`Loading backtest ${runId}...`);
      const [run, trades] = await Promise.all([
        api(`/api/backtest/${encodeURIComponent(runId)}`),
        api(`/api/backtest/${encodeURIComponent(runId)}/trades`),
      ]);
      state.backtest = { ...run, trades: trades.trades || [] };
      state.selectedRegimeId = null;
      renderAll();
      setLoading(`Loaded saved backtest ${runId}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("loadSavedValidationRuns").addEventListener("click", async () => {
    try {
      setLoading("Loading saved validation runs...");
      const result = await api("/api/validation/runs?limit=50");
      state.savedValidationRuns = result.runs || [];
      renderSavedData();
      setLoading(`Loaded ${state.savedValidationRuns.length} saved validation runs.`);
    } catch (err) {
      setError(err);
    }
  });
  $("savedValidationPanel").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-validation-run-id]");
    if (!button) return;
    try {
      const validationRunId = button.getAttribute("data-validation-run-id");
      setLoading(`Loading validation run ${validationRunId}...`);
      const saved = await api(`/api/validation/runs/${encodeURIComponent(validationRunId)}`);
      const result = saved.result || {};
      if (saved.validation_type === "out_of_sample") state.outOfSample = result;
      else if (saved.validation_type === "walk_forward") state.walkForward = result;
      else if (saved.validation_type === "monte_carlo") state.monteCarlo = result;
      else if (saved.validation_type === "portfolio") state.portfolio = result;
      else if (saved.validation_type === "validation_cockpit") {
        state.validation = result;
        if (result.backtest?.summary) state.backtest = result.backtest;
        if (result.out_of_sample?.summary) state.outOfSample = result.out_of_sample;
        if (result.walk_forward?.summary) state.walkForward = result.walk_forward;
        if (result.monte_carlo?.summary) state.monteCarlo = result.monte_carlo;
        if (result.portfolio?.summary && result.portfolio.summary.status !== "SKIPPED") state.portfolio = result.portfolio;
      } else if (saved.validation_type === "mt5_tester") state.mt5Tester = result;
      else if (saved.validation_type === "mt5_model_comparison") state.mt5Comparison = result;
      else if (saved.validation_type === "mt5_report_import") state.mt5Import = result;
      else if (saved.validation_type === "mt5_real_tick_workflow") state.realTickWorkflow = result;
      else if (saved.validation_type === "monthly_regime_research") state.monthlyResearch = result;
      renderAll();
      setLoading(`Loaded ${saved.validation_type} validation run ${validationRunId}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("savedMonthlySweepsPanel").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-monthly-sweep-run-id]");
    if (!button) return;
    try {
      const runId = button.getAttribute("data-monthly-sweep-run-id");
      setLoading(`Loading monthly sweep ${runId} from SQLite...`);
      state.monthlyResearch = await api(`/api/research/monthly-regime-sweeps/${encodeURIComponent(runId)}`);
      renderMonthlyResearch();
      setLoading(`Loaded monthly sweep ${runId}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("loadSavedFeatures").addEventListener("click", async () => {
    try {
      const p = currentPayload();
      setLoading("Loading saved feature rows...");
      const params = new URLSearchParams({
        symbol: p.symbol,
        timeframe: p.timeframe,
        start_date: p.start_date,
        end_date: p.end_date,
        data_source: p.data_source_controls.data_source,
        limit: "100",
      });
      const result = await api(`/api/features?${params.toString()}`);
      state.savedFeatures = result.features || [];
      renderSavedData();
      setLoading(`Loaded ${state.savedFeatures.length} saved feature rows.`);
    } catch (err) {
      setError(err);
    }
  });
  $("connectMt5").addEventListener("click", async () => {
    try {
      setLoading("Connecting MT5...");
      const result = await api("/api/mt5/connect", { method: "POST", body: "{}" });
      $("mt5Status").textContent = result.connected ? `MT5 connected: ${result.account?.server || "account"}` : "MT5 failed";
      $("mt5Status").className = result.connected ? "status-pill bg-emerald-50 text-emerald-700" : "status-pill bg-red-50 text-red-700";
      setLoading(result.message || result.error || "MT5 check complete.");
    } catch (err) {
      setError(err);
    }
  });
  $("fetchCandles").addEventListener("click", async () => {
    try {
      const p = currentPayload();
      setLoading(`Fetching candles from ${p.data_source_controls.provider || p.data_source_controls.data_source}...`);
      const result = await api("/api/candles/fetch", { method: "POST", body: JSON.stringify({ symbol: p.symbol, timeframe: p.timeframe, start_date: p.start_date, end_date: p.end_date, data_source_controls: currentDataSourceControls(true) }) });
      setLoading(result.error || result.message || `Saved ${result.saved} candles from ${result.provider || p.data_source_controls.provider}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("calcFeatures").addEventListener("click", async () => {
    try {
      const p = currentPayload();
      setLoading("Calculating features...");
      const result = await api("/api/features/calculate", { method: "POST", body: JSON.stringify({ symbol: p.symbol, timeframe: p.timeframe, start_date: p.start_date, end_date: p.end_date, sentiment: p.sentiment, usd_bias: p.usd_bias, risk_sentiment: p.risk_sentiment, cb_divergence: p.cb_divergence, macro_evidence: p.macro_evidence, data_source_controls: p.data_source_controls }) });
      const cacheLabel = result.cached ? "cache hit" : "cache refreshed";
      setLoading(`${cacheLabel}: saved ${result.saved || 0} feature rows.`);
    } catch (err) {
      setError(err);
    }
  });
  $("detectLatest").addEventListener("click", async () => {
    try {
      await detectLatestMarket(true);
    } catch (err) {
      setError(err);
    }
  });
  $("runBacktest").addEventListener("click", async () => {
    try {
      setLoading("Running backtest...");
      const result = await api("/api/backtest/run", { method: "POST", body: JSON.stringify(currentPayload()) });
      state.backtest = result;
      if ($("mt5ReportRunId")) $("mt5ReportRunId").value = result.run_id || "";
      state.savedRuns = (await api("/api/backtests?limit=25")).runs || [];
      setLoading(`Backtest complete. Run ID: ${result.run_id}`);
      renderAll();
    } catch (err) {
      setError(err);
    }
  });
  $("previewMacroEvidence").addEventListener("click", async () => {
    try {
      setLoading("Resolving macro evidence...");
      const result = await api("/api/macro/evidence", { method: "POST", body: JSON.stringify(currentMacroEvidenceReviewPayload()) });
      state.macroEvidence = result;
      renderMacroEvidence();
      setLoading(`Macro evidence resolved: ${result.usd_bias || "--"}, ${result.risk_sentiment || "--"}, ${result.cb_divergence || "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("reviewMacroPipeline").addEventListener("click", async () => {
    try {
      setLoading("Reviewing macro evidence pipeline...");
      const result = await api(`/api/macro/diagnostics?${currentMacroDiagnosticsQuery()}`);
      state.macroDiagnostics = result;
      state.macroEvidence = result.resolved || state.macroEvidence;
      renderMacroEvidence();
      renderMacroDiagnostics();
      setLoading(`Macro pipeline status: ${result.status || "NO_EVIDENCE"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("importMacroCsv").addEventListener("click", async () => {
    try {
      setLoading("Importing macro CSV evidence...");
      const result = await api("/api/macro/import-csv", {
        method: "POST",
        body: JSON.stringify({
          source: $("macroCsvSource").value || "macro_research_csv",
          csv_text: $("macroCsvText").value,
        }),
      });
      state.macroEvidence = result.latest?.resolved || state.macroEvidence;
      renderMacroImportResult(result, "macro rows");
      renderMacroEvidence();
      setLoading(`Imported ${result.saved} macro evidence rows.`);
    } catch (err) {
      setError(err);
    }
  });
  $("importMacroFeedText").addEventListener("click", async () => {
    try {
      setLoading("Importing macro/news feed text...");
      const result = await api("/api/macro/import-feed", {
        method: "POST",
        body: JSON.stringify({
          source: $("macroCsvSource").value || "macro_feed_text",
          feed_type: $("macroFeedType").value || "macro",
          feed_format: $("macroFeedFormat").value || "csv",
          feed_text: $("macroCsvText").value,
        }),
      });
      state.macroEvidence = result.latest?.resolved || state.macroEvidence;
      renderMacroImportResult(result, "feed rows");
      renderMacroEvidence();
      setLoading(`Imported ${result.saved} feed rows.`);
    } catch (err) {
      setError(err);
    }
  });
  $("importMacroUrl").addEventListener("click", async () => {
    try {
      setLoading("Importing macro URL feed...");
      const result = await api("/api/macro/import-url", {
        method: "POST",
        body: JSON.stringify({
          url: $("macroCsvUrl").value,
          source: $("macroUrlSource").value || "macro_feed_url",
          feed_type: $("macroUrlFeedType").value || "macro",
          feed_format: $("macroUrlFeedFormat").value || "auto",
          timeout_seconds: 15,
        }),
      });
      state.macroEvidence = result.latest?.resolved || state.macroEvidence;
      renderMacroImportResult(result, "URL feed rows");
      renderMacroEvidence();
      setLoading(`Imported ${result.saved} macro evidence rows from URL.`);
    } catch (err) {
      setError(err);
    }
  });
  $("importCrossPairEvidence").addEventListener("click", async () => {
    try {
      setLoading("Building cross-pair macro evidence from saved candles...");
      const symbols = ($("macroCrossPairSymbols").value || "")
        .split(",")
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean);
      const result = await api("/api/macro/cross-pair/import", {
        method: "POST",
        body: JSON.stringify({
          symbol: $("symbol").value || "EURUSD",
          timeframe: $("timeframe").value || "M15",
          start_date: $("startDate").value,
          end_date: $("endDate").value,
          symbols,
          source: $("macroCsvSource").value || "cross_pair_candles",
          data_source_controls: currentPayload().data_source_controls,
        }),
      });
      state.macroEvidence = result.latest?.resolved || state.macroEvidence;
      renderMacroImportResult(result, "cross-pair evidence rows");
      renderMacroEvidence();
      setLoading(`Built cross-pair evidence from ${result.cross_pair_summary?.symbols_used || 0} symbols.`);
    } catch (err) {
      setError(err);
    }
  });
  $("importCotEvidence").addEventListener("click", async () => {
    try {
      setLoading("Importing official CFTC COT positioning...");
      const symbols = ($("cotSymbols").value || "")
        .split(",")
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean);
      const result = await api("/api/macro/cot/import", {
        method: "POST",
        body: JSON.stringify({
          symbols,
          as_of: $("cotAsOf").value || null,
          source: $("cotSource").value || "cftc_tff_cot",
          report_type: $("cotReportType").value || "Combined",
          timeout_seconds: 20,
        }),
      });
      state.macroEvidence = result.latest?.resolved || state.macroEvidence;
      renderMacroImportResult(result, "COT rows");
      renderMacroEvidence();
      setLoading(`Imported ${result.saved} COT evidence rows.`);
    } catch (err) {
      setError(err);
    }
  });
  $("calibrateBrokerCost").addEventListener("click", async () => {
    try {
      setLoading("Calibrating broker costs from imported MT5 reports...");
      const result = await api("/api/cost/calibration", { method: "POST", body: JSON.stringify(currentBrokerCostCalibrationPayload()) });
      state.brokerCostCalibration = result;
      renderBrokerCostCalibration();
      setLoading(`Broker cost calibration: ${result.status || "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("applyBrokerCostCalibration").addEventListener("click", () => {
    const rec = state.brokerCostCalibration?.recommended_costs || {};
    if (!Object.keys(rec).length) {
      setError(new Error("Run broker cost calibration before applying it."));
      return;
    }
    $("costMode").value = rec.cost_mode || "mt5_imported";
    $("mt5ImportedCostR").value = rec.mt5_imported_cost_R ?? $("mt5ImportedCostR").value;
    if (rec.commission_R !== undefined) $("commissionR").value = rec.commission_R;
    if (rec.slippage_points !== undefined) $("slippagePoints").value = rec.slippage_points;
    if (rec.rollover_block !== undefined) $("rolloverCostBlock").checked = Boolean(rec.rollover_block);
    setLoading(`Applied calibrated broker cost R: ${rec.mt5_imported_cost_R ?? "--"}.`);
  });
  $("runMt5Tester").addEventListener("click", async () => {
    try {
      setLoading("Preparing MT5 Strategy Tester run...");
      const result = await api("/api/mt5/tester/run", { method: "POST", body: JSON.stringify(currentMt5TesterPayload()) });
      state.mt5Tester = result;
      if (result.report_import) state.mt5Import = result.report_import;
      renderMt5Tester();
      renderMt5Import();
      renderPerformanceTables();
      setLoading(`MT5 tester status: ${result.status || "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("buildParityPacket").addEventListener("click", async () => {
    try {
      const runId = $("mt5ReportRunId").value || state.backtest?.run_id;
      if (!runId) throw new Error("Run a Python backtest first or enter a saved run_id.");
      setLoading("Building Python/MT5 parity packet...");
      const result = await api(`/api/backtest/${encodeURIComponent(runId)}/mt5-parity-packet`);
      state.mt5ParityPacket = result;
      renderMt5Parity();
      setLoading(`Parity packet ready. Expected trades: ${result.expected_trade_count || 0}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("checkMt5Parity").addEventListener("click", async () => {
    try {
      const payload = currentMt5ParityPayload();
      if (!payload.python_run_id) throw new Error("Run a Python backtest first or enter a saved run_id.");
      if (!payload.mt5_import_id && !payload.report_text) throw new Error("Import/paste an MT5 report or signal CSV before parity checking.");
      setLoading("Checking Python vs MT5 parity...");
      const result = await api("/api/mt5/parity/check-run-report", { method: "POST", body: JSON.stringify(payload) });
      state.mt5Parity = result;
      renderMt5Parity();
      setLoading(`Parity check complete: ${result.status || "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("completeMt5Parity").addEventListener("click", async () => {
    try {
      setLoading("Running institutional Python/MT5 parity completion...");
      const result = await api("/api/mt5/parity/complete", { method: "POST", body: JSON.stringify(currentMt5ParityCompletionPayload()) });
      state.mt5ParityCompletion = result;
      state.mt5ParityPacket = result.packet || state.mt5ParityPacket;
      if (result.parity_check) state.mt5Parity = result.parity_check;
      if (result.tester_run) state.mt5Tester = result.tester_run;
      if (result.mt5_import) state.mt5Import = result.mt5_import;
      if (result.python_run_id && $("mt5ReportRunId")) $("mt5ReportRunId").value = result.python_run_id;
      renderMt5Parity();
      renderMt5Tester();
      renderMt5Import();
      setLoading(`Parity completion: ${result.status || "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("runRealTickWorkflow").addEventListener("click", async () => {
    try {
      setLoading("Preparing real-tick validation workflow...");
      const result = await api("/api/mt5/real-tick-workflow", { method: "POST", body: JSON.stringify(currentRealTickWorkflowPayload()) });
      state.realTickWorkflow = result;
      if (result.model_comparison) state.mt5Comparison = result.model_comparison;
      renderRealTickWorkflow();
      renderMt5ComparisonImport();
      renderPerformanceTables();
      setLoading(`Real-tick workflow: ${result.status || "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("runValidationCockpit").addEventListener("click", async () => {
    try {
      setLoading("Running full validation cockpit...");
      const result = await api("/api/validation/cockpit", { method: "POST", body: JSON.stringify(currentValidationPayload()) });
      state.validation = result;
      if (result.backtest?.summary) state.backtest = result.backtest;
      if (result.out_of_sample?.summary) state.outOfSample = result.out_of_sample;
      if (result.walk_forward?.summary) state.walkForward = result.walk_forward;
      if (result.monte_carlo?.summary) state.monteCarlo = result.monte_carlo;
      if (result.portfolio?.summary && result.portfolio.summary.status !== "SKIPPED") state.portfolio = result.portfolio;
      if (result.final_approval) state.finalApproval = result.final_approval;
      renderAll();
      const s = result.summary || {};
      setLoading(`Validation cockpit: ${s.status || "--"} score ${s.validation_score ?? "--"}/100.`);
    } catch (err) {
      setError(err);
    }
  });
  $("runWalkForward").addEventListener("click", async () => {
    try {
      setLoading("Running walk-forward windows...");
      const result = await api("/api/walk-forward/run", { method: "POST", body: JSON.stringify(currentWalkForwardPayload()) });
      state.walkForward = result;
      renderWalkForward();
      const s = result.summary || {};
      setLoading(`Walk-forward complete. Windows: ${s.windows || 0}, Pass: ${s.passed_windows || 0}, Stable: ${s.stable ? "yes" : "no"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("runOutOfSample").addEventListener("click", async () => {
    try {
      setLoading("Running out-of-sample validation...");
      const result = await api("/api/out-of-sample/run", { method: "POST", body: JSON.stringify(currentOutOfSamplePayload()) });
      state.outOfSample = result;
      renderOutOfSample();
      const s = result.summary || {};
      setLoading(`Out-of-sample complete. Status: ${s.status || "--"}, Stable: ${s.stable ? "yes" : "no"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("runPortfolioBacktest").addEventListener("click", async () => {
    try {
      setLoading("Running portfolio research across symbols/timeframes...");
      const result = await api("/api/portfolio/backtest", { method: "POST", body: JSON.stringify(currentPortfolioPayload()) });
      state.portfolio = result;
      renderPortfolio();
      const s = result.summary || {};
      setLoading(`Portfolio complete. Status: ${s.status || "--"}, legs: ${s.legs_completed || 0}/${s.legs_requested || 0}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("runOptimizerGrid").addEventListener("click", async () => {
    try {
      setLoading("Running optimizer grid...");
      const result = await api("/api/optimizer/grid", { method: "POST", body: JSON.stringify(currentOptimizerPayload()) });
      state.optimizer = result;
      renderOptimizer();
      const s = result.summary || {};
      setLoading(`Optimizer complete. Run: ${s.combinations_run || 0}, approved candidates: ${s.approved_candidates || 0}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("runMonteCarlo").addEventListener("click", async () => {
    try {
      setLoading("Running Monte Carlo drawdown test...");
      const result = await api("/api/monte-carlo/run", { method: "POST", body: JSON.stringify(currentMonteCarloPayload()) });
      state.monteCarlo = result;
      renderMonteCarlo();
      const s = result.summary || {};
      setLoading(`Monte Carlo complete. Status: ${s.status || "--"}, DD breach: ${s.probability_drawdown_breach !== undefined ? `${(Number(s.probability_drawdown_breach) * 100).toFixed(1)}%` : "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("importMt5Report").addEventListener("click", async () => {
    try {
      setLoading("Importing MT5 Strategy Tester report...");
      const result = await api("/api/mt5/report/import", { method: "POST", body: JSON.stringify(currentMt5ReportPayload()) });
      state.mt5Import = result;
      renderMt5Import();
      renderPerformanceTables();
      const s = result.summary || {};
      setLoading(`MT5 report imported. Trades: ${s.trade_count || 0}, PF: ${fmt(s.profit_factor)}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("importMt5Comparison").addEventListener("click", async () => {
    try {
      setLoading("Importing MT5 model comparison reports...");
      const result = await api("/api/mt5/model-comparison/import", { method: "POST", body: JSON.stringify(currentMt5ComparisonPayload()) });
      state.mt5Comparison = result;
      renderMt5ComparisonImport();
      renderPerformanceTables();
      setLoading(`MT5 model comparison: ${result.status || "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("runLlmReview").addEventListener("click", async () => {
    try {
      setLoading("Running quant reviewer...");
      const result = await api("/api/llm/review", { method: "POST", body: JSON.stringify(currentLlmReviewPayload()) });
      state.llmReview = result;
      renderLlmReview();
      setLoading(`Reviewer complete: ${result.review?.verdict || result.status || "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("runFinalApproval").addEventListener("click", async () => {
    try {
      setLoading("Running final approval gate...");
      const result = await api("/api/final-approval/review", { method: "POST", body: JSON.stringify(currentFinalApprovalPayload()) });
      state.finalApproval = result;
      renderFinalApproval();
      renderSemiManualWatchlist();
      setLoading(`Final approval: ${result.status || "--"}.`);
    } catch (err) {
      setError(err);
    }
  });
  $("loadApiStructure").addEventListener("click", async () => {
    try {
      state.apiStructure = await api("/api/reference/api-structure");
      renderApiStructure();
      setLoading("API structure refreshed.");
    } catch (err) {
      setError(err);
    }
  });
}

hydrate()
  .then(() => {
    bindEvents();
    setText("lastAction", "Reference data loaded.");
  })
  .catch((err) => {
    $("apiStatus").textContent = "API error";
    $("apiStatus").className = "status-pill bg-red-50 text-red-700";
    setError(err);
  });
