//+------------------------------------------------------------------+
//| ForexRegime.mq5                                                  |
//| Matches forex_regime Python: EMA span, SMA(TR) ATR, same rules |
//+------------------------------------------------------------------+
#property copyright "forex_regime"
#property link      ""
#property version   "1.00"
#property indicator_separate_window
#property indicator_plots   1
#property indicator_buffers 2
#property indicator_type1   DRAW_COLOR_HISTOGRAM
#property indicator_color1  clrGray, clrDodgerBlue, clrTomato
#property indicator_width1  3
#property indicator_label1  "Regime (+1 up, 0 range, -1 down)"

input int    InpEmaFast       = 12;      // EMA fast span (matches pandas)
input int    InpEmaSlow       = 26;      // EMA slow span
input int    InpAtrPeriod     = 14;      // ATR = SMA(true range, period)
input double InpTrendAtrMult  = 0.35;    // |EMAfast-EMAslow|/ATR > this => trend
input double InpRangeAtrMult  = 0.15;    // below this * ATR (normalized) => range

double RegimeBuffer[];
double ColorBuffer[];

int OnInit()
  {
   SetIndexBuffer(0, RegimeBuffer, INDICATOR_DATA);
   SetIndexBuffer(1, ColorBuffer, INDICATOR_COLOR_INDEX);
   PlotIndexSetInteger(0, PLOT_DRAW_BEGIN, MathMax(InpEmaSlow, InpAtrPeriod) + 2);
   IndicatorSetString(INDICATOR_SHORTNAME,
                       StringFormat("ForexRegime(%d,%d,%d)", InpEmaFast, InpEmaSlow, InpAtrPeriod));
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
  }

// Pandas-style EMA: alpha = 2/(span+1), first value = first close
void BuildEma(const double &close[], const int total, const int span, double &ema[])
  {
   ArrayResize(ema, total);
   ArraySetAsSeries(ema, true);
   if(total <= 0)
      return;
   double alpha = 2.0 / (span + 1.0);
   int oldest = total - 1;
   for(int i = oldest; i >= 0; i--)
     {
      if(i == oldest)
         ema[i] = close[i];
      else
         ema[i] = alpha * close[i] + (1.0 - alpha) * ema[i + 1];
     }
  }

// True range; prev close is bar i+1 in time (older index in series array)
void BuildTr(const double &high[], const double &low[], const double &close[], const int total, double &tr[])
  {
   ArrayResize(tr, total);
   ArraySetAsSeries(tr, true);
   int oldest = total - 1;
   for(int i = oldest; i >= 0; i--)
     {
      double pc = (i < oldest) ? close[i + 1] : close[i];
      double a = high[i] - low[i];
      double b = MathAbs(high[i] - pc);
      double c = MathAbs(low[i] - pc);
      tr[i] = MathMax(a, MathMax(b, c));
     }
  }

// SMA of TR (matches pandas rolling mean), no Wilder smoothing
void BuildAtrSma(const double &tr[], const int total, const int period, double &atr[])
  {
   ArrayResize(atr, total);
   ArraySetAsSeries(atr, true);
   int oldest = total - 1;
   for(int i = oldest; i >= 0; i--)
     {
      // sum tr from i .. i+period-1 along time (i = newer? series: i is index, i+d is older)
      double sum = 0.0;
      int cnt = 0;
      for(int k = 0; k < period; k++)
        {
         int j = i + k;
         if(j > oldest)
            break;
         sum += tr[j];
         cnt++;
        }
      if(cnt < period || cnt == 0)
         atr[i] = 0.0;
      else
         atr[i] = sum / period;
     }
  }

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   if(rates_total < MathMax(InpEmaSlow, InpAtrPeriod) + 2)
      return(0);

   ArraySetAsSeries(RegimeBuffer, true);
   ArraySetAsSeries(ColorBuffer, true);

   static double emaFast[], emaSlow[], tr[], atr[];
   BuildEma(close, rates_total, InpEmaFast, emaFast);
   BuildEma(close, rates_total, InpEmaSlow, emaSlow);
   BuildTr(high, low, close, rates_total, tr);
   BuildAtrSma(tr, rates_total, InpAtrPeriod, atr);

   for(int i = 0; i < rates_total; i++)
     {
      double a = atr[i];
      double spr = emaFast[i] - emaSlow[i];
      double reg = 0.0;
      int colorIdx = 0;

      if(a <= 0.0)
        {
         RegimeBuffer[i] = 0.0;
         ColorBuffer[i] = 0;
         continue;
        }

      double n = spr / a;
      // Python: TREND_UP if n > trend; TREND_DOWN if n < -trend; then force RANGE if fabs(n) < range
      if(MathAbs(n) < InpRangeAtrMult)
        {
         reg = 0.0;
         colorIdx = 0;
        }
      else if(n > InpTrendAtrMult)
        {
         reg = 1.0;
         colorIdx = 1;
        }
      else if(n < -InpTrendAtrMult)
        {
         reg = -1.0;
         colorIdx = 2;
        }
      else
        {
         reg = 0.0;
         colorIdx = 0;
        }

      RegimeBuffer[i] = reg;
      ColorBuffer[i] = colorIdx;
     }

   string last = "RANGE";
   if(RegimeBuffer[0] > 0.5)
      last = "TREND_UP";
   else if(RegimeBuffer[0] < -0.5)
      last = "TREND_DOWN";

   double ncur = (atr[0] > 0.0) ? (emaFast[0] - emaSlow[0]) / atr[0] : 0.0;
   Comment("ForexRegime [", _Symbol, " ", EnumToString(Period()), "]  current: ", last,
           "  n=", DoubleToString(ncur, 4));

   return(rates_total);
  }
//+------------------------------------------------------------------+
