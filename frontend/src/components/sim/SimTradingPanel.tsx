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
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyObj = Record<string, any>;
interface AnalysisResult {
  coin: string; timestamp: string;
  call1?: AnyObj; call2?: AnyObj; call3?: AnyObj; call4?: AnyObj;
  market_data?: AnyObj;
}

/* ─── Helper: render key-value pairs from obj ─── */
function KV({ label, value, color }: { label: string; value: string; color?: string }) {
  return <div className="flex justify-between text-xs py-0.5 border-b border-white/5"><span className="text-text-muted">{label}</span><span className={color || ""}>{value}</span></div>;
}
function Badge({ text, type }: { text: string; type: "green" | "red" | "yellow" | "blue" | "purple" }) {
  const c = { green: "bg-accent-green/15 text-accent-green", red: "bg-accent-red/15 text-accent-red", yellow: "bg-accent-yellow/15 text-accent-yellow", blue: "bg-accent-blue/15 text-accent-blue", purple: "bg-purple-500/15 text-purple-300" };
  return <span className={`text-[10px] px-1.5 py-0.5 rounded ${c[type]}`}>{text}</span>;
}

/* ─── Collapsible dimension section ─── */
function DimSection({ title, icon, defaultOpen, children }: { title: string; icon: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen || false);
  return (
    <div className="border border-card-border rounded-lg overflow-hidden mb-2">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between px-3 py-2 bg-card-bg hover:bg-white/5 text-sm font-semibold text-left">
        <span>{icon} {title}</span><span className="text-text-muted text-xs">{open ? "▼" : "▶"}</span>
      </button>
      {open && <div className="px-3 py-2 text-xs space-y-1">{children}</div>}
    </div>
  );
}

/* ─── Factor Review for postmortem ─── */
function FactorReviewCard({ review }: { review: AnyObj }) {
  const reviews = (review.factor_reviews || []) as Array<{ factor_index: number; original: string; verdict: string; explanation: string }>;
  const dimReview = review.dimension_review as AnyObj | undefined;
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold">🔬 9维因子归因复盘</h4>
      {reviews.map((r, i) => (
        <div key={i} className={`p-2 rounded text-xs border ${r.verdict?.includes("✅") ? "border-accent-green/30 bg-accent-green/5" : r.verdict?.includes("❌") ? "border-accent-red/30 bg-accent-red/5" : "border-accent-yellow/30 bg-accent-yellow/5"}`}>
          <div className="font-medium">{r.verdict} 因子{r.factor_index}: {r.original}</div>
          <div className="text-text-muted mt-1">{r.explanation}</div>
        </div>
      ))}
      {dimReview && (
        <DimSection title="各维度复盘" icon="📐" defaultOpen>
          {Object.entries(dimReview).map(([k, v]) => <KV key={k} label={k} value={String(v)} />)}
        </DimSection>
      )}
      {[
        { key: "core_correct_factor", icon: "✅", label: "核心正确因素", type: "green" as const },
        { key: "core_wrong_factor", icon: "❌", label: "核心错误因素", type: "red" as const },
        { key: "root_lesson", icon: "📝", label: "根源教训", type: "blue" as const },
        { key: "what_if", icon: "🔄", label: "如果重来", type: "yellow" as const },
        { key: "reusable_rule", icon: "📌", label: "可复用规则", type: "purple" as const },
      ].map(({ key, icon, label, type }) => review[key] ? (
        <div key={key} className={`p-2 rounded text-xs ${type === "green" ? "bg-accent-green/10" : type === "red" ? "bg-accent-red/10" : type === "blue" ? "bg-accent-blue/10" : type === "yellow" ? "bg-accent-yellow/10" : "bg-purple-500/10"}`}>
          <span className="font-semibold">{icon} {label}：</span>{String(review[key])}
        </div>
      ) : null)}
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
      if (res.ok) { const d = await res.json(); setAnalysis(d); setCurrentStep(4); }
    } catch { /* */ }
    setAnalyzing(false);
  };

  const confirmOpen = async () => {
    if (!analysis?.call4) return;
    const td = (analysis.call4 as AnyObj).trade_decision;
    if (!td || td.direction === "NONE") return;
    setOpeningPosition(true);
    try {
      // Collect factors from call2 (technical) + call4 (summary)
      const techFactors = (analysis.call2 as AnyObj)?.factors || [];
      const summaryFactors = (analysis.call4 as AnyObj)?.factors || [];
      const allFactors = [...techFactors, ...summaryFactors];
      await fetch(`${API}/sim/open`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          coin: selectedCoin, direction: td.direction,
          entry_price: td.entry_price, stop_loss: td.stop_loss,
          take_profit_1: td.take_profit_1, take_profit_2: td.take_profit_2,
          factors: allFactors,
        }),
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

  // Derive trade decision
  const td = (analysis?.call4 as AnyObj)?.trade_decision;
  const c1 = analysis?.call1 as AnyObj;
  const c2 = analysis?.call2 as AnyObj;
  const c3 = analysis?.call3 as AnyObj;
  const c4 = analysis?.call4 as AnyObj;

  return (
    <div className="space-y-4">
      {/* ═══ ACCOUNT BAR ═══ */}
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

      {/* ═══ COIN PICKER ═══ */}
      <div className="flex items-center gap-3 bg-card-bg border border-card-border rounded-xl p-3">
        <div className="relative flex-1" ref={pickerRef}>
          <button onClick={() => setShowCoinPicker(!showCoinPicker)}
            className="w-full px-3 py-2 bg-transparent border border-card-border rounded-lg text-left text-sm hover:border-accent-blue/40">
            {selectedCoin ? `${selectedCoin}/USDT 永续` : "点击选择币种..."}
          </button>
          {showCoinPicker && (
            <div className="absolute top-full left-0 mt-1 w-full bg-card-bg border border-card-border rounded-lg shadow-xl z-50">
              <input type="text" placeholder="搜索..." value={coinSearch} onChange={(e) => setCoinSearch(e.target.value.toUpperCase())}
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
          className="px-6 py-2 bg-accent-blue/20 text-accent-blue rounded-lg font-semibold text-sm hover:bg-accent-blue/30 disabled:opacity-50 whitespace-nowrap">
          {analyzing ? "🔬 9维分析中..." : "🔬 开始深度分析"}
        </button>
      </div>

      {/* ═══ SUB-TABS ═══ */}
      <div className="flex gap-2 border-b border-card-border pb-2">
        <button onClick={() => setViewMode("trade")} className={`px-4 py-1.5 rounded-lg text-sm font-medium ${viewMode === "trade" ? "bg-accent-blue/20 text-accent-blue" : "text-text-muted hover:text-white"}`}>
          📈 交易分析
        </button>
        <button onClick={() => setViewMode("history")} className={`px-4 py-1.5 rounded-lg text-sm font-medium ${viewMode === "history" ? "bg-accent-blue/20 text-accent-blue" : "text-text-muted hover:text-white"}`}>
          📋 历史 & 复盘 {closedPositions.length > 0 && `(${closedPositions.length})`}
        </button>
      </div>

      {viewMode === "trade" ? (<>
        {/* ═══ LOADING ═══ */}
        {analyzing && !analysis && (
          <div className="bg-card-bg border border-accent-blue/30 rounded-xl p-6 text-center">
            <div className="w-8 h-8 border-[3px] border-accent-blue border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-sm text-accent-blue font-semibold">🔬 9维深度分析中（约60秒）...</p>
            <p className="text-xs text-text-muted mt-1">代币经济学 → 技术面 → 链上+宏观+情绪 → 交易决策</p>
          </div>
        )}

        {/* ═══ 1. EXECUTIVE SUMMARY (always on top after analysis) ═══ */}
        {c4?.executive_summary && (
          <div className="bg-card-bg border-2 border-accent-blue/40 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-bold">📋 执行摘要</h3>
              <div className="flex gap-2">
                <Badge text={`📈 涨 ${c4.executive_summary.probability?.up || 0}%`} type="green" />
                <Badge text={`📉 跌 ${c4.executive_summary.probability?.down || 0}%`} type="red" />
                <Badge text={`➡️ 震荡 ${c4.executive_summary.probability?.sideways || 0}%`} type="yellow" />
              </div>
            </div>
            <p className="text-sm font-medium mb-2">{c4.executive_summary.core_conclusion}</p>
            <div className="flex flex-wrap gap-2 text-xs">
              {c4.executive_summary.recommended_action && <Badge text={`建议: ${c4.executive_summary.recommended_action}`} type="blue" />}
              {c4.multi_dimension_confluence?.pump_dump_stage && <Badge text={`P&D阶段: ${c4.multi_dimension_confluence.pump_dump_stage}`} type="purple" />}
              {c4.top_bottom_confirmation?.verdict && <Badge text={`触顶/底: ${c4.top_bottom_confirmation.verdict}`} type="yellow" />}
            </div>
          </div>
        )}

        {/* ═══ 2. SIGNAL SUMMARY + ORDER BUTTON (prominent!) ═══ */}
        {td && (
          <div className={`border-2 rounded-xl p-5 ${td.direction === "LONG" ? "bg-accent-green/5 border-accent-green/50" : td.direction === "SHORT" ? "bg-accent-red/5 border-accent-red/50" : "bg-accent-yellow/5 border-accent-yellow/50"}`}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <span className={`text-2xl font-bold ${td.direction === "LONG" ? "text-accent-green" : td.direction === "SHORT" ? "text-accent-red" : "text-accent-yellow"}`}>
                  {td.direction === "LONG" ? "🟢 建议做多" : td.direction === "SHORT" ? "🔴 建议做空" : "⚠️ 不建议交易"}
                </span>
                <Badge text={`置信度 ${td.confidence}%`} type="blue" />
              </div>
              {td.direction !== "NONE" && (
                <button onClick={confirmOpen} disabled={openingPosition}
                  className={`px-8 py-3 rounded-xl font-bold text-base shadow-lg transition-all hover:scale-105 ${td.direction === "LONG" ? "bg-accent-green text-black hover:bg-accent-green/90" : "bg-accent-red text-white hover:bg-accent-red/90"} disabled:opacity-50 disabled:hover:scale-100`}>
                  {openingPosition ? "⏳ 开仓中..." : "✅ 确认开仓 (10x全仓)"}
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-sm font-mono mb-3">
              <div className="bg-black/20 rounded-lg p-3 text-center"><span className="text-text-muted text-[10px] block mb-1">📍 入场价</span><span className="font-bold">${td.entry_price}</span></div>
              <div className="bg-black/20 rounded-lg p-3 text-center"><span className="text-text-muted text-[10px] block mb-1">🛑 止损</span><span className="font-bold text-accent-red">${td.stop_loss}</span></div>
              <div className="bg-black/20 rounded-lg p-3 text-center"><span className="text-text-muted text-[10px] block mb-1">🎯 止盈1</span><span className="font-bold text-accent-green">${td.take_profit_1}</span></div>
              {td.take_profit_2 ? <div className="bg-black/20 rounded-lg p-3 text-center"><span className="text-text-muted text-[10px] block mb-1">🎯 止盈2</span><span className="font-bold text-accent-green">${td.take_profit_2}</span></div> : null}
              {c2?.key_levels?.support && <div className="bg-black/20 rounded-lg p-3 text-center"><span className="text-text-muted text-[10px] block mb-1">📊 支撑位</span><span className="text-accent-blue text-xs">{c2.key_levels.support.map((s: number) => `$${s}`).join(" / ")}</span></div>}
              {c2?.key_levels?.resistance && <div className="bg-black/20 rounded-lg p-3 text-center"><span className="text-text-muted text-[10px] block mb-1">📊 阻力位</span><span className="text-accent-yellow text-xs">{c2.key_levels.resistance.map((r: number) => `$${r}`).join(" / ")}</span></div>}
            </div>
            <p className="text-xs text-text-muted">{td.reasoning}</p>
            {td.risk_assessment ? <p className="text-xs text-accent-yellow mt-1">⚠️ 风险: {td.risk_assessment}</p> : null}
            {td.key_invalidation ? <p className="text-xs text-accent-red/70 mt-1">❌ 失效条件: {td.key_invalidation}</p> : null}
          </div>
        )}

        {/* ═══ 3. K-LINE CHARTS ═══ */}
        {chartCoins.length > 0 && (
          <div className={`grid gap-4 ${chartCoins.length >= 2 ? "grid-cols-1 lg:grid-cols-2" : "grid-cols-1"}`}>
            {chartCoins.map(coin => {
              const coinKlines = klinesMap[coin] || [];
              const coinPos = openPositions.find(p => p.coin === coin);
              if (coinKlines.length === 0) return null;
              return <SimChart key={coin} coin={coin} klines={coinKlines as any}
                entryPrice={coinPos?.entry_price || undefined} stopLoss={coinPos?.stop_loss}
                takeProfit1={coinPos?.take_profit_1} takeProfit2={coinPos?.take_profit_2 || undefined}
                events={coinPos?.events} direction={coinPos?.direction} />;
            })}
          </div>
        )}

        {/* ═══ 4. ACTIVE POSITIONS ═══ */}
        {openPositions.length > 0 && (
          <div className="bg-card-bg border border-card-border rounded-xl p-4">
            <h3 className="text-sm font-semibold mb-2">📈 活跃持仓 ({openPositions.length}/2)</h3>
            {openPositions.map(pos => {
              const price = livePrice[pos.coin]; const entry = pos.entry_price || pos.target_entry_price;
              let livePnl = 0;
              if (price && pos.entry_price) { livePnl = pos.direction === "LONG" ? (price - pos.entry_price) / pos.entry_price * 100 * pos.leverage : (pos.entry_price - price) / pos.entry_price * 100 * pos.leverage; }
              return (
                <div key={pos.id} className="border border-card-border rounded-lg p-3 mb-2">
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <span className="font-bold">{pos.coin}/USDT</span>
                      <Badge text={`${pos.direction === "LONG" ? "做多" : "做空"} ${pos.leverage}x`} type={pos.direction === "LONG" ? "green" : "red"} />
                      <Badge text={pos.status === "OPEN" ? "持仓中" : "等待成交"} type={pos.status === "OPEN" ? "blue" : "yellow"} />
                    </div>
                    <button onClick={() => closePos(pos.id)} className="px-2 py-1 bg-accent-red/20 text-accent-red rounded text-xs hover:bg-accent-red/30">{pos.status === "PENDING" ? "取消" : "市价平仓"}</button>
                  </div>
                  <div className="grid grid-cols-5 gap-2 mt-2 text-xs">
                    <div><span className="text-text-muted">入场</span><div className="font-mono">${entry}</div></div>
                    <div><span className="text-text-muted">现价</span><div className="font-mono">${price?.toFixed(6) || "..."}</div></div>
                    <div><span className="text-text-muted">浮动盈亏</span><div className={`font-mono font-bold ${livePnl >= 0 ? "text-accent-green" : "text-accent-red"}`}>{pos.status === "OPEN" ? `${livePnl >= 0 ? "+" : ""}${livePnl.toFixed(2)}%` : "—"}</div></div>
                    <div><span className="text-text-muted">止损</span><div className="font-mono text-accent-red">${pos.stop_loss}</div></div>
                    <div><span className="text-text-muted">止盈</span><div className="font-mono text-accent-green">${pos.take_profit_1}</div></div>
                  </div>
                  {pos.events && pos.events.filter(e => ["VOLATILITY","AI_ANALYSIS"].includes(e.event_type)).length > 0 && (
                    <div className="mt-2 space-y-1 border-t border-card-border pt-2">
                      {pos.events.filter(e => ["VOLATILITY","AI_ANALYSIS"].includes(e.event_type)).slice(-3).map((ev, i) => (
                        <div key={i} className={`text-[10px] p-1.5 rounded ${ev.event_type === "VOLATILITY" ? "bg-purple-500/10 text-purple-300" : "bg-accent-blue/10 text-accent-blue"}`}>
                          {ev.event_type === "VOLATILITY" ? "⚡" : "🔄"} {ev.timestamp?.slice(11, 16)} {ev.change_pct ? `${ev.change_pct > 0 ? "+" : ""}${ev.change_pct}%` : ""} — {ev.ai_analysis?.slice(0, 150)}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* ═══ 5. 9-DIMENSION ANALYSIS ═══ */}
        {analysis && (
          <div className="space-y-2">
            {/* ── 技术面 (standalone prominent section) ── */}
            {c2 && !c2.error && (
              <div className="bg-card-bg border border-card-border rounded-xl p-4">
                <h3 className="text-sm font-bold mb-3">📐 技术面分析</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {/* Market Structure */}
                  {c2.market_structure && (
                    <div className="bg-white/5 rounded-lg p-3">
                      <h4 className="text-[10px] text-text-muted mb-2">市场结构</h4>
                      <div className="flex items-center gap-2 mb-1">
                        <Badge text={c2.market_structure.trend || "N/A"} type={c2.market_structure.trend?.includes("上") ? "green" : c2.market_structure.trend?.includes("下") ? "red" : "yellow"} />
                        {c2.market_structure.bos_choch && <span className="text-xs">{c2.market_structure.bos_choch}</span>}
                      </div>
                      <p className="text-[11px] text-text-muted">{c2.market_structure.hh_hl_or_lh_ll}</p>
                    </div>
                  )}
                  {/* Momentum Gauges */}
                  {c2.momentum && (
                    <div className="bg-white/5 rounded-lg p-3">
                      <h4 className="text-[10px] text-text-muted mb-2">动量指标</h4>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="flex justify-between"><span>RSI(14)</span><span className={`font-mono font-bold ${String(c2.momentum.rsi_14).includes("超买") ? "text-accent-red" : String(c2.momentum.rsi_14).includes("超卖") ? "text-accent-green" : ""}`}>{c2.momentum.rsi_14}</span></div>
                        <div className="flex justify-between"><span>MACD</span><span className="font-mono">{c2.momentum.macd}</span></div>
                        <div className="flex justify-between"><span>RSI背离</span><span className={`font-mono ${String(c2.momentum.rsi_divergence).includes("是") || String(c2.momentum.rsi_divergence).includes("背离") ? "text-accent-yellow font-bold" : ""}`}>{c2.momentum.rsi_divergence}</span></div>
                        <div className="flex justify-between"><span>ADX</span><span className="font-mono">{c2.momentum.adx}</span></div>
                      </div>
                    </div>
                  )}
                  {/* Volatility */}
                  {c2.volatility && (
                    <div className="bg-white/5 rounded-lg p-3">
                      <h4 className="text-[10px] text-text-muted mb-2">波动率</h4>
                      <div className="text-xs space-y-1">
                        <div className="flex justify-between"><span>Bollinger</span><span className="font-mono">{c2.volatility.bollinger}</span></div>
                        <div className="flex justify-between"><span>ATR</span><span className="font-mono">{c2.volatility.atr}</span></div>
                      </div>
                    </div>
                  )}
                  {/* Volume */}
                  {c2.volume_analysis && (
                    <div className="bg-white/5 rounded-lg p-3">
                      <h4 className="text-[10px] text-text-muted mb-2">量价分析</h4>
                      <div className="text-xs space-y-1">
                        <div className="flex justify-between"><span>OBV</span><span className="font-mono">{c2.volume_analysis.obv_trend}</span></div>
                        <div className="flex justify-between"><span>量价背离</span><span className={`font-mono ${String(c2.volume_analysis.volume_price_divergence).includes("是") ? "text-accent-yellow font-bold" : ""}`}>{c2.volume_analysis.volume_price_divergence}</span></div>
                        <div className="flex justify-between"><span>VWAP</span><span className="font-mono">{c2.volume_analysis.vwap}</span></div>
                      </div>
                    </div>
                  )}
                  {/* Trend/MA */}
                  {c2.trend_ma && (
                    <div className="bg-white/5 rounded-lg p-3">
                      <h4 className="text-[10px] text-text-muted mb-2">趋势 & MA</h4>
                      <div className="text-xs space-y-1">
                        <div className="flex justify-between"><span>EMA对齐</span><span className="font-mono">{c2.trend_ma.alignment}</span></div>
                        <div className="flex justify-between"><span>金叉/死叉</span><span className={`font-mono ${String(c2.trend_ma.golden_death_cross).includes("金叉") ? "text-accent-green" : String(c2.trend_ma.golden_death_cross).includes("死叉") ? "text-accent-red" : ""}`}>{c2.trend_ma.golden_death_cross}</span></div>
                      </div>
                    </div>
                  )}
                  {/* Advanced */}
                  {c2.advanced && (
                    <div className="bg-white/5 rounded-lg p-3">
                      <h4 className="text-[10px] text-text-muted mb-2">高级指标</h4>
                      <div className="text-xs space-y-1">
                        {c2.advanced.ichimoku && <div className="flex justify-between"><span>Ichimoku</span><span className="font-mono">{c2.advanced.ichimoku}</span></div>}
                        {c2.advanced.fibonacci_levels && <div className="flex justify-between"><span>Fibonacci</span><span className="font-mono">{c2.advanced.fibonacci_levels}</span></div>}
                        {c2.advanced.supertrend && <div className="flex justify-between"><span>Supertrend</span><span className="font-mono">{c2.advanced.supertrend}</span></div>}
                      </div>
                    </div>
                  )}
                </div>
                {/* K-line patterns */}
                {c2.candlestick_patterns && (
                  <div className="mt-3 flex flex-wrap gap-1">
                    <span className="text-[10px] text-text-muted mr-1">K线形态:</span>
                    {(Array.isArray(c2.candlestick_patterns) ? c2.candlestick_patterns : [String(c2.candlestick_patterns)]).map((p: string, i: number) => <Badge key={i} text={p} type="blue" />)}
                  </div>
                )}
                {/* Multi-timeframe */}
                {c2.multi_timeframe && (
                  <div className="mt-3 grid grid-cols-4 gap-2 text-xs">
                    <div className="bg-white/5 rounded p-2 text-center"><span className="text-[10px] text-text-muted block">日线</span>{c2.multi_timeframe.daily}</div>
                    <div className="bg-white/5 rounded p-2 text-center"><span className="text-[10px] text-text-muted block">4H</span>{c2.multi_timeframe.four_hour}</div>
                    <div className="bg-white/5 rounded p-2 text-center"><span className="text-[10px] text-text-muted block">1H</span>{c2.multi_timeframe.one_hour}</div>
                    <div className={`rounded p-2 text-center ${String(c2.multi_timeframe.confluence).includes("是") ? "bg-accent-green/10" : "bg-white/5"}`}><span className="text-[10px] text-text-muted block">共振</span><span className="font-semibold">{c2.multi_timeframe.confluence}</span></div>
                  </div>
                )}
                {/* Top/Bottom verdict */}
                {c2.top_bottom && (
                  <div className={`mt-3 p-3 rounded-lg border ${String(c2.top_bottom.verdict).includes("顶") ? "border-accent-red/30 bg-accent-red/5" : String(c2.top_bottom.verdict).includes("底") ? "border-accent-green/30 bg-accent-green/5" : "border-accent-yellow/30 bg-accent-yellow/5"}`}>
                    <div className="flex items-center gap-2 mb-2"><span className="text-sm font-bold">🔮 {c2.top_bottom.verdict}</span></div>
                    {c2.top_bottom.signals_present?.length > 0 && <div className="flex flex-wrap gap-1 mb-1">{c2.top_bottom.signals_present.map((s: string, i: number) => <Badge key={i} text={`✅ ${s}`} type="green" />)}</div>}
                    {c2.top_bottom.signals_missing?.length > 0 && <div className="flex flex-wrap gap-1">{c2.top_bottom.signals_missing.map((s: string, i: number) => <Badge key={i} text={`❓ ${s}`} type="yellow" />)}</div>}
                    {c2.top_bottom.pump_dump_stage && <p className="text-xs text-text-muted mt-1">Pump&Dump: {c2.top_bottom.pump_dump_stage}</p>}
                  </div>
                )}
              </div>
            )}

            {/* ── 信息面 (enhanced with detail) ── */}
            {c1?.news_catalyst && (
              <div className="bg-card-bg border border-card-border rounded-xl p-4">
                <h3 className="text-sm font-bold mb-3">📰 信息面 / 催化剂 (7-30天)</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {/* Bullish */}
                  <div>
                    <h4 className="text-[10px] text-accent-green font-semibold mb-2">🟢 利好</h4>
                    {c1.news_catalyst.bullish_news?.length > 0 ? c1.news_catalyst.bullish_news.map((n: AnyObj, i: number) => (
                      <div key={i} className="bg-accent-green/5 border border-accent-green/20 rounded-lg p-2 mb-2">
                        <div className="flex items-center gap-2 mb-1"><Badge text={n.impact || "中"} type="green" /><span className="text-xs font-medium">{n.event}</span></div>
                        {n.detail && <p className="text-[11px] text-text-muted">{n.detail}</p>}
                      </div>
                    )) : <p className="text-xs text-text-muted">暂无利好消息</p>}
                  </div>
                  {/* Bearish */}
                  <div>
                    <h4 className="text-[10px] text-accent-red font-semibold mb-2">🔴 利空</h4>
                    {c1.news_catalyst.bearish_news?.length > 0 ? c1.news_catalyst.bearish_news.map((n: AnyObj, i: number) => (
                      <div key={i} className="bg-accent-red/5 border border-accent-red/20 rounded-lg p-2 mb-2">
                        <div className="flex items-center gap-2 mb-1"><Badge text={n.impact || "中"} type="red" /><span className="text-xs font-medium">{n.event}</span></div>
                        {n.detail && <p className="text-[11px] text-text-muted">{n.detail}</p>}
                      </div>
                    )) : <p className="text-xs text-text-muted">暂无利空消息</p>}
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {c1.news_catalyst.catalyst_strength && <Badge text={`催化剂强度: ${c1.news_catalyst.catalyst_strength}`} type="blue" />}
                  {c1.news_catalyst.narrative_position && <Badge text={`叙事: ${c1.news_catalyst.narrative_position}`} type="purple" />}
                </div>
              </div>
            )}

            {/* ── 代币经济学 ── */}
            {c1?.token_economics && (
              <DimSection title="代币经济学" icon="💰">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
                  {[["总发行量", c1.token_economics.total_supply], ["流通量", c1.token_economics.circulating_supply], ["市值", c1.token_economics.market_cap], ["FDV", c1.token_economics.fdv],
                    ["24h成交量", c1.token_economics.volume_24h], ["换手率", c1.token_economics.turnover_rate], ["24h量比", c1.token_economics.volume_ratio_24h], ["赛道", c1.token_economics.sector],
                  ].map(([l, v]) => <div key={String(l)} className="bg-white/5 rounded p-1.5"><span className="text-text-muted text-[10px] block">{l}</span><span className="font-mono text-xs">{String(v || "N/A")}</span></div>)}
                </div>
                {c1.token_economics.token_model && <p className="text-xs text-text-muted">{c1.token_economics.token_model}</p>}
                {c1.token_economics.risk_flags?.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{c1.token_economics.risk_flags.map((r: string, i: number) => <Badge key={i} text={`⚠️ ${r}`} type="red" />)}</div>}
              </DimSection>
            )}

            {/* ── 链上 + 宏观 + 庄家 + 情绪 + 流动性 (compact grid) ── */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {c3?.onchain && (
                <DimSection title="链上数据" icon="⛓️">
                  <KV label="鲸鱼流向" value={c3.onchain.whale_flow} /><KV label="MVRV" value={c3.onchain.mvrv} /><KV label="NVT" value={c3.onchain.nvt} />
                  <KV label="团队钱包" value={c3.onchain.team_wallet} />
                  <KV label="聪明钱" value={c3.onchain.smart_money_verdict} color={c3.onchain.smart_money_verdict?.includes("积累") ? "text-accent-green font-bold" : c3.onchain.smart_money_verdict?.includes("分发") ? "text-accent-red font-bold" : ""} />
                </DimSection>
              )}
              {c3?.macro && (
                <DimSection title="宏观市场" icon="🌍">
                  <KV label="BTC Dominance" value={c3.macro.btc_dominance} /><KV label="Altcoin Season" value={c3.macro.altcoin_season} />
                  <KV label="Fear & Greed" value={c3.macro.fear_greed} /><KV label="市场阶段" value={c3.macro.market_phase} />
                </DimSection>
              )}
              {c3?.whale_manipulation && (
                <DimSection title="庄家/操纵" icon="🐋">
                  <KV label="筹码集中度" value={c3.whale_manipulation.chip_concentration} /><KV label="拉盘成本" value={c3.whale_manipulation.pump_cost_estimate} />
                  <KV label="刷量风险" value={c3.whale_manipulation.wash_trading_risk} color={c3.whale_manipulation.wash_trading_risk === "高" ? "text-accent-red font-bold" : ""} />
                </DimSection>
              )}
              {c3?.sentiment && (
                <DimSection title="情绪面" icon="📊">
                  <KV label="社交热度" value={c3.sentiment.social_heat} /><KV label="多空比" value={c3.sentiment.bull_bear_ratio} />
                  <KV label="FOMO" value={c3.sentiment.fomo_level} /><KV label="整体" value={c3.sentiment.overall} />
                </DimSection>
              )}
            </div>

            {c3?.liquidity_risk && (
              <DimSection title="流动性与风险" icon="💧">
                <div className="flex flex-wrap gap-2 mb-2">
                  <KV label="滑点风险" value={c3.liquidity_risk.slippage_risk} /><KV label="资金费率" value={c3.liquidity_risk.funding_rate_impact} />
                  <KV label="风险等级" value={c3.liquidity_risk.risk_level} color={c3.liquidity_risk.risk_level === "高" ? "text-accent-red font-bold" : ""} />
                </div>
                {c3.liquidity_risk.major_risks?.length > 0 && <div className="flex flex-wrap gap-1">{c3.liquidity_risk.major_risks.map((r: string, i: number) => <Badge key={i} text={`⚠️ ${r}`} type="red" />)}</div>}
              </DimSection>
            )}

            {c4?.alert_indicators?.length > 0 && (
              <div className="bg-accent-yellow/10 border border-accent-yellow/30 rounded-lg p-3">
                <h4 className="text-xs font-semibold text-accent-yellow mb-1">🔔 关键监测指标</h4>
                <div className="flex flex-wrap gap-1">{c4.alert_indicators.map((a: string, i: number) => <Badge key={i} text={a} type="yellow" />)}</div>
              </div>
            )}
          </div>
        )}
      </>) : (
        /* ═══ HISTORY & REVIEW TAB ═══ */
        <div className="space-y-4">
          {closedPositions.length === 0 ? (
            <div className="bg-card-bg border border-card-border rounded-xl p-8 text-center text-text-muted">暂无历史交易</div>
          ) : closedPositions.map(pos => (
            <div key={pos.id} className="bg-card-bg border border-card-border rounded-xl p-4">
              {/* Header with P&L */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-lg">{pos.coin}/USDT</span>
                  <Badge text={`${pos.direction === "LONG" ? "做多" : "做空"} ${pos.leverage}x`} type={pos.direction === "LONG" ? "green" : "red"} />
                  {pos.status === "LIQUIDATED" && <Badge text="💥 爆仓" type="red" />}
                </div>
                <span className={`text-2xl font-bold font-mono ${(pos.pnl || 0) >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                  {(pos.pnl_pct || 0) >= 0 ? "+" : ""}{pos.pnl_pct?.toFixed(2)}%
                  <span className="text-sm ml-1">(${pos.pnl?.toFixed(2)})</span>
                </span>
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-6 gap-3 text-xs mb-4">
                {[["入场价", `$${pos.entry_price}`], ["平仓价", `$${pos.exit_price}`], ["保证金", `$${pos.margin?.toFixed(2)}`],
                  ["MAE", `${pos.mae?.toFixed(2)}%`, "text-accent-red"], ["MFE", `+${pos.mfe?.toFixed(2)}%`, "text-accent-green"], ["开仓", pos.opened_at?.slice(5, 16) || "N/A"],
                ].map(([l, v, c]) => <div key={String(l)} className="bg-white/5 rounded p-2"><span className="text-text-muted text-[10px] block">{l}</span><div className={`font-mono ${c || ""}`}>{v}</div></div>)}
              </div>

              {/* Factor Review — Visual */}
              {pos.factor_review ? (() => {
                const rv = pos.factor_review as AnyObj;
                const reviews = (rv.factor_reviews || []) as Array<{ factor_index: number; original: string; verdict: string; explanation: string }>;
                const dimReview = rv.dimension_review as AnyObj | undefined;
                return (
                  <div className="space-y-3">
                    {/* Quick verdict row */}
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                      {rv.core_correct_factor && (
                        <div className="bg-accent-green/10 border border-accent-green/30 rounded-lg p-3">
                          <span className="text-[10px] text-accent-green block mb-1">✅ 核心正确因素</span>
                          <span className="text-xs font-medium">{String(rv.core_correct_factor)}</span>
                        </div>
                      )}
                      {rv.core_wrong_factor && (
                        <div className="bg-accent-red/10 border border-accent-red/30 rounded-lg p-3">
                          <span className="text-[10px] text-accent-red block mb-1">❌ 核心错误因素</span>
                          <span className="text-xs font-medium">{String(rv.core_wrong_factor)}</span>
                        </div>
                      )}
                      {rv.root_lesson && (
                        <div className="bg-accent-blue/10 border border-accent-blue/30 rounded-lg p-3">
                          <span className="text-[10px] text-accent-blue block mb-1">📝 根源教训</span>
                          <span className="text-xs font-medium">{String(rv.root_lesson)}</span>
                        </div>
                      )}
                    </div>
                    {/* Actionable row */}
                    <div className="grid grid-cols-2 gap-2">
                      {rv.what_if && (
                        <div className="bg-accent-yellow/10 rounded-lg p-3">
                          <span className="text-[10px] text-accent-yellow block mb-1">🔄 如果重来</span>
                          <span className="text-xs">{String(rv.what_if)}</span>
                        </div>
                      )}
                      {rv.reusable_rule && (
                        <div className="bg-purple-500/10 rounded-lg p-3">
                          <span className="text-[10px] text-purple-300 block mb-1">📌 可复用规则</span>
                          <span className="text-xs">{String(rv.reusable_rule)}</span>
                        </div>
                      )}
                    </div>
                    {/* Dimension scores */}
                    {dimReview && (
                      <div className="bg-white/5 rounded-lg p-3">
                        <h4 className="text-[10px] text-text-muted mb-2">各维度判断评估</h4>
                        <div className="grid grid-cols-3 gap-1 text-[11px]">
                          {Object.entries(dimReview).map(([k, v]) => (
                            <div key={k} className="flex justify-between py-0.5 border-b border-white/5">
                              <span className="text-text-muted">{k}</span>
                              <span className={`${String(v).includes("正确") || String(v).includes("有效") ? "text-accent-green" : String(v).includes("错误") || String(v).includes("误判") ? "text-accent-red" : ""}`}>{String(v).slice(0, 40)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Factor details (collapsible) */}
                    {reviews.length > 0 && (
                      <details><summary className="text-xs text-accent-blue cursor-pointer font-semibold">查看 {reviews.length} 个因子详细归因</summary>
                        <div className="mt-2 space-y-1">
                          {reviews.map((r, i) => (
                            <div key={i} className={`p-2 rounded text-xs border ${r.verdict?.includes("✅") ? "border-accent-green/20 bg-accent-green/5" : r.verdict?.includes("❌") ? "border-accent-red/20 bg-accent-red/5" : "border-accent-yellow/20 bg-accent-yellow/5"}`}>
                              <div className="font-medium">{r.verdict} 因子{r.factor_index}: {r.original}</div>
                              <div className="text-text-muted mt-1">{r.explanation}</div>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                );
              })() : (
                <button onClick={() => reviewPos(pos.id)} disabled={reviewing}
                  className="px-4 py-2 bg-accent-blue/20 text-accent-blue rounded-lg text-sm font-semibold hover:bg-accent-blue/30 disabled:opacity-50">
                  {reviewing ? "🔬 9维复盘中..." : "🔬 生成9维深度复盘"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}