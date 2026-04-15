"""Pydantic schemas for API responses."""

from pydantic import BaseModel
from datetime import datetime


# ── Market Data ──
class MarketData(BaseModel):
    symbol: str
    name: str
    price: float
    price_change_24h: float
    price_change_pct_24h: float
    high_24h: float
    low_24h: float
    volume_24h: float
    market_cap: float | None = None
    funding_rate: float | None = None
    long_short_ratio: float | None = None
    open_interest: float | None = None
    open_interest_change_pct: float | None = None
    timestamp: datetime


# ── Technical Indicators ──
class TechnicalIndicators(BaseModel):
    symbol: str
    timeframe: str  # "1h", "4h", "1d"
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    ema_21: float | None = None
    ema_55: float | None = None
    ema_200: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    atr: float | None = None
    volume_sma_20: float | None = None
    # New indicators
    stoch_rsi_k: float | None = None
    stoch_rsi_d: float | None = None
    adx: float | None = None
    obv: float | None = None          # On-Balance Volume (raw)
    obv_slope: float | None = None    # OBV trend (positive=accumulation)
    vwap: float | None = None


# ── Fear & Greed ──
class FearGreedIndex(BaseModel):
    value: int
    label: str  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    timestamp: datetime


# ── Trading Signal ──
class TradingSignal(BaseModel):
    direction: str  # "LONG", "SHORT", "NEUTRAL"
    confidence: int  # 0-100
    entry_zone: list[float]
    stop_loss: float
    take_profit: list[float]
    leverage_suggestion: str
    risk_reward_ratio: float | None = None


# ── Calendar Event ──
class CalendarEvent(BaseModel):
    date: str
    time: str  # "20:30" or "TBD"
    title: str
    impact: str  # "HIGH", "MEDIUM", "LOW"
    category: str  # "economic", "fed", "crypto"
    previous: str | None = None
    forecast: str | None = None
    description: str | None = None
    impact_if_met: str | None = None      # 达预期: 对行情的影响分析
    impact_if_missed: str | None = None   # 未达预期: 对行情的影响分析


# ── Full Analysis Report ──
class AnalysisSection(BaseModel):
    title: str
    content: str
    bullets: list[str] = []
    key_support: list[float] = []
    key_resistance: list[float] = []


class NewsItem(BaseModel):
    event: str
    detail: str = ""
    impact: str = "MEDIUM"  # HIGH, MEDIUM, LOW
    source: str = ""

class News7d(BaseModel):
    bullish: list[NewsItem] = []
    bearish: list[NewsItem] = []
    summary: str = ""

class AnalysisReport(BaseModel):
    id: str | None = None
    symbol: str
    name: str
    session: str  # "morning", "evening"
    timestamp: datetime
    price_at_analysis: float
    ai_provider: str = "gemini"
    signal: TradingSignal
    technical: AnalysisSection
    fundamental: AnalysisSection
    sentiment: AnalysisSection
    macro: AnalysisSection
    risk_warning: AnalysisSection
    news_7d: News7d | None = None
    calendar_events: list[CalendarEvent] = []
    raw_market_data: MarketData | None = None
    raw_indicators: TechnicalIndicators | None = None


# ── Dashboard Response ──
class DashboardResponse(BaseModel):
    markets: list[MarketData]
    fear_greed: FearGreedIndex
    last_updated: datetime


# ── Reports List ──
class ReportListItem(BaseModel):
    id: str
    symbol: str
    name: str
    session: str
    timestamp: datetime
    direction: str
    confidence: int
    price_at_analysis: float


# ── Post-Mortem (Signal Evaluation) ──
class PostMortem(BaseModel):
    report_id: str
    symbol: str
    name: str
    direction: str
    confidence: int
    price_at_analysis: float
    price_at_expiry: float
    price_high: float  # highest price during signal validity
    price_low: float   # lowest price during signal validity
    entry_zone: list[float]
    stop_loss: float
    take_profit: list[float]
    hit_tp: int  # which TP was hit (0=none, 1=TP1, 2=TP2)
    hit_sl: bool
    pnl_pct: float  # estimated PnL %
    result: str  # "WIN", "LOSS", "BREAKEVEN", "PENDING"
    analysis_time: datetime
    expiry_time: datetime
    evaluated_at: datetime
    summary: str  # AI-generated summary


# ── Price Spike Alert ──
class PriceSpikeAnalysis(BaseModel):
    primary_cause: str
    category: str  # "news|whale|liquidation|macro|fed|technical|other"
    details: str
    confidence: str  # "high|medium|low"
    sources: list[str] = []


class PriceSpikeAlert(BaseModel):
    price_before: float
    price_after: float
    change_pct: float
    direction: str  # "pump" or "dump"
    window_seconds: int
    detected_at: str
    analysis: PriceSpikeAnalysis


# ── Whale Alert ──
class WhaleTransaction(BaseModel):
    hash: str
    blockchain: str
    symbol: str
    amount: float
    amount_usd: float
    from_address: str
    from_owner: str  # "Binance", "unknown", etc.
    to_address: str
    to_owner: str
    tx_type: str  # "exchange_inflow", "exchange_outflow", "transfer"
    timestamp: datetime


class WhaleAlertResponse(BaseModel):
    transactions: list[WhaleTransaction]
    summary: dict  # {"total_inflow_usd": x, "total_outflow_usd": y, "net_flow": z}


# ── Liquidation Heatmap ──
class LiquidationLevel(BaseModel):
    price: float
    long_liq_usd: float  # estimated long liquidations at this price
    short_liq_usd: float  # estimated short liquidations at this price
    leverage: str  # "5x", "10x", "25x", "50x", "100x"


class LiquidationMap(BaseModel):
    symbol: str
    current_price: float
    levels: list[LiquidationLevel]
    total_long_liq: float
    total_short_liq: float
    timestamp: datetime


# ── Correlation Matrix ──
class CorrelationPair(BaseModel):
    asset_a: str
    asset_b: str
    correlation_7d: float
    correlation_30d: float


class CorrelationMatrix(BaseModel):
    assets: list[str]
    matrix_7d: list[list[float]]  # NxN matrix
    matrix_30d: list[list[float]]
    pairs: list[CorrelationPair]  # notable pairs
    timestamp: datetime


# ── Multi-Timeframe Analysis ──
class TimeframeSignal(BaseModel):
    timeframe: str  # "1h", "4h", "1d"
    direction: str  # "LONG", "SHORT", "NEUTRAL"
    strength: int  # 0-100
    rsi: float | None = None
    macd_hist: float | None = None
    ema_trend: str  # "bullish", "bearish", "neutral"
    bb_position: str  # "above_upper", "below_lower", "middle"


class MultiTimeframe(BaseModel):
    symbol: str
    name: str
    price: float
    timeframes: list[TimeframeSignal]
    consensus: str  # "STRONG_LONG", "LONG", "NEUTRAL", "SHORT", "STRONG_SHORT"
    timestamp: datetime

