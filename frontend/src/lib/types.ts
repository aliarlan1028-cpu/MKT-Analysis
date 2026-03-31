// Types matching backend Pydantic schemas

export interface MarketData {
  symbol: string;
  name: string;
  price: number;
  price_change_24h: number;
  price_change_pct_24h: number;
  high_24h: number;
  low_24h: number;
  volume_24h: number;
  market_cap: number | null;
  funding_rate: number | null;
  long_short_ratio: number | null;
  open_interest: number | null;
  open_interest_change_pct: number | null;
  timestamp: string;
}

export interface FearGreedIndex {
  value: number;
  label: string;
  timestamp: string;
}

export interface DashboardResponse {
  markets: MarketData[];
  fear_greed: FearGreedIndex;
  last_updated: string;
}

export interface TradingSignal {
  direction: "LONG" | "SHORT" | "NEUTRAL";
  confidence: number;
  entry_zone: number[];
  stop_loss: number;
  take_profit: number[];
  leverage_suggestion: string;
  risk_reward_ratio: number | null;
}

export interface AnalysisSection {
  title: string;
  content: string;
  bullets: string[];
}

export interface CalendarEvent {
  date: string;
  time: string;
  title: string;
  impact: "HIGH" | "MEDIUM" | "LOW";
  category: string;
  previous: string | null;
  forecast: string | null;
  description: string | null;
  impact_if_met: string | null;
  impact_if_missed: string | null;
}

export interface AnalysisReport {
  id: string;
  symbol: string;
  name: string;
  session: string;
  timestamp: string;
  price_at_analysis: number;
  signal: TradingSignal;
  technical: AnalysisSection;
  fundamental: AnalysisSection;
  sentiment: AnalysisSection;
  macro: AnalysisSection;
  risk_warning: AnalysisSection;
  calendar_events: CalendarEvent[];
}

export interface ReportListItem {
  id: string;
  symbol: string;
  name: string;
  session: string;
  timestamp: string;
  direction: string;
  confidence: number;
  price_at_analysis: number;
}

// ── Post-Mortem ──
export interface PostMortem {
  report_id: string;
  symbol: string;
  name: string;
  direction: string;
  confidence: number;
  price_at_analysis: number;
  price_at_expiry: number;
  price_high: number;
  price_low: number;
  entry_zone: number[];
  stop_loss: number;
  take_profit: number[];
  hit_tp: number;
  hit_sl: boolean;
  pnl_pct: number;
  result: string;
  analysis_time: string;
  expiry_time: string;
  evaluated_at: string;
  summary: string;
}

export interface WinRateStats {
  total_signals: number;
  wins: number;
  losses: number;
  breakeven: number;
  win_rate: number;
  total_pnl_pct: number;
}

// ── Price Spike ──
export interface PriceSpikeAnalysis {
  primary_cause: string;
  category: string;
  details: string;
  confidence: string;
  sources: string[];
}

export interface PriceSpikeAlert {
  price_before: number;
  price_after: number;
  change_pct: number;
  direction: string;
  window_seconds: number;
  detected_at: string;
  analysis: PriceSpikeAnalysis;
}

// ── Whale Alert ──
export interface WhaleTransaction {
  hash: string;
  blockchain: string;
  symbol: string;
  amount: number;
  amount_usd: number;
  from_address: string;
  from_owner: string;
  to_address: string;
  to_owner: string;
  tx_type: string;
  timestamp: string;
}

export interface WhaleAlertResponse {
  transactions: WhaleTransaction[];
  summary: {
    total_inflow_usd: number;
    total_outflow_usd: number;
    net_flow: number;
    total_transactions: number;
    signal: string;
  };
}

// ── Liquidation ──
export interface LiquidationLevel {
  price: number;
  long_liq_usd: number;
  short_liq_usd: number;
  leverage: string;
}

export interface LiquidationMap {
  symbol: string;
  current_price: number;
  levels: LiquidationLevel[];
  total_long_liq: number;
  total_short_liq: number;
  timestamp: string;
}

// ── Correlation ──
export interface CorrelationPair {
  asset_a: string;
  asset_b: string;
  correlation_7d: number;
  correlation_30d: number;
}

export interface CorrelationMatrix {
  assets: string[];
  matrix_7d: number[][];
  matrix_30d: number[][];
  pairs: CorrelationPair[];
  timestamp: string;
}

// ── Multi-Timeframe Analysis ──
export interface TimeframeSignal {
  timeframe: string;
  direction: string;
  strength: number;
  rsi: number | null;
  macd_hist: number | null;
  ema_trend: string;
  bb_position: string;
}

export interface MultiTimeframe {
  symbol: string;
  name: string;
  price: number;
  timeframes: TimeframeSignal[];
  consensus: string;
  timestamp: string;
}

// ── Pump & Dump Scanner ──
export interface PumpCandidate {
  coin: string;
  inst_id: string;
  price: number;
  change_pct_24h: number;
  volume_24h: number;
  open_interest: number;
  funding_rate: number | null;
  rsi: number | null;
  bb_width: number | null;
  volume_ratio: number | null;
  cumulative_return_7d: number;
  ema_deviation_pct: number;
  consecutive_up_days: number;
  score: number;
}

export interface PumpScannerResult {
  pre_pump: PumpCandidate[];
  dump_risk: PumpCandidate[];
  total_scanned: number;
  timestamp: string;
}

// ── Professional Dashboard ──
export interface ProfessionalDashboard {
  price_spikes: PriceSpikeAlert[];
  whale_alerts: WhaleAlertResponse;
  correlation: CorrelationMatrix | null;
  liquidation: LiquidationMap[];
  pump_scanner: PumpScannerResult | null;
  postmortems: PostMortem[];
  win_rate: WinRateStats;
  timestamp: string;
}

