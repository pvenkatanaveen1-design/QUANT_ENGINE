#property strict
#property version   "1.00"
#property description "quant_forex_V10 research EA for MT5 Strategy Tester only."

#include <Trade/Trade.mqh>

CTrade Trade;

input string Symbol = "";
input string Timeframe = "M15";
input string StartDate = "";
input string EndDate = "";
input string RegimeFilter = "ALL";
input string StrategyFilter = "ALL";
input double RiskPercent = 1.0;
input double RR = 2.0;
input double InitialEquity = 100000.0;
input string Sentiment = "NEUTRAL";
input string UsdBias = "NEUTRAL";
input string RiskSentiment = "NEUTRAL";
input string CbDivergence = "NEUTRAL";

input bool UsePatterns = true;
input bool UseICT = true;
input bool UseFVG = true;
input bool UseOrderBlocks = true;
input bool UseBOS = true;
input bool UseMSS = true;
input bool UseLiquidityPools = true;
input bool UseRoundNumbers = true;
input bool UseVWAP = true;
input bool UseMVWAP = true;
input bool UseSessionVWAP = true;
input string PatternScoreMode = "score_only";
input int MinPatternScore = 2;
input double FVGMinSizeATR = 0.20;
input int FVGMaxAgeBars = 30;
input double OBDisplacementBodyRatioMin = 0.60;
input double OBDisplacementCandleRangeATRMin = 1.20;
input int OBMaxAgeBars = 60;
input double VWAPReversionDistanceATR = 1.50;
input double BOSATRBuffer = 0.10;
input double RoundNumberToleranceATR = 0.25;

input bool UseKillzone = true;
input string KillzoneMode = "score_only";
input string AllowedSessions = "London,NewYork,Overlap";
input bool UseSpreadFilter = true;
input string SpreadFilterMode = "score_only";
input double MaxSpreadPercentile = 70.0;
input bool UseSweeps = true;
input bool UseAlpha = true;
input string AlphaMode = "hard_minimum";
input int MinAlphaScore = 5;
input bool StrictCleanTrend = true;
input bool StrictRegimeValidation = true;
input bool RejectTrendWeakening = false;
input bool RejectLowERCleanTrend = false;
input bool RejectADXOutsideCleanTrendBand = false;
input bool RejectMTFConflictScore = false;
input double MinCleanTrendER = 0.25;
input int MaxMTFConflictScore = 0;
input bool RejectM08Conflict = true;
input bool RejectM11Exhaustion = true;
input bool RejectNews = true;
input bool RejectRollover = true;

input string EntryPrice = "signal_close";
input string SLTPMode = "strategy_defined";
input string SameCandleSLTP = "mt5_model_decides";
input bool OneTradeAtATime = true;
input int MaxTradesPerDay = 3;

input int MagicNumber = 401040;
input int LookbackBars = 300;
input int SwingLookback = 20;
input int ERPeriod = 30;
input int ATRPercentileLookback = 252;
input bool AllowNonTesterExecution = false;
input string NonTesterSafetyConfirm = "";
input bool WriteSignalCsv = true;
input bool UsePythonSignalCsv = false;
input bool RequirePythonSignalCsv = true;
input string PythonSignalCsvFile = "QuantForexV10_python_signals.csv";
input int PythonSignalTimeToleranceSeconds = 60;

bool NonTesterSafetyWarningPrinted = false;

string RequiredNonTesterSafetyConfirm()
{
   return "I_UNDERSTAND_THIS_CAN_TRADE_LIVE";
}

bool TesterSafetyAllowed()
{
   if(MQLInfoInteger(MQL_TESTER))
      return true;
   if(!AllowNonTesterExecution)
   {
      Alert("quant_forex_V10 ResearchEA blocked: Strategy Tester only. AllowNonTesterExecution=false.");
      Print("quant_forex_V10 ResearchEA blocked: Strategy Tester only. This EA is for Tab 1 research/backtest validation.");
      return false;
   }
   if(NonTesterSafetyConfirm != RequiredNonTesterSafetyConfirm())
   {
      Alert("DANGER: non-tester execution requested but safety confirmation token is missing or invalid. EA blocked.");
      Print("DANGER: AllowNonTesterExecution=true requires NonTesterSafetyConfirm=", RequiredNonTesterSafetyConfirm(), ". EA blocked outside Strategy Tester.");
      return false;
   }
   if(!NonTesterSafetyWarningPrinted)
   {
      Alert("DANGER: quant_forex_V10 ResearchEA is running outside Strategy Tester and can send demo/live orders.");
      Print("DANGER: AllowNonTesterExecution=true confirmed. Use only controlled demo testing. Never use on funded/live accounts.");
      NonTesterSafetyWarningPrinted = true;
   }
   return true;
}

int Ema20Handle = INVALID_HANDLE;
int Ema50Handle = INVALID_HANDLE;
int AtrHandle = INVALID_HANDLE;
int AdxHandle = INVALID_HANDLE;
ENUM_TIMEFRAMES TradeTF = PERIOD_M15;
datetime LastBarTime = 0;
datetime CurrentDay = 0;
int TradesToday = 0;
int SignalLogHandle = INVALID_HANDLE;
int PythonSignalCount = 0;

struct PythonSignal
{
   int parity_index;
   string parity_hash;
   datetime entry_time;
   string symbol;
   string timeframe;
   string regime_id;
   string strategy_id;
   string direction;
   double entry;
   double sl;
   double tp;
   double result_R;
   double profit;
   double alpha_score;
   double pattern_score;
   double final_score;
   double initial_risk;
   string patterns_detected;
   string comment;
   bool used;
};

PythonSignal PythonSignals[];

struct FeatureState
{
   datetime bar_time;
   string regime;
   string session;
   string htf_bias;
   string ltf_bias;
   double open;
   double high;
   double low;
   double close;
   double prev_close;
   double ema20;
   double ema50;
   double ema20_prev;
   double ema50_prev;
   double atr;
   double adx;
   double adx_prev5;
   double plus_di;
   double minus_di;
   double er;
   double er_prev5;
   double atr_percentile;
   double spread_percentile;
   double swing_high;
   double swing_low;
   double recent_high3;
   double recent_low3;
   double session_vwap;
   double mvwap20;
   double mvwap50;
   double vwap_distance_atr;
   double candle_range_atr;
   double body_ratio;
   double upper_wick_ratio;
   double lower_wick_ratio;
   bool sweep_high;
   bool sweep_low;
   bool bos_bull;
   bool bos_bear;
   bool mss_bull;
   bool mss_bear;
   bool trend_weakening;
   bool gap_flag;
   bool data_quality_error;
   int mtf_conflict_score;
};

struct PatternState
{
   int score;
   string labels;
   bool long_bias;
   bool short_bias;
};

string TradeSymbol()
{
   if(StringLen(Symbol) > 0)
      return Symbol;
   return _Symbol;
}

string Upper(string value)
{
   string v = value;
   StringToUpper(v);
   return v;
}

string Lower(string value)
{
   string v = value;
   StringToLower(v);
   return v;
}

ENUM_TIMEFRAMES ParseTimeframe(string tf)
{
   string v = Upper(tf);
   if(v == "M1") return PERIOD_M1;
   if(v == "M5") return PERIOD_M5;
   if(v == "M15") return PERIOD_M15;
   if(v == "M30") return PERIOD_M30;
   if(v == "H1") return PERIOD_H1;
   if(v == "H4") return PERIOD_H4;
   if(v == "D1") return PERIOD_D1;
   return PERIOD_CURRENT;
}

datetime ParseInputDate(string value, bool end_of_day)
{
   if(StringLen(value) == 0)
      return 0;
   string v = value;
   StringReplace(v, "-", ".");
   if(StringLen(v) <= 10)
      v += end_of_day ? " 23:59" : " 00:00";
   return StringToTime(v);
}

bool InDateRange(datetime t)
{
   datetime start = ParseInputDate(StartDate, false);
   datetime end = ParseInputDate(EndDate, true);
   if(start > 0 && t < start)
      return false;
   if(end > 0 && t > end)
      return false;
   return true;
}

bool IsAll(string value)
{
   return StringLen(value) == 0 || Upper(value) == "ALL";
}

bool StringOptionEnabled(string mode, string enabled_value)
{
   return StringCompare(Lower(mode), Lower(enabled_value)) == 0;
}

double SafeDiv(double a, double b)
{
   if(MathAbs(b) <= 0.0000000001)
      return 0.0;
   return a / b;
}

double BodyRatio(const MqlRates &bar)
{
   double range = bar.high - bar.low;
   if(range <= 0)
      return 0.0;
   return MathAbs(bar.close - bar.open) / range;
}

datetime ParseSignalTime(string value)
{
   string v = value;
   StringReplace(v, "-", ".");
   StringReplace(v, "T", " ");
   int plus_pos = StringFind(v, "+");
   if(plus_pos > 0)
      v = StringSubstr(v, 0, plus_pos);
   if(StringLen(v) > 16)
      v = StringSubstr(v, 0, 16);
   return StringToTime(v);
}

void SkipCsvFields(int handle, int count)
{
   for(int i = 0; i < count && !FileIsEnding(handle); i++)
      FileReadString(handle);
}

bool LoadPythonSignals()
{
   if(!UsePythonSignalCsv)
      return true;

   int handle = FileOpen(PythonSignalCsvFile, FILE_READ | FILE_CSV | FILE_COMMON, ',');
   if(handle == INVALID_HANDLE)
      handle = FileOpen(PythonSignalCsvFile, FILE_READ | FILE_CSV, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("Python signal CSV not found: ", PythonSignalCsvFile, ". Copy it to MT5 Common/Files or disable UsePythonSignalCsv.");
      return !RequirePythonSignalCsv;
   }

   PythonSignalCount = 0;
   ArrayResize(PythonSignals, 0);
   if(!FileIsEnding(handle))
   {
      FileReadString(handle);
      SkipCsvFields(handle, 20);
   }

   while(!FileIsEnding(handle))
   {
      string idx_text = FileReadString(handle);
      if(StringLen(idx_text) == 0 && FileIsEnding(handle))
         break;
      PythonSignal sig;
      sig.parity_index = (int)StringToInteger(idx_text);
      sig.parity_hash = FileReadString(handle);
      sig.entry_time = ParseSignalTime(FileReadString(handle));
      FileReadString(handle); // exit_time from Python research
      sig.symbol = FileReadString(handle);
      sig.timeframe = FileReadString(handle);
      sig.regime_id = FileReadString(handle);
      sig.strategy_id = FileReadString(handle);
      sig.direction = Lower(FileReadString(handle));
      sig.entry = StringToDouble(FileReadString(handle));
      sig.sl = StringToDouble(FileReadString(handle));
      sig.tp = StringToDouble(FileReadString(handle));
      FileReadString(handle); // exit_price from Python research
      sig.result_R = StringToDouble(FileReadString(handle));
      sig.profit = StringToDouble(FileReadString(handle));
      sig.alpha_score = StringToDouble(FileReadString(handle));
      sig.pattern_score = StringToDouble(FileReadString(handle));
      sig.final_score = StringToDouble(FileReadString(handle));
      sig.initial_risk = StringToDouble(FileReadString(handle));
      sig.patterns_detected = FileReadString(handle);
      sig.comment = FileReadString(handle);
      sig.used = false;

      if(sig.entry_time > 0 && (IsAll(sig.symbol) || Upper(sig.symbol) == Upper(TradeSymbol())))
      {
         int next = PythonSignalCount + 1;
         ArrayResize(PythonSignals, next);
         PythonSignals[PythonSignalCount] = sig;
         PythonSignalCount = next;
      }
   }
   FileClose(handle);
   Print("Loaded Python source-of-truth signals: ", PythonSignalCount, " from ", PythonSignalCsvFile);
   return true;
}

double UpperWickRatio(const MqlRates &bar)
{
   double range = bar.high - bar.low;
   if(range <= 0)
      return 0.0;
   return (bar.high - MathMax(bar.open, bar.close)) / range;
}

double LowerWickRatio(const MqlRates &bar)
{
   double range = bar.high - bar.low;
   if(range <= 0)
      return 0.0;
   return (MathMin(bar.open, bar.close) - bar.low) / range;
}

string SessionName(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   int h = dt.hour;
   if(h >= 21 && h < 22)
      return "Rollover";
   if(h >= 12 && h < 16)
      return "Overlap";
   if(h >= 7 && h < 12)
      return "London";
   if(h >= 16 && h < 20)
      return "NewYork";
   if(h >= 0 && h < 7)
      return "Asia";
   return "OffSession";
}

bool SessionAllowed(string session)
{
   if(!UseKillzone)
      return true;
   if(!StringOptionEnabled(KillzoneMode, "hard_filter"))
      return true;
   string haystack = "," + AllowedSessions + ",";
   string needle = "," + session + ",";
   return StringFind(haystack, needle) >= 0;
}

double HighestHigh(MqlRates &rates[], int from_shift, int lookback)
{
   double value = -DBL_MAX;
   int total = ArraySize(rates);
   for(int i = from_shift; i < MathMin(total, from_shift + lookback); i++)
      value = MathMax(value, rates[i].high);
   return value == -DBL_MAX ? 0.0 : value;
}

double LowestLow(MqlRates &rates[], int from_shift, int lookback)
{
   double value = DBL_MAX;
   int total = ArraySize(rates);
   for(int i = from_shift; i < MathMin(total, from_shift + lookback); i++)
      value = MathMin(value, rates[i].low);
   return value == DBL_MAX ? 0.0 : value;
}

double EfficiencyRatio(MqlRates &rates[], int shift, int period)
{
   if(ArraySize(rates) <= shift + period)
      return 0.0;
   double directional = MathAbs(rates[shift].close - rates[shift + period].close);
   double noise = 0.0;
   for(int i = shift; i < shift + period; i++)
      noise += MathAbs(rates[i].close - rates[i + 1].close);
   return SafeDiv(directional, noise);
}

double PercentileRank(double value, double &arr[], int shift, int lookback)
{
   int total = ArraySize(arr);
   int count = 0;
   int below = 0;
   for(int i = shift; i < MathMin(total, shift + lookback); i++)
   {
      if(arr[i] <= 0)
         continue;
      count++;
      if(arr[i] <= value)
         below++;
   }
   if(count <= 0)
      return 50.0;
   return 100.0 * below / count;
}

double SpreadPercentile(MqlRates &rates[], int shift, int lookback)
{
   int total = ArraySize(rates);
   int count = 0;
   int below = 0;
   long current = rates[shift].spread;
   for(int i = shift; i < MathMin(total, shift + lookback); i++)
   {
      if(rates[i].spread <= 0)
         continue;
      count++;
      if(rates[i].spread <= current)
         below++;
   }
   if(count <= 0)
      return 50.0;
   return 100.0 * below / count;
}

double SessionVWAP(MqlRates &rates[], int shift)
{
   if(ArraySize(rates) <= shift)
      return 0.0;
   string session = SessionName(rates[shift].time);
   double pv = 0.0;
   double vol = 0.0;
   for(int i = shift; i < ArraySize(rates); i++)
   {
      if(SessionName(rates[i].time) != session)
         break;
      double typical = (rates[i].high + rates[i].low + rates[i].close) / 3.0;
      double v = (double)MathMax((long)1, rates[i].tick_volume);
      pv += typical * v;
      vol += v;
   }
   return SafeDiv(pv, vol);
}

double MovingVWAP(MqlRates &rates[], int shift, int period)
{
   double pv = 0.0;
   double vol = 0.0;
   for(int i = shift; i < MathMin(ArraySize(rates), shift + period); i++)
   {
      double typical = (rates[i].high + rates[i].low + rates[i].close) / 3.0;
      double v = (double)MathMax((long)1, rates[i].tick_volume);
      pv += typical * v;
      vol += v;
   }
   return SafeDiv(pv, vol);
}

double RoundStep(string sym, bool half)
{
   string s = Upper(sym);
   if(StringFind(s, "JPY") >= 0)
      return half ? 0.50 : 1.00;
   if(StringFind(s, "XAU") >= 0 || StringFind(s, "XAG") >= 0)
      return half ? 5.0 : 10.0;
   return half ? 0.0050 : 0.0100;
}

double NearestRound(double price, double step)
{
   if(step <= 0)
      return price;
   return MathRound(price / step) * step;
}

bool HasOpenPosition(string sym)
{
   if(!OneTradeAtATime)
      return false;
   if(!PositionSelect(sym))
      return false;
   long magic = PositionGetInteger(POSITION_MAGIC);
   return magic == MagicNumber;
}

void ResetDailyCounter(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   dt.hour = 0;
   dt.min = 0;
   dt.sec = 0;
   datetime day = StructToTime(dt);
   if(CurrentDay != day)
   {
      CurrentDay = day;
      TradesToday = 0;
   }
}

bool CopyMarketState(string sym, FeatureState &f, MqlRates &rates[], double &ema20[], double &ema50[], double &atr[], double &adx[], double &plusdi[], double &minusdi[])
{
   int need = MathMax(LookbackBars, ATRPercentileLookback + 20);
   if(CopyRates(sym, TradeTF, 0, need, rates) < 80)
      return false;
   ArraySetAsSeries(rates, true);
   ArraySetAsSeries(ema20, true);
   ArraySetAsSeries(ema50, true);
   ArraySetAsSeries(atr, true);
   ArraySetAsSeries(adx, true);
   ArraySetAsSeries(plusdi, true);
   ArraySetAsSeries(minusdi, true);
   if(CopyBuffer(Ema20Handle, 0, 0, need, ema20) <= 60) return false;
   if(CopyBuffer(Ema50Handle, 0, 0, need, ema50) <= 60) return false;
   if(CopyBuffer(AtrHandle, 0, 0, need, atr) <= 60) return false;
   if(CopyBuffer(AdxHandle, 0, 0, need, adx) <= 60) return false;
   if(CopyBuffer(AdxHandle, 1, 0, need, plusdi) <= 60) return false;
   if(CopyBuffer(AdxHandle, 2, 0, need, minusdi) <= 60) return false;

   int sh = 1;
   f.bar_time = rates[sh].time;
   f.open = rates[sh].open;
   f.high = rates[sh].high;
   f.low = rates[sh].low;
   f.close = rates[sh].close;
   f.prev_close = rates[sh + 1].close;
   f.ema20 = ema20[sh];
   f.ema50 = ema50[sh];
   f.ema20_prev = ema20[sh + 5];
   f.ema50_prev = ema50[sh + 5];
   f.atr = atr[sh];
   f.adx = adx[sh];
   f.adx_prev5 = adx[sh + 5];
   f.plus_di = plusdi[sh];
   f.minus_di = minusdi[sh];
   f.er = EfficiencyRatio(rates, sh, ERPeriod);
   f.er_prev5 = EfficiencyRatio(rates, sh + 5, ERPeriod);
   f.atr_percentile = PercentileRank(f.atr, atr, sh, ATRPercentileLookback);
   f.spread_percentile = SpreadPercentile(rates, sh, 100);
   f.swing_high = HighestHigh(rates, sh + 1, SwingLookback);
   f.swing_low = LowestLow(rates, sh + 1, SwingLookback);
   f.recent_high3 = HighestHigh(rates, sh + 1, 3);
   f.recent_low3 = LowestLow(rates, sh + 1, 3);
   f.session_vwap = SessionVWAP(rates, sh);
   f.mvwap20 = MovingVWAP(rates, sh, 20);
   f.mvwap50 = MovingVWAP(rates, sh, 50);
   f.vwap_distance_atr = SafeDiv(f.close - f.session_vwap, f.atr);
   f.candle_range_atr = SafeDiv(f.high - f.low, f.atr);
   f.body_ratio = BodyRatio(rates[sh]);
   f.upper_wick_ratio = UpperWickRatio(rates[sh]);
   f.lower_wick_ratio = LowerWickRatio(rates[sh]);
   f.sweep_high = f.high > f.swing_high && f.close < f.swing_high;
   f.sweep_low = f.low < f.swing_low && f.close > f.swing_low;
   f.bos_bull = f.close > f.swing_high + f.atr * BOSATRBuffer;
   f.bos_bear = f.close < f.swing_low - f.atr * BOSATRBuffer;
   f.mss_bull = f.sweep_low && f.close > f.ema20 && f.close > f.open;
   f.mss_bear = f.sweep_high && f.close < f.ema20 && f.close < f.open;
   f.htf_bias = f.ema20 > f.ema50 ? "bullish" : f.ema20 < f.ema50 ? "bearish" : "neutral";
   f.ltf_bias = f.plus_di > f.minus_di ? "bullish" : f.minus_di > f.plus_di ? "bearish" : "neutral";
   f.session = SessionName(rates[sh].time);
   f.trend_weakening = (f.adx - f.adx_prev5) < 0.0 && (f.er - f.er_prev5) < 0.0;
   f.gap_flag = SafeDiv(MathAbs(f.open - f.prev_close), f.atr) >= 0.75;
   f.data_quality_error = f.high < f.low || f.close > f.high || f.close < f.low || f.open > f.high || f.open < f.low || f.high == f.low || f.atr <= 0.0;
   f.mtf_conflict_score = 0;
   if(f.htf_bias != f.ltf_bias) f.mtf_conflict_score++;
   if(f.adx < 18.0) f.mtf_conflict_score++;
   if(f.er < 0.25) f.mtf_conflict_score++;
   if(MathAbs(f.close - f.ema50) <= f.atr * 0.25) f.mtf_conflict_score++;
   return true;
}

void DetectRegime(FeatureState &f)
{
   if(f.data_quality_error)
   {
      f.regime = "R40";
      return;
   }
   if(f.gap_flag)
   {
      f.regime = "R39";
      return;
   }
   if(f.trend_weakening && f.htf_bias == "bullish" && f.close < f.ema20 && f.plus_di > f.minus_di)
   {
      f.regime = "R32";
      return;
   }
   if(f.trend_weakening && f.htf_bias == "bearish" && f.close > f.ema20 && f.minus_di > f.plus_di)
   {
      f.regime = "R33";
      return;
   }
   if(f.htf_bias == "bullish" && f.sweep_low && f.lower_wick_ratio >= 0.40)
   {
      f.regime = "R34";
      return;
   }
   if(f.htf_bias == "bearish" && f.sweep_high && f.upper_wick_ratio >= 0.40)
   {
      f.regime = "R35";
      return;
   }
   if(f.adx <= 18.0 && f.er <= 0.25 && f.atr_percentile >= 25.0 && f.atr_percentile <= 75.0 && MathAbs(f.vwap_distance_atr) >= VWAPReversionDistanceATR)
   {
      f.regime = "R36";
      return;
   }
   if(f.htf_bias != f.ltf_bias && f.adx >= 15.0 && f.adx <= 25.0 && f.er <= 0.30)
   {
      f.regime = "R37";
      return;
   }
   if(f.htf_bias == "bullish" && f.ltf_bias == "bullish" && f.adx >= 18.0 && f.adx <= 35.0 && f.er >= 0.25 && f.atr_percentile >= 25.0 && f.atr_percentile <= 80.0)
   {
      f.regime = "R01";
      return;
   }
   if(f.htf_bias == "bearish" && f.ltf_bias == "bearish" && f.adx >= 18.0 && f.adx <= 35.0 && f.er >= 0.25 && f.atr_percentile >= 25.0 && f.atr_percentile <= 80.0)
   {
      f.regime = "R02";
      return;
   }
   if(f.htf_bias == "bullish" && f.bos_bull && f.atr_percentile >= 75.0)
   {
      f.regime = "R04";
      return;
   }
   if(f.htf_bias == "bearish" && f.bos_bear && f.atr_percentile >= 75.0)
   {
      f.regime = "R05";
      return;
   }
   if(f.atr_percentile < 25.0)
   {
      f.regime = "R06";
      return;
   }
   f.regime = "R31";
}

bool HardFilterPass(FeatureState &f)
{
   if(!SessionAllowed(f.session))
      return false;
   if(UseSpreadFilter && StringOptionEnabled(SpreadFilterMode, "hard_filter") && f.spread_percentile > MaxSpreadPercentile)
      return false;
   if(RejectRollover && f.session == "Rollover")
      return false;
   if(RejectTrendWeakening && f.trend_weakening && (f.regime == "R01" || f.regime == "R02"))
      return false;
   if(RejectLowERCleanTrend && (f.regime == "R01" || f.regime == "R02") && f.er < MinCleanTrendER)
      return false;
   if(RejectADXOutsideCleanTrendBand && (f.regime == "R01" || f.regime == "R02") && (f.adx < 18.0 || f.adx > 35.0))
      return false;
   if(RejectMTFConflictScore && f.mtf_conflict_score > MaxMTFConflictScore)
      return false;
   return true;
}

int AlphaScore(FeatureState &f, string direction)
{
   int score = 0;
   if((direction == "long" && f.htf_bias == "bullish") || (direction == "short" && f.htf_bias == "bearish")) score += 2;
   if((direction == "long" && f.ltf_bias == "bullish") || (direction == "short" && f.ltf_bias == "bearish")) score += 2;
   if(f.adx >= 18.0 && f.adx <= 35.0) score += 2;
   if(f.er >= 0.25) score += 2;
   if(f.atr_percentile >= 25.0 && f.atr_percentile <= 80.0) score += 1;
   if(f.session == "London" || f.session == "NewYork" || f.session == "Overlap") score += 1;
   if(f.spread_percentile <= MaxSpreadPercentile) score += 1;
   if(f.trend_weakening) score -= 2;
   if(f.mtf_conflict_score > 0) score -= 1;
   return score;
}

void AddPattern(PatternState &p, string label, int score, string direction)
{
   p.score += score;
   if(StringLen(p.labels) > 0)
      p.labels += "+";
   p.labels += label;
   if(direction == "long")
      p.long_bias = true;
   if(direction == "short")
      p.short_bias = true;
}

void DetectPatterns(FeatureState &f, MqlRates &rates[], PatternState &p)
{
   p.score = 0;
   p.labels = "";
   p.long_bias = false;
   p.short_bias = false;
   if(!UsePatterns)
      return;

   int sh = 1;
   if(UseFVG && ArraySize(rates) > FVGMaxAgeBars + 5)
   {
      int max_age = MathMax(3, FVGMaxAgeBars);
      for(int i = sh + 2; i < MathMin(ArraySize(rates), sh + max_age); i++)
      {
         double bull_size = SafeDiv(rates[i].high - rates[i - 2].low, f.atr);
         double bear_size = SafeDiv(rates[i - 2].high - rates[i].low, f.atr);
         if(rates[i].high < rates[i - 2].low && bull_size >= FVGMinSizeATR && f.low <= rates[i - 2].low && f.close >= rates[i].high)
         {
            AddPattern(p, "FVG_BULL", 3, "long");
            break;
         }
         if(rates[i].low > rates[i - 2].high && bear_size >= FVGMinSizeATR && f.high >= rates[i - 2].high && f.close <= rates[i].low)
         {
            AddPattern(p, "FVG_BEAR", 3, "short");
            break;
         }
      }
   }

   if(UseBOS)
   {
      if(f.bos_bull) AddPattern(p, "BOS_BULL", 2, "long");
      if(f.bos_bear) AddPattern(p, "BOS_BEAR", 2, "short");
   }
   if(UseMSS)
   {
      if(f.mss_bull) AddPattern(p, "MSS_BULL", 3, "long");
      if(f.mss_bear) AddPattern(p, "MSS_BEAR", 3, "short");
   }
   if(UseLiquidityPools)
   {
      if(f.sweep_low) AddPattern(p, "LIQ_SWEEP_LOW", 2, "long");
      if(f.sweep_high) AddPattern(p, "LIQ_SWEEP_HIGH", 2, "short");
   }
   if(UseRoundNumbers)
   {
      string sym = TradeSymbol();
      double half = NearestRound(f.close, RoundStep(sym, true));
      double whole = NearestRound(f.close, RoundStep(sym, false));
      double tol = f.atr * RoundNumberToleranceATR;
      if(MathAbs(f.close - half) <= tol || MathAbs(f.close - whole) <= tol)
      {
         if(f.close > f.open) AddPattern(p, "ROUND_RECLAIM", 1, "long");
         if(f.close < f.open) AddPattern(p, "ROUND_REJECT", 1, "short");
      }
   }
   if(UseVWAP)
   {
      if(f.vwap_distance_atr <= -VWAPReversionDistanceATR && f.lower_wick_ratio >= 0.30) AddPattern(p, "VWAP_LOW", 2, "long");
      if(f.vwap_distance_atr >= VWAPReversionDistanceATR && f.upper_wick_ratio >= 0.30) AddPattern(p, "VWAP_HIGH", 2, "short");
   }
   if(UseSessionVWAP)
   {
      if(f.low <= f.session_vwap && f.close > f.session_vwap) AddPattern(p, "SVWAP_RECLAIM", 2, "long");
      if(f.high >= f.session_vwap && f.close < f.session_vwap) AddPattern(p, "SVWAP_REJECT", 2, "short");
   }
   if(UseMVWAP)
   {
      if(f.mvwap20 > f.mvwap50 && f.close > f.mvwap20) AddPattern(p, "MVWAP_BULL", 1, "long");
      if(f.mvwap20 < f.mvwap50 && f.close < f.mvwap20) AddPattern(p, "MVWAP_BEAR", 1, "short");
   }
   if(UseOrderBlocks)
   {
      for(int i = 2; i < MathMin(ArraySize(rates), OBMaxAgeBars); i++)
      {
         double range_atr = SafeDiv(rates[i - 1].high - rates[i - 1].low, f.atr);
         double body = BodyRatio(rates[i - 1]);
         bool bull_disp = rates[i - 1].close > rates[i - 1].open && body >= OBDisplacementBodyRatioMin && range_atr >= OBDisplacementCandleRangeATRMin;
         bool bear_disp = rates[i - 1].close < rates[i - 1].open && body >= OBDisplacementBodyRatioMin && range_atr >= OBDisplacementCandleRangeATRMin;
         if(bull_disp && rates[i].close < rates[i].open && f.low <= rates[i].high && f.high >= rates[i].low)
         {
            AddPattern(p, "OB_BULL", 3, "long");
            break;
         }
         if(bear_disp && rates[i].close > rates[i].open && f.low <= rates[i].high && f.high >= rates[i].low)
         {
            AddPattern(p, "OB_BEAR", 3, "short");
            break;
         }
      }
   }
}

bool PatternPass(PatternState &p, string direction)
{
   if(!UsePatterns)
      return true;
   if(PatternScoreMode == "score_only")
      return true;
   if(p.score < MinPatternScore)
      return false;
   if(direction == "long" && p.short_bias && !p.long_bias)
      return false;
   if(direction == "short" && p.long_bias && !p.short_bias)
      return false;
   return true;
}

string DefaultStrategyForRegime(string regime, string direction)
{
   if(regime == "R01") return direction == "long" ? "T1" : "";
   if(regime == "R02") return direction == "short" ? "T4" : "";
   if(regime == "R04") return direction == "long" ? "B1" : "";
   if(regime == "R05") return direction == "short" ? "B4" : "";
   if(regime == "R06") return direction == "long" ? "C1" : "C2";
   if(regime == "R31") return "TR1";
   if(regime == "R32") return direction == "long" ? "TW1" : "TW2";
   if(regime == "R33") return direction == "short" ? "TW3" : "TW4";
   if(regime == "R34") return direction == "long" ? "LS1" : "";
   if(regime == "R35") return direction == "short" ? "LS4" : "";
   if(regime == "R36") return direction == "long" ? "VW2" : "VW1";
   if(regime == "R37") return "MT1";
   if(regime == "R39") return "G1";
   return "";
}

string DirectionForStrategy(string strategy, FeatureState &f, PatternState &p)
{
   string s = Upper(strategy);
   if(s == "D0" || s == "D1" || s == "DQ1" || s == "TR2" || s == "DL1" || s == "MF1" || s == "AR5")
      return "none";
   if(s == "T1" || s == "T2" || s == "T3" || s == "R2" || s == "S2" || s == "B1" || s == "B2" || s == "B3" ||
      s == "C1" || s == "C4" || s == "E3" || s == "E4" || s == "L1" || s == "L2" || s == "L3" ||
      s == "CH1" || s == "CH2" || s == "CH3" || s == "RL1" || s == "RL2" || s == "RL3" ||
      s == "FB4" || s == "FB5" || s == "FB6" || s == "AR2" || s == "AR4" || s == "RO1" || s == "RO2" || s == "RO3" ||
      s == "TW1" || s == "TW4" || s == "LS1" || s == "LS2" || s == "LS3" || s == "VW2")
      return "long";
   if(s == "T4" || s == "T5" || s == "T6" || s == "R1" || s == "S1" || s == "B4" || s == "B5" || s == "B6" ||
      s == "C2" || s == "C3" || s == "E1" || s == "E2" || s == "L4" || s == "L5" || s == "L6" ||
      s == "CH4" || s == "CH5" || s == "CH6" || s == "RH1" || s == "RH2" || s == "RH3" ||
      s == "FB1" || s == "FB2" || s == "FB3" || s == "AR1" || s == "AR3" || s == "RF1" || s == "RF2" ||
      s == "TW2" || s == "TW3" || s == "LS4" || s == "LS5" || s == "LS6" || s == "VW1")
      return "short";
   if(p.long_bias && !p.short_bias) return "long";
   if(p.short_bias && !p.long_bias) return "short";
   if(f.htf_bias == "bullish") return "long";
   if(f.htf_bias == "bearish") return "short";
   return f.close >= f.open ? "long" : "short";
}

bool EvaluateStrategy(string strategy, string direction, FeatureState &f, PatternState &p, double &sl, double &tp, string &reason)
{
   if(direction == "none")
      return false;
   double entry = direction == "long" ? SymbolInfoDouble(TradeSymbol(), SYMBOL_ASK) : SymbolInfoDouble(TradeSymbol(), SYMBOL_BID);
   if(entry <= 0)
      entry = f.close;
   bool ok = false;
   string s = Upper(strategy);

   if(s == "T1" || s == "L1" || s == "CH2" || s == "TW1")
      ok = direction == "long" && f.low <= f.ema20 + f.atr * 0.35 && f.close > f.ema20 && f.close > f.open;
   else if(s == "T2")
      ok = direction == "long" && f.low <= f.ema50 + f.atr * 0.35 && f.close > f.ema50 && f.close > f.open;
   else if(s == "T3" || s == "B1" || s == "B2" || s == "B3" || s == "C1" || s == "CH3" || s == "LS3")
      ok = direction == "long" && (f.bos_bull || f.close > f.recent_high3);
   else if(s == "T4" || s == "L4" || s == "CH5" || s == "TW3")
      ok = direction == "short" && f.high >= f.ema20 - f.atr * 0.35 && f.close < f.ema20 && f.close < f.open;
   else if(s == "T5")
      ok = direction == "short" && f.high >= f.ema50 - f.atr * 0.35 && f.close < f.ema50 && f.close < f.open;
   else if(s == "T6" || s == "B4" || s == "B5" || s == "B6" || s == "C2" || s == "CH6" || s == "LS6")
      ok = direction == "short" && (f.bos_bear || f.close < f.recent_low3);
   else if(s == "R1" || s == "S1" || s == "RH1" || s == "RH2" || s == "RH3" || s == "FB1" || s == "FB2" || s == "FB3" || s == "AR1" || s == "AR3" || s == "E1" || s == "E2")
      ok = direction == "short" && (f.sweep_high || f.upper_wick_ratio >= 0.35);
   else if(s == "R2" || s == "S2" || s == "RL1" || s == "RL2" || s == "RL3" || s == "FB4" || s == "FB5" || s == "FB6" || s == "AR2" || s == "AR4" || s == "E3" || s == "E4")
      ok = direction == "long" && (f.sweep_low || f.lower_wick_ratio >= 0.35);
   else if(s == "LS1" || s == "LS2")
      ok = direction == "long" && f.sweep_low && f.close > f.swing_low;
   else if(s == "LS4" || s == "LS5")
      ok = direction == "short" && f.sweep_high && f.close < f.swing_high;
   else if(s == "VW1")
      ok = direction == "short" && f.vwap_distance_atr >= VWAPReversionDistanceATR && f.upper_wick_ratio >= 0.30;
   else if(s == "VW2")
      ok = direction == "long" && f.vwap_distance_atr <= -VWAPReversionDistanceATR && f.lower_wick_ratio >= 0.30;
   else if(s == "VW3")
      ok = MathAbs(f.vwap_distance_atr) >= VWAPReversionDistanceATR && ((direction == "long" && f.close > f.open) || (direction == "short" && f.close < f.open));
   else if(s == "TR1")
      ok = f.close > f.recent_high3 || f.close < f.recent_low3;
   else if(s == "MT1" || s == "MT2")
      ok = f.mtf_conflict_score > 0 && (f.sweep_low || f.sweep_high || f.bos_bull || f.bos_bear);
   else if(s == "G1" || s == "G2")
      ok = f.gap_flag && ((direction == "long" && f.close > f.open) || (direction == "short" && f.close < f.open));
   else
      ok = ((direction == "long" && f.close > f.ema20 && f.close > f.open) || (direction == "short" && f.close < f.ema20 && f.close < f.open));

   if(!ok)
      return false;

   double buffer = f.atr * 0.35;
   if(direction == "long")
   {
      sl = MathMin(f.low, MathMin(f.ema20, f.swing_low)) - buffer;
      tp = entry + (entry - sl) * RR;
   }
   else
   {
      sl = MathMax(f.high, MathMax(f.ema20, f.swing_high)) + buffer;
      tp = entry - (sl - entry) * RR;
   }
   reason = f.regime + "|" + strategy + "|" + p.labels;
   return true;
}

double NormalizeVolume(double volume)
{
   string sym = TradeSymbol();
   double min_vol = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double max_vol = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   if(step <= 0)
      step = 0.01;
   volume = MathMax(min_vol, MathMin(max_vol, volume));
   return MathFloor(volume / step) * step;
}

double RiskVolume(double entry, double sl)
{
   string sym = TradeSymbol();
   double tick_size = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   double tick_value = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   if(tick_size <= 0 || tick_value <= 0)
      return SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double risk_money = AccountInfoDouble(ACCOUNT_BALANCE) * RiskPercent / 100.0;
   double loss_per_lot = MathAbs(entry - sl) / tick_size * tick_value;
   if(loss_per_lot <= 0)
      return SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   return NormalizeVolume(risk_money / loss_per_lot);
}

void WriteSignal(FeatureState &f, string strategy, string direction, PatternState &p, double entry, double sl, double tp, int alpha)
{
   if(SignalLogHandle == INVALID_HANDLE)
      return;
   double initial_risk = AccountInfoDouble(ACCOUNT_BALANCE) * RiskPercent / 100.0;
   double final_score = alpha + p.score;
   FileWrite(SignalLogHandle, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES), TradeSymbol(), f.regime, strategy, direction, alpha, p.score, final_score, p.labels, entry, sl, tp, 0.0, 0.0, initial_risk, f.session, f.adx, f.er, f.atr_percentile, f.spread_percentile, f.vwap_distance_atr, "EA_SIGNAL");
   FileFlush(SignalLogHandle);
}

void WritePythonSignalExecution(PythonSignal &sig, double actual_entry)
{
   if(SignalLogHandle == INVALID_HANDLE)
      return;
   FileWrite(
      SignalLogHandle,
      TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES),
      TradeSymbol(),
      sig.regime_id,
      sig.strategy_id,
      sig.direction,
      sig.alpha_score,
      sig.pattern_score,
      sig.final_score,
      sig.patterns_detected,
      actual_entry,
      sig.sl,
      sig.tp,
      sig.result_R,
      sig.profit,
      sig.initial_risk,
      "PythonSignalCsv",
      0,
      0,
      0,
      0,
      0,
      sig.comment
   );
   FileFlush(SignalLogHandle);
}

bool SignalDue(PythonSignal &sig, datetime bar_time)
{
   int delta = (int)MathAbs((long)(bar_time - sig.entry_time));
   return delta <= PythonSignalTimeToleranceSeconds;
}

void TryOpenPythonSignal(FeatureState &f)
{
   string sym = TradeSymbol();
   if(HasOpenPosition(sym))
      return;
   for(int i = 0; i < PythonSignalCount; i++)
   {
      if(PythonSignals[i].used)
         continue;
      if(!SignalDue(PythonSignals[i], f.bar_time))
         continue;
      if(!IsAll(RegimeFilter) && PythonSignals[i].regime_id != RegimeFilter)
         continue;
      if(!IsAll(StrategyFilter) && PythonSignals[i].strategy_id != StrategyFilter)
         continue;
      if(Upper(PythonSignals[i].timeframe) != Upper(Timeframe))
         continue;

      string direction = Lower(PythonSignals[i].direction);
      if(direction != "long" && direction != "short")
      {
         PythonSignals[i].used = true;
         continue;
      }
      double entry = direction == "long" ? SymbolInfoDouble(sym, SYMBOL_ASK) : SymbolInfoDouble(sym, SYMBOL_BID);
      if(entry <= 0)
         entry = f.close;
      double sl = PythonSignals[i].sl;
      double tp = PythonSignals[i].tp;
      if(sl <= 0 || tp <= 0 || MathAbs(entry - sl) <= 0)
      {
         Print("Python signal skipped because SL/TP is invalid: ", PythonSignals[i].comment);
         PythonSignals[i].used = true;
         continue;
      }
      double volume = RiskVolume(entry, sl);
      if(volume <= 0)
         return;
      string comment = PythonSignals[i].comment;
      if(StringLen(comment) == 0)
         comment = PythonSignals[i].regime_id + "|" + PythonSignals[i].strategy_id + "|PYIDX:" + IntegerToString(PythonSignals[i].parity_index) + "|PYHASH:" + PythonSignals[i].parity_hash;

      bool sent = false;
      if(direction == "long")
         sent = Trade.Buy(volume, sym, 0.0, sl, tp, comment);
      else
         sent = Trade.Sell(volume, sym, 0.0, sl, tp, comment);
      if(sent)
      {
         TradesToday++;
         PythonSignals[i].used = true;
         WritePythonSignalExecution(PythonSignals[i], entry);
      }
      else
      {
         Print("Python signal order failed: ", comment, " retcode=", Trade.ResultRetcode(), " ", Trade.ResultRetcodeDescription());
      }
      return;
   }
}

void TryOpenTrade(FeatureState &f, PatternState &p)
{
   string sym = TradeSymbol();
   if(HasOpenPosition(sym) || TradesToday >= MaxTradesPerDay)
      return;
   if(!IsAll(RegimeFilter) && f.regime != RegimeFilter)
      return;
   if(f.regime == "R10" || f.regime == "R30" || f.regime == "R40")
      return;
   if(!HardFilterPass(f))
      return;

   string strategy = StrategyFilter;
   string direction = "";
   if(IsAll(strategy))
   {
      if(p.long_bias && !p.short_bias) direction = "long";
      else if(p.short_bias && !p.long_bias) direction = "short";
      else direction = (f.htf_bias == "bearish" || f.regime == "R02" || f.regime == "R05" || f.regime == "R35") ? "short" : "long";
      strategy = DefaultStrategyForRegime(f.regime, direction);
      if(StringLen(strategy) == 0)
         return;
   }
   else
   {
      direction = DirectionForStrategy(strategy, f, p);
   }
   if(direction == "none")
      return;
   if(!PatternPass(p, direction))
      return;
   int alpha = AlphaScore(f, direction);
   if(UseAlpha && AlphaMode == "hard_minimum" && alpha < MinAlphaScore)
      return;

   double sl = 0.0;
   double tp = 0.0;
   string reason = "";
   if(!EvaluateStrategy(strategy, direction, f, p, sl, tp, reason))
      return;

   double entry = direction == "long" ? SymbolInfoDouble(sym, SYMBOL_ASK) : SymbolInfoDouble(sym, SYMBOL_BID);
   double volume = RiskVolume(entry, sl);
   if(volume <= 0)
      return;

   string comment = f.regime + "|" + strategy + "|A" + IntegerToString(alpha) + "|P" + IntegerToString(p.score);
   bool sent = false;
   if(direction == "long")
      sent = Trade.Buy(volume, sym, 0.0, sl, tp, comment);
   else
      sent = Trade.Sell(volume, sym, 0.0, sl, tp, comment);
   if(sent)
   {
      TradesToday++;
      WriteSignal(f, strategy, direction, p, entry, sl, tp, alpha);
   }
}

int OnInit()
{
   if(!TesterSafetyAllowed())
      return INIT_FAILED;
   string sym = TradeSymbol();
   TradeTF = ParseTimeframe(Timeframe);
   Trade.SetExpertMagicNumber(MagicNumber);
   Ema20Handle = iMA(sym, TradeTF, 20, 0, MODE_EMA, PRICE_CLOSE);
   Ema50Handle = iMA(sym, TradeTF, 50, 0, MODE_EMA, PRICE_CLOSE);
   AtrHandle = iATR(sym, TradeTF, 14);
   AdxHandle = iADX(sym, TradeTF, 14);
   if(Ema20Handle == INVALID_HANDLE || Ema50Handle == INVALID_HANDLE || AtrHandle == INVALID_HANDLE || AdxHandle == INVALID_HANDLE)
      return INIT_FAILED;
   if(WriteSignalCsv)
   {
      SignalLogHandle = FileOpen("QuantForexV10_ResearchEA_signals.csv", FILE_WRITE | FILE_CSV | FILE_COMMON);
      if(SignalLogHandle != INVALID_HANDLE)
         FileWrite(SignalLogHandle, "time", "symbol", "regime", "strategy", "direction", "alpha_score", "pattern_score", "final_score", "patterns", "entry", "sl", "tp", "result_R", "profit", "initial_risk", "session", "adx", "er", "atr_percentile", "spread_percentile", "vwap_distance_atr", "setup_reason");
   }
   if(!LoadPythonSignals())
      return INIT_FAILED;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(Ema20Handle != INVALID_HANDLE) IndicatorRelease(Ema20Handle);
   if(Ema50Handle != INVALID_HANDLE) IndicatorRelease(Ema50Handle);
   if(AtrHandle != INVALID_HANDLE) IndicatorRelease(AtrHandle);
   if(AdxHandle != INVALID_HANDLE) IndicatorRelease(AdxHandle);
   if(SignalLogHandle != INVALID_HANDLE) FileClose(SignalLogHandle);
}

void OnTick()
{
   if(!TesterSafetyAllowed())
      return;
   string sym = TradeSymbol();
   datetime bar_time = iTime(sym, TradeTF, 0);
   if(bar_time == 0 || bar_time == LastBarTime)
      return;
   LastBarTime = bar_time;

   MqlRates rates[];
   double ema20[];
   double ema50[];
   double atr[];
   double adx[];
   double plusdi[];
   double minusdi[];
   FeatureState f;
   if(!CopyMarketState(sym, f, rates, ema20, ema50, atr, adx, plusdi, minusdi))
      return;
   if(!InDateRange(rates[1].time))
      return;
   ResetDailyCounter(rates[1].time);
   if(UsePythonSignalCsv)
   {
      TryOpenPythonSignal(f);
      return;
   }
   DetectRegime(f);
   PatternState p;
   DetectPatterns(f, rates, p);
   TryOpenTrade(f, p);
}
