"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import dynamic from "next/dynamic";

const SimChart = dynamic(() => import("@/components/sim/SimChart"), { ssr: false });

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Account {
  balance: number; used_margin: number; available_balance: number;
  total_pnl: number; total_trades: number; wins: number; losses: number;
  win_rate: number; can_refund: boolean;
}

interface Factor { description: string; bias: string }

interface Position {
  id: number; coin: string; direction: string; status: string;
  leverage: number; margin: number; entry_price: number | null;
  target_entry_price: number; stop_loss: number;
  take_profit_1: number; take_profit_2: number | null;
  exit_price: number | null; pnl: number | null; pnl_pct: number | null;
  mae: number; mfe: number; factors: Factor[];
  factor_review: Record<string, unknown> | null;
  events?: { timestamp: string; event_type: string; price: number; ai_analysis?: string; change_pct?: number }[];
  opened_at: string | null; closed_at: string | null; created_at: string;
  analysis_data?: Record<string, unknown>;
}

interface AnalysisResult {
  coin: string; timestamp: string;
  step1?: Record<string, unknown>; step2?: Record<string, unknown>;
  step3?: Record<string, unknown>; step4?: Record<string, unknown>;
  market_data?: Record<string, unknown>;
}

// ─── Helper: format analysis step into readable Chinese ───
function StepCard({ title, icon, data }: { title: string; icon: string; data: Record<string, unknown> | undefined }) {
  if (!data || "error" in data) return null;
  return (
    <div className="border border-card-border rounded-lg p-3 mb-3">
      <h4 className="text-sm font-semibold mb-2">{icon} {title}</h4>
      <div className="text-xs text-text-muted space-y-1.5">
        {Object.entries(data).map(([key, val]) => {
          if (key === "factors" && Array.isArray(val)) {
            return (
              <div key={key}>
                <span className="text-white font-medium">分析因子：</span>
                {(val as Factor[]).map((f, i) => (
                  <div key={i} className={`ml-2 mt-1 p-1.5 rounded text-xs ${f.bias === "看多" ? "bg-accent-green/10 text-accent-green" : f.bias === "看空" ? "bg-accent-red/10 text-accent-red" : "bg-accent-yellow/10 text-accent-yellow"}`}>
                    <span className="font-medium">{f.bias}</span> {f.description}
                  </div>
                ))}
              </div>
            );
          }
          if (Array.isArray(val)) {
            return <div key={key}><span className="text-white font-medium">{key}：</span>{val.join("；")}</div>;
          }
          if (typeof val === "object" && val !== null) {
            return <div key={key}><span className="text-white font-medium">{key}：</span>{JSON.stringify(val)}</div>;
          }
          return <div key={key}><span className="text-white font-medium">{key}：</span>{String(val)}</div>;
        })}
      </div>
    </div>
  );
}

// ─── Factor Review Display ───
function FactorReviewCard({ review }: { review: Record<string, unknown> }) {
  const reviews = (review.factor_reviews || []) as Array<{ factor_index: number; original: string; verdict: string; explanation: string }>;
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold">🔬 因子归因复盘</h4>
      {reviews.map((r, i) => (
        <div key={i} className={`p-2 rounded-lg text-xs border ${r.verdict?.includes("✅") ? "border-accent-green/30 bg-accent-green/5" : r.verdict?.includes("❌") ? "border-accent-red/30 bg-accent-red/5" : "border-accent-yellow/30 bg-accent-yellow/5"}`}>
          <div className="font-medium">{r.verdict} 因子{r.factor_index}: {r.original}</div>
          <div className="text-text-muted mt-1">{r.explanation}</div>
        </div>
      ))}
      {String(review.core_correct_factor || "") && (
        <div className="p-2 bg-accent-green/10 rounded-lg text-xs">
          <span className="font-semibold text-accent-green">✅ 核心正确因素：</span>{String(review.core_correct_factor)}
        </div>
      )}
      {String(review.core_wrong_factor || "") && (
        <div className="p-2 bg-accent-red/10 rounded-lg text-xs">
          <span className="font-semibold text-accent-red">❌ 核心错误因素：</span>{String(review.core_wrong_factor)}
        </div>
      )}
      {String(review.root_lesson || "") && (
        <div className="p-2 bg-accent-blue/10 rounded-lg text-xs">
          <span className="font-semibold text-accent-blue">📝 根源教训：</span>{String(review.root_lesson)}
        </div>
      )}
      {String(review.what_if || "") && (
        <div className="p-2 bg-accent-yellow/10 rounded-lg text-xs">
          <span className="font-semibold text-accent-yellow">🔄 如果重来：</span>{String(review.what_if)}
        </div>
      )}
      {String(review.reusable_rule || "") && (
        <div className="p-2 bg-purple-500/10 rounded-lg text-xs">
          <span className="font-semibold text-purple-400">📌 可复用规则：</span>{String(review.reusable_rule)}
        </div>
      )}
    </div>
  );
}

export default function SimTradingPanel() {
  const [account, setAccount] = useState<Account | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [allSymbols, setAllSymbols] = useState<string[]>([]);
  const [selectedCoin, setSelectedCoin] = useState("");
  const [coinSearch, setCoinSearch] = useState("");
  const [showCoinPicker, setShowCoinPicker] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [openingPosition, setOpeningPosition] = useState(false);
  const [klinesMap, setKlinesMap] = useState<Record<string, unknown[]>>({});
  const [selectedPositionId, setSelectedPositionId] = useState<number | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [livePrice, setLivePrice] = useState<Record<string, number>>({});
  const [viewMode, setViewMode] = useState<"trade" | "history">("trade");
  const pickerRef = useRef<HTMLDivElement>(null);


  const fetchData = useCallback(async () => {
    try {
      const [accRes, posRes] = await Promise.all([
        fetch(`${API}/sim/account`), fetch(`${API}/sim/positions`),
      ]);
      if (accRes.ok) setAccount(await accRes.json());
      if (posRes.ok) {
        const allPos: Position[] = await posRes.json();
        // Load events for open positions
        const openOnes = allPos.filter(p => p.status === "OPEN");
        await Promise.allSettled(openOnes.map(async (p) => {
          try {
            const evRes = await fetch(`${API}/sim/positions/${p.id}`);
            if (evRes.ok) { const detail = await evRes.json(); p.events = detail.events; }
          } catch { /* */ }
        }));
        setPositions(allPos);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchData();
    fetch(`${API}/derivatives/symbols`).then(r => r.ok ? r.json() : [])
      .then((data: Array<{ ccy?: string } | string>) => {
        setAllSymbols(data.map(d => typeof d === "string" ? d : (d.ccy || "")).filter(Boolean));
      }).catch(() => {});
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setShowCoinPicker(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    const openPos = positions.filter(p => p.status === "OPEN" || p.status === "PENDING");
    if (!openPos.length) return;
    const fetchPrices = async () => {
      const prices: Record<string, number> = {};
      await Promise.allSettled(openPos.map(async p => {
        try { const r = await fetch(`${API}/market/okx/${p.coin}`); if (r.ok) { const d = await r.json(); prices[p.coin] = d.price; } } catch { /* */ }
      }));
      setLivePrice(prices);
    };
    fetchPrices();
    const interval = setInterval(fetchPrices, 10000);
    return () => clearInterval(interval);
  }, [positions]);

  // Fetch klines for all active coins + selected coin
  const activeCoins = positions.filter(p => p.status === "OPEN" || p.status === "PENDING").map(p => p.coin);
  const chartCoins = Array.from(new Set([
    ...(selectedCoin ? [selectedCoin] : []),
    ...activeCoins,
  ]));
  useEffect(() => {
    if (!chartCoins.length) return;
    const fetchAll = async () => {
      const newMap: Record<string, unknown[]> = {};
      await Promise.allSettled(chartCoins.map(async (coin) => {
        try {
          const r = await fetch(`${API}/sim/klines/${coin}?bar=5m&limit=200`);
          if (r.ok) newMap[coin] = await r.json();
        } catch { /* */ }
      }));
      setKlinesMap(prev => ({ ...prev, ...newMap }));
    };
    fetchAll();
    const interval = setInterval(fetchAll, 60000);
    return () => clearInterval(interval);
  }, [chartCoins.join(",")]);

  const runAnalysis = async () => {
    if (!selectedCoin) return;
    setAnalyzing(true); setAnalysis(null); setCurrentStep(1);
    try {
      const res = await fetch(`${API}/sim/analyze/${selectedCoin}`, { method: "POST" });
      if (res.ok) { const d = await res.json(); setAnalysis(d); setCurrentStep(d.step4 ? 4 : d.step3 ? 3 : 2); }
    } catch { /* */ }
    setAnalyzing(false);
  };

  const confirmOpen = async () => {
    if (!analysis?.step4 || !analysis.step3) return;
    const s4 = analysis.step4 as Record<string, unknown>;
    if (s4.direction === "NONE") return;
    setOpeningPosition(true);
    try {
      const factors = ((analysis.step3 as Record<string, unknown>).factors as Factor[]) || [];
      await fetch(`${API}/sim/open`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ coin: selectedCoin, direction: s4.direction, entry_price: s4.entry_price, stop_loss: s4.stop_loss, take_profit_1: s4.take_profit_1, take_profit_2: s4.take_profit_2, factors }),
      });
      fetchData();
    } catch { /* */ }
    setOpeningPosition(false);
  };

  const closePos = async (id: number) => { await fetch(`${API}/sim/close/${id}`, { method: "POST" }); fetchData(); };
  const reviewPos = async (id: number) => { setReviewing(true); await fetch(`${API}/sim/review/${id}`, { method: "POST" }); await fetchData(); setReviewing(false); };
  const doRefund = async () => { await fetch(`${API}/sim/refund`, { method: "POST" }); fetchData(); };

  const openPositions = positions.filter(p => p.status === "OPEN" || p.status === "PENDING");
  const closedPositions = positions.filter(p => p.status === "CLOSED" || p.status === "LIQUIDATED");
  const selectedPosition = positions.find(p => p.id === selectedPositionId) || null;

  return (
    <div className="space-y-4">
      {/* Account Bar */}
      {account && (
        <div className="grid grid-cols-3 md:grid-cols-7 gap-2">
          {[
            { label: "账户余额", value: `$${account.balance.toFixed(2)}` },
            { label: "已用保证金", value: `$${account.used_margin.toFixed(2)}` },
            { label: "可用余额", value: `$${account.available_balance.toFixed(2)}` },
            { label: "累计盈亏", value: `${account.total_pnl >= 0 ? "+" : ""}${account.total_pnl.toFixed(2)}`, color: account.total_pnl >= 0 ? "text-accent-green" : "text-accent-red" },
            { label: "胜率", value: `${account.win_rate}%` },
            { label: "交易", value: `${account.wins}胜 ${account.losses}负` },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-card-bg border border-card-border rounded-lg p-2 text-center">
              <div className="text-[10px] text-text-muted">{label}</div>
              <div className={`text-sm font-bold font-mono ${color || ""}`}>{value}</div>
            </div>
          ))}
          <div className="bg-card-bg border border-card-border rounded-lg p-2 flex items-center justify-center">
            {account.can_refund ? (
              <button onClick={doRefund} className="px-2 py-1 bg-accent-yellow/20 text-accent-yellow rounded text-xs font-semibold hover:bg-accent-yellow/30">💰 补充资金</button>
            ) : <span className="text-[10px] text-text-muted">余额充足</span>}
          </div>
        </div>
      )}

      {/* Sub-tabs */}
      <div className="flex gap-2 border-b border-card-border pb-2">
        <button onClick={() => setViewMode("trade")} className={`px-4 py-1.5 rounded-lg text-sm font-medium ${viewMode === "trade" ? "bg-accent-blue/20 text-accent-blue" : "text-text-muted hover:text-white"}`}>
          📈 交易分析
        </button>
        <button onClick={() => setViewMode("history")} className={`px-4 py-1.5 rounded-lg text-sm font-medium ${viewMode === "history" ? "bg-accent-blue/20 text-accent-blue" : "text-text-muted hover:text-white"}`}>
          📋 历史 & 复盘 {closedPositions.length > 0 && `(${closedPositions.length})`}
        </button>
      </div>

      {viewMode === "trade" ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* LEFT: Coin Picker + Analysis */}
          <div className="lg:col-span-4 space-y-4">
            {/* Coin Picker */}
            <div className="bg-card-bg border border-card-border rounded-xl p-4">
              <h3 className="text-sm font-semibold mb-2">🔎 选择币种</h3>
              <div className="relative" ref={pickerRef}>
                <button onClick={() => setShowCoinPicker(!showCoinPicker)}
                  className="w-full px-3 py-2 bg-transparent border border-card-border rounded-lg text-left text-sm hover:border-accent-blue/40">
                  {selectedCoin ? `${selectedCoin}/USDT 永续` : "点击选择币种..."}
                </button>
                {showCoinPicker && (
                  <div className="absolute top-full left-0 mt-1 w-full bg-card-bg border border-card-border rounded-lg shadow-xl z-50">
                    <input type="text" placeholder="搜索..." value={coinSearch}
                      onChange={(e) => setCoinSearch(e.target.value.toUpperCase())}
                      className="w-full px-3 py-2 bg-transparent border-b border-card-border text-sm outline-none" autoFocus />
                    <div className="max-h-48 overflow-y-auto">
                      {allSymbols.filter(s => s.includes(coinSearch)).slice(0, 30).map(s => (
                        <button key={s} onClick={() => { setSelectedCoin(s); setShowCoinPicker(false); setCoinSearch(""); setAnalysis(null); }}
                          className="w-full text-left px-3 py-1.5 text-sm hover:bg-accent-blue/10">{s}/USDT</button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <button onClick={runAnalysis} disabled={!selectedCoin || analyzing}
                className="w-full mt-2 px-4 py-2 bg-accent-blue/20 text-accent-blue rounded-lg font-semibold text-sm hover:bg-accent-blue/30 disabled:opacity-50">
                {analyzing ? "🔬 AI 分析中（约30秒）..." : "🔬 开始深度分析"}
              </button>
            </div>

            {/* Analysis Results */}
            {(analyzing || analysis) && (
              <div className="bg-card-bg border border-card-border rounded-xl p-4 max-h-[600px] overflow-y-auto">
                <h3 className="text-sm font-semibold mb-3">📊 Gemini 四步分析</h3>
                {analyzing && !analysis && (
                  <div className="flex items-center gap-2 text-sm text-accent-blue animate-pulse">
                    <div className="w-4 h-4 border-2 border-accent-blue border-t-transparent rounded-full animate-spin" />
                    正在执行 Step {currentStep}...
                  </div>
                )}
                <StepCard title="基本面扫描" icon="🏗️" data={analysis?.step1 as Record<string, unknown>} />
                <StepCard title="分析策略选择" icon="🧠" data={analysis?.step2 as Record<string, unknown>} />
                <StepCard title="深度行情分析" icon="🔍" data={analysis?.step3 as Record<string, unknown>} />

                {/* Trade Decision */}
                {analysis?.step4 && (() => {
                  const s4 = analysis.step4 as Record<string, unknown>;
                  if (s4.direction === "NONE") return (
                    <div className="p-3 bg-accent-yellow/10 border border-accent-yellow/30 rounded-lg text-sm">
                      ⚠️ <span className="font-semibold">不建议交易</span><br />
                      <span className="text-xs text-text-muted">{String(s4.reasoning || "")}</span>
                    </div>
                  );
                  const isLong = s4.direction === "LONG";
                  return (
                    <div className={`p-3 rounded-lg border ${isLong ? "bg-accent-green/10 border-accent-green/30" : "bg-accent-red/10 border-accent-red/30"}`}>
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`text-lg font-bold ${isLong ? "text-accent-green" : "text-accent-red"}`}>{isLong ? "🟢 做多" : "🔴 做空"}</span>
                        <span className="text-xs bg-white/10 px-2 py-0.5 rounded">置信度 {String(s4.confidence)}%</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs font-mono mb-2">
                        <div>📍 入场: ${String(s4.entry_price)}</div>
                        <div>🛑 止损: ${String(s4.stop_loss)}</div>
                        <div>🎯 止盈1: ${String(s4.take_profit_1)}</div>
                        {s4.take_profit_2 ? <div>🎯 止盈2: ${String(s4.take_profit_2)}</div> : null}
                      </div>
                      <p className="text-xs text-text-muted mb-2">{String(s4.reasoning || "")}</p>
                      {s4.risk_assessment ? <p className="text-xs text-accent-yellow">⚠️ {String(s4.risk_assessment)}</p> : null}
                      <button onClick={confirmOpen} disabled={openingPosition}
                        className={`w-full mt-2 py-2 rounded-lg font-semibold text-sm ${isLong ? "bg-accent-green/20 text-accent-green hover:bg-accent-green/30" : "bg-accent-red/20 text-accent-red hover:bg-accent-red/30"} disabled:opacity-50`}>
                        {openingPosition ? "开仓中..." : "✅ 确认开仓 (10x全仓)"}
                      </button>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>

          {/* RIGHT: Charts + Active Positions */}
          <div className="lg:col-span-8 space-y-4">
            {/* Show a chart for each active coin */}
            <div className={`grid gap-4 ${chartCoins.length >= 2 ? "grid-cols-1 lg:grid-cols-2" : "grid-cols-1"}`}>
              {chartCoins.map(coin => {
                const coinKlines = klinesMap[coin] || [];
                const coinPos = openPositions.find(p => p.coin === coin);
                if (coinKlines.length === 0) return null;
                return (
                  <SimChart key={coin} coin={coin} klines={coinKlines as any}
                    entryPrice={coinPos?.entry_price || undefined}
                    stopLoss={coinPos?.stop_loss}
                    takeProfit1={coinPos?.take_profit_1}
                    takeProfit2={coinPos?.take_profit_2 || undefined}
                    events={coinPos?.events}
                    direction={coinPos?.direction} />
                );
              })}
            </div>

            {/* Active Positions */}
            <div className="bg-card-bg border border-card-border rounded-xl p-4">
              <h3 className="text-sm font-semibold mb-3">📈 活跃持仓 ({openPositions.length}/2)</h3>
              {openPositions.length === 0 ? (
                <p className="text-text-muted text-sm text-center py-4">暂无持仓</p>
              ) : openPositions.map(pos => {
                const price = livePrice[pos.coin];
                const entry = pos.entry_price || pos.target_entry_price;
                let livePnl = 0;
                if (price && pos.entry_price) {
                  livePnl = pos.direction === "LONG"
                    ? (price - pos.entry_price) / pos.entry_price * 100 * pos.leverage
                    : (pos.entry_price - price) / pos.entry_price * 100 * pos.leverage;
                }
                return (
                  <div key={pos.id} onClick={() => setSelectedPositionId(pos.id)}
                    className={`border rounded-lg p-3 mb-2 cursor-pointer transition-colors ${selectedPositionId === pos.id ? "border-accent-blue bg-accent-blue/5" : "border-card-border hover:border-accent-blue/40"}`}>
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <span className="font-bold">{pos.coin}/USDT</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${pos.direction === "LONG" ? "bg-accent-green/20 text-accent-green" : "bg-accent-red/20 text-accent-red"}`}>
                          {pos.direction === "LONG" ? "做多" : "做空"} {pos.leverage}x
                        </span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${pos.status === "OPEN" ? "bg-accent-blue/20 text-accent-blue" : "bg-accent-yellow/20 text-accent-yellow"}`}>
                          {pos.status === "OPEN" ? "持仓中" : "等待成交"}
                        </span>
                      </div>
                      <button onClick={(e) => { e.stopPropagation(); closePos(pos.id); }}
                        className="px-2 py-1 bg-accent-red/20 text-accent-red rounded text-xs hover:bg-accent-red/30">
                        {pos.status === "PENDING" ? "取消" : "市价平仓"}
                      </button>
                    </div>
                    <div className="grid grid-cols-5 gap-2 mt-2 text-xs">
                      <div><span className="text-text-muted">入场价</span><div className="font-mono">${entry}</div></div>
                      <div><span className="text-text-muted">现价</span><div className="font-mono">${price?.toFixed(6) || "..."}</div></div>
                      <div><span className="text-text-muted">浮动盈亏</span>
                        <div className={`font-mono font-bold ${livePnl >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                          {pos.status === "OPEN" ? `${livePnl >= 0 ? "+" : ""}${livePnl.toFixed(2)}%` : "等待中"}
                        </div>
                      </div>
                      <div><span className="text-text-muted">止损</span><div className="font-mono text-accent-red">${pos.stop_loss}</div></div>
                      <div><span className="text-text-muted">止盈</span><div className="font-mono text-accent-green">${pos.take_profit_1}</div></div>
                    </div>
                    {/* Volatility & Re-analysis Events */}
                    {pos.events && pos.events.filter(e => e.event_type === "VOLATILITY" || e.event_type === "AI_ANALYSIS").length > 0 && (
                      <div className="mt-2 space-y-1 border-t border-card-border pt-2">
                        {pos.events.filter(e => e.event_type === "VOLATILITY" || e.event_type === "AI_ANALYSIS").slice(-3).map((ev, i) => (
                          <div key={i} className={`text-[10px] p-1.5 rounded ${ev.event_type === "VOLATILITY" ? "bg-purple-500/10 text-purple-300" : "bg-accent-blue/10 text-accent-blue"}`}>
                            <span className="font-medium">{ev.event_type === "VOLATILITY" ? "⚡" : "🔄"} {ev.timestamp?.slice(11, 16)}</span>
                            {ev.change_pct ? ` ${ev.change_pct > 0 ? "+" : ""}${ev.change_pct}%` : ""} — {ev.ai_analysis?.slice(0, 150) || ""}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        /* HISTORY & REVIEW TAB */
        <div className="space-y-4">
          {closedPositions.length === 0 ? (
            <div className="bg-card-bg border border-card-border rounded-xl p-8 text-center text-text-muted">暂无历史交易</div>
          ) : closedPositions.map(pos => (
            <div key={pos.id} className="bg-card-bg border border-card-border rounded-xl p-4">
              {/* Header */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-lg">{pos.coin}/USDT</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${pos.direction === "LONG" ? "bg-accent-green/20 text-accent-green" : "bg-accent-red/20 text-accent-red"}`}>
                    {pos.direction === "LONG" ? "做多" : "做空"} {pos.leverage}x
                  </span>
                  {pos.status === "LIQUIDATED" && <span className="text-xs px-2 py-0.5 rounded bg-accent-red/30 text-accent-red">💥 爆仓</span>}
                </div>
                <span className={`text-xl font-bold font-mono ${(pos.pnl || 0) >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                  {(pos.pnl_pct || 0) >= 0 ? "+" : ""}{pos.pnl_pct?.toFixed(2)}% (${pos.pnl?.toFixed(2)})
                </span>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-6 gap-3 text-xs mb-3">
                <div><span className="text-text-muted">入场价</span><div className="font-mono">${pos.entry_price}</div></div>
                <div><span className="text-text-muted">平仓价</span><div className="font-mono">${pos.exit_price}</div></div>
                <div><span className="text-text-muted">保证金</span><div className="font-mono">${pos.margin?.toFixed(2)}</div></div>
                <div><span className="text-text-muted">最大回撤(MAE)</span><div className="font-mono text-accent-red">{pos.mae?.toFixed(2)}%</div></div>
                <div><span className="text-text-muted">最大浮盈(MFE)</span><div className="font-mono text-accent-green">+{pos.mfe?.toFixed(2)}%</div></div>
                <div><span className="text-text-muted">开仓时间</span><div className="font-mono">{pos.opened_at?.slice(5, 16) || "N/A"}</div></div>
              </div>

              {/* Factors at entry */}
              {pos.factors && pos.factors.length > 0 && (
                <details className="mb-3">
                  <summary className="text-xs text-accent-blue cursor-pointer font-semibold">📊 入场分析因子 ({pos.factors.length}个)</summary>
                  <div className="mt-2 space-y-1">
                    {pos.factors.map((f, i) => (
                      <div key={i} className={`p-1.5 rounded text-xs ${f.bias === "看多" ? "bg-accent-green/10 text-accent-green" : f.bias === "看空" ? "bg-accent-red/10 text-accent-red" : "bg-accent-yellow/10 text-accent-yellow"}`}>
                        <span className="font-medium">{f.bias}</span> {f.description}
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {/* Factor Review */}
              {pos.factor_review ? (
                <FactorReviewCard review={pos.factor_review} />
              ) : (
                <button onClick={() => reviewPos(pos.id)} disabled={reviewing}
                  className="px-4 py-2 bg-accent-blue/20 text-accent-blue rounded-lg text-sm font-semibold hover:bg-accent-blue/30 disabled:opacity-50">
                  {reviewing ? "🔬 AI 复盘中..." : "🔬 生成深度复盘"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}