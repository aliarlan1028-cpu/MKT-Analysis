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

interface Position {
  id: number; coin: string; direction: string; status: string;
  leverage: number; margin: number; entry_price: number | null;
  target_entry_price: number; stop_loss: number;
  take_profit_1: number; take_profit_2: number | null;
  exit_price: number | null; pnl: number | null; pnl_pct: number | null;
  mae: number; mfe: number; factors: { description: string; bias: string }[];
  factor_review: Record<string, unknown> | null;
  events?: { timestamp: string; event_type: string; price: number; ai_analysis?: string; change_pct?: number }[];
  opened_at: string | null; closed_at: string | null; created_at: string;
}

interface AnalysisResult {
  coin: string; timestamp: string;
  step1?: Record<string, unknown>; step2?: Record<string, unknown>;
  step3?: Record<string, unknown>; step4?: Record<string, unknown>;
  market_data?: Record<string, unknown>;
}

export default function SimPage() {
  const [account, setAccount] = useState<Account | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [allSymbols, setAllSymbols] = useState<string[]>([]);
  const [selectedCoin, setSelectedCoin] = useState<string>("");
  const [coinSearch, setCoinSearch] = useState("");
  const [showCoinPicker, setShowCoinPicker] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [openingPosition, setOpeningPosition] = useState(false);
  const [klines, setKlines] = useState<unknown[]>([]);
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [livePrice, setLivePrice] = useState<Record<string, number>>({});
  const pickerRef = useRef<HTMLDivElement>(null);

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      const [accRes, posRes] = await Promise.all([
        fetch(`${API}/sim/account`), fetch(`${API}/sim/positions`),
      ]);
      if (accRes.ok) setAccount(await accRes.json());
      if (posRes.ok) setPositions(await posRes.json());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchData();
    fetch(`${API}/derivatives/symbols`).then(r => r.ok ? r.json() : [])
      .then((data: Array<{ ccy?: string } | string>) => {
        setAllSymbols(data.map((d) => typeof d === "string" ? d : (d.ccy || "")).filter(Boolean));
      }).catch(() => {});
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Close picker on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setShowCoinPicker(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Live prices for open positions
  useEffect(() => {
    const openPos = positions.filter(p => p.status === "OPEN" || p.status === "PENDING");
    if (!openPos.length) return;
    const fetchPrices = async () => {
      const prices: Record<string, number> = {};
      await Promise.allSettled(openPos.map(async (p) => {
        try {
          const r = await fetch(`${API}/market/okx/${p.coin}`);
          if (r.ok) { const d = await r.json(); prices[p.coin] = d.price; }
        } catch { /* ignore */ }
      }));
      setLivePrice(prices);
    };
    fetchPrices();
    const interval = setInterval(fetchPrices, 10000);
    return () => clearInterval(interval);
  }, [positions]);

  // Fetch klines when coin selected
  useEffect(() => {
    const coin = selectedPosition?.coin || selectedCoin;
    if (!coin) return;
    fetch(`${API}/sim/klines/${coin}?bar=5m&limit=200`).then(r => r.ok ? r.json() : []).then(setKlines).catch(() => {});
  }, [selectedCoin, selectedPosition]);

  // Run analysis
  const runAnalysis = async () => {
    if (!selectedCoin) return;
    setAnalyzing(true); setAnalysis(null); setCurrentStep(1);
    try {
      const res = await fetch(`${API}/sim/analyze/${selectedCoin}`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setAnalysis(data);
        setCurrentStep(data.step4 ? 4 : data.step3 ? 3 : data.step2 ? 2 : 1);
      }
    } catch { /* ignore */ }
    setAnalyzing(false);
  };

  // Open position
  const confirmOpen = async () => {
    if (!analysis?.step4 || !analysis.step3) return;
    const s4 = analysis.step4 as Record<string, unknown>;
    if (s4.direction === "NONE") return;
    setOpeningPosition(true);
    try {
      const factors = ((analysis.step3 as Record<string, unknown>).factors as { description: string; bias: string }[]) || [];
      const res = await fetch(`${API}/sim/open`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          coin: selectedCoin, direction: s4.direction,
          entry_price: s4.entry_price, stop_loss: s4.stop_loss,
          take_profit_1: s4.take_profit_1, take_profit_2: s4.take_profit_2,
          factors,
        }),
      });
      if (res.ok) { fetchData(); setAnalysis(null); setSelectedCoin(""); }
    } catch { /* ignore */ }
    setOpeningPosition(false);
  };

  // Close position
  const closePos = async (id: number) => {
    await fetch(`${API}/sim/close/${id}`, { method: "POST" });
    fetchData();
  };

  // Review
  const reviewPos = async (id: number) => {
    setReviewing(true);
    const res = await fetch(`${API}/sim/review/${id}`, { method: "POST" });
    if (res.ok) fetchData();
    setReviewing(false);
  };

  // Refund
  const doRefund = async () => {
    await fetch(`${API}/sim/refund`, { method: "POST" });
    fetchData();
  };

  const openPositions = positions.filter(p => p.status === "OPEN" || p.status === "PENDING");
  const closedPositions = positions.filter(p => p.status === "CLOSED" || p.status === "LIQUIDATED");

  return (
    <main className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold"><span className="text-accent-yellow">🎮</span> AI 模拟盘</h1>
          <p className="text-sm text-text-muted">Gemini 深度分析 · 自动跟踪 · 因子归因复盘</p>
        </div>
        <a href="/" className="text-sm text-accent-blue hover:underline">← 返回主面板</a>
      </header>

      {/* Account Bar */}
      {account && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6">
          <div className="bg-card-bg border border-card-border rounded-lg p-3 text-center">
            <div className="text-xs text-text-muted">账户余额</div>
            <div className="text-lg font-bold font-mono">${account.balance.toFixed(2)}</div>
          </div>
          <div className="bg-card-bg border border-card-border rounded-lg p-3 text-center">
            <div className="text-xs text-text-muted">已用保证金</div>
            <div className="text-lg font-bold font-mono">${account.used_margin.toFixed(2)}</div>
          </div>
          <div className="bg-card-bg border border-card-border rounded-lg p-3 text-center">
            <div className="text-xs text-text-muted">累计盈亏</div>
            <div className={`text-lg font-bold font-mono ${account.total_pnl >= 0 ? "text-accent-green" : "text-accent-red"}`}>
              {account.total_pnl >= 0 ? "+" : ""}{account.total_pnl.toFixed(2)}
            </div>
          </div>
          <div className="bg-card-bg border border-card-border rounded-lg p-3 text-center">
            <div className="text-xs text-text-muted">胜率</div>
            <div className="text-lg font-bold">{account.win_rate}%</div>
          </div>
          <div className="bg-card-bg border border-card-border rounded-lg p-3 text-center">
            <div className="text-xs text-text-muted">交易次数</div>
            <div className="text-lg font-bold">{account.wins}胜 {account.losses}负</div>
          </div>
          <div className="bg-card-bg border border-card-border rounded-lg p-3 flex items-center justify-center">
            {account.can_refund ? (
              <button onClick={doRefund} className="px-3 py-1.5 bg-accent-yellow/20 text-accent-yellow rounded-lg text-sm font-semibold hover:bg-accent-yellow/30">
                💰 申请补充资金
              </button>
            ) : (
              <span className="text-xs text-text-muted">余额充足</span>
            )}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT: Coin Selection & Analysis */}
        <div className="lg:col-span-3 space-y-4">
          {/* Coin Picker */}
          <div className="bg-card-bg border border-card-border rounded-xl p-4">
            <h3 className="text-sm font-semibold mb-3">🔎 选择币种分析</h3>
            <div className="relative" ref={pickerRef}>
              <button onClick={() => setShowCoinPicker(!showCoinPicker)}
                className="w-full px-3 py-2 bg-transparent border border-card-border rounded-lg text-left text-sm hover:border-accent-blue/40">
                {selectedCoin ? `${selectedCoin}/USDT` : "点击选择币种..."}
              </button>
              {showCoinPicker && (
                <div className="absolute top-full left-0 mt-1 w-full bg-card-bg border border-card-border rounded-lg shadow-xl z-50">
                  <input type="text" placeholder="搜索..." value={coinSearch}
                    onChange={(e) => setCoinSearch(e.target.value.toUpperCase())}
                    className="w-full px-3 py-2 bg-transparent border-b border-card-border text-sm outline-none" autoFocus />
                  <div className="max-h-48 overflow-y-auto">
                    {allSymbols.filter(s => s.includes(coinSearch)).slice(0, 30).map(s => (
                      <button key={s} onClick={() => { setSelectedCoin(s); setShowCoinPicker(false); setCoinSearch(""); }}
                        className="w-full text-left px-3 py-1.5 text-sm hover:bg-accent-blue/10">{s}/USDT</button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <button onClick={runAnalysis} disabled={!selectedCoin || analyzing}
              className="w-full mt-3 px-4 py-2 bg-accent-blue/20 text-accent-blue rounded-lg font-semibold text-sm hover:bg-accent-blue/30 disabled:opacity-50">
              {analyzing ? "🔬 分析中..." : "🔬 深度分析"}
            </button>
          </div>

          {/* Analysis Steps */}
          {(analyzing || analysis) && (
            <div className="bg-card-bg border border-card-border rounded-xl p-4 space-y-3">
              <h3 className="text-sm font-semibold">📊 分析进度</h3>
              {[
                { step: 1, label: "基本面扫描", key: "step1" },
                { step: 2, label: "分析策略选择", key: "step2" },
                { step: 3, label: "深度行情分析", key: "step3" },
                { step: 4, label: "交易决策", key: "step4" },
              ].map(({ step, label, key }) => {
                const done = analysis?.[key as keyof AnalysisResult];
                const active = analyzing && currentStep === step;
                return (
                  <div key={step} className={`p-2 rounded-lg border text-sm ${done ? "border-accent-green/30 bg-accent-green/5" : active ? "border-accent-blue/30 bg-accent-blue/5 animate-pulse" : "border-card-border opacity-50"}`}>
                    <span className="mr-2">{done ? "✅" : active ? "⏳" : "⬜"}</span>
                    Step {step}: {label}
                    {done && typeof done === "object" && !("error" in (done as Record<string, unknown>)) && (
                      <details className="mt-2"><summary className="text-xs text-accent-blue cursor-pointer">查看详情</summary>
                        <pre className="text-xs text-text-muted mt-1 whitespace-pre-wrap max-h-48 overflow-y-auto">
                          {JSON.stringify(done, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                );
              })}

              {/* Trade Decision Summary & Confirm */}
              {analysis?.step4 && (() => {
                const s4 = analysis.step4 as Record<string, unknown>;
                if (s4.direction === "NONE") return (
                  <div className="p-3 bg-accent-yellow/10 border border-accent-yellow/30 rounded-lg text-sm">
                    ⚠️ AI 不建议交易：{String(s4.reasoning || "")}
                  </div>
                );
                const isLong = s4.direction === "LONG";
                return (
                  <div className={`p-3 rounded-lg border ${isLong ? "bg-accent-green/10 border-accent-green/30" : "bg-accent-red/10 border-accent-red/30"}`}>
                    <div className="text-lg font-bold mb-1">{isLong ? "🟢 做多" : "🔴 做空"} <span className="text-sm font-normal">置信度 {String(s4.confidence)}%</span></div>
                    <div className="text-xs space-y-0.5 font-mono">
                      <div>入场: ${String(s4.entry_price)}</div>
                      <div>止损: ${String(s4.stop_loss)}</div>
                      <div>止盈1: ${String(s4.take_profit_1)} {s4.take_profit_2 ? `| 止盈2: $${String(s4.take_profit_2)}` : ""}</div>
                    </div>
                    <p className="text-xs text-text-muted mt-1">{String(s4.reasoning || "")}</p>
                    <button onClick={confirmOpen} disabled={openingPosition}
                      className={`w-full mt-2 py-2 rounded-lg font-semibold text-sm ${isLong ? "bg-accent-green/20 text-accent-green hover:bg-accent-green/30" : "bg-accent-red/20 text-accent-red hover:bg-accent-red/30"} disabled:opacity-50`}>
                      {openingPosition ? "开仓中..." : "✅ 确认开仓"}
                    </button>
                  </div>
                );
              })()}
            </div>
          )}
        </div>

        {/* CENTER: Chart + Active Positions */}
        <div className="lg:col-span-6 space-y-4">
          {/* Chart */}
          {(selectedCoin || selectedPosition) && klines.length > 0 && (
            <SimChart
              coin={selectedPosition?.coin || selectedCoin}
              klines={klines as any}
              entryPrice={selectedPosition?.entry_price || undefined}
              stopLoss={selectedPosition?.stop_loss}
              takeProfit1={selectedPosition?.take_profit_1}
              takeProfit2={selectedPosition?.take_profit_2 || undefined}
              events={selectedPosition?.events}
              direction={selectedPosition?.direction}
            />
          )}

          {/* Active Positions */}
          <div className="bg-card-bg border border-card-border rounded-xl p-4">
            <h3 className="text-sm font-semibold mb-3">📈 活跃持仓 ({openPositions.length}/{2})</h3>
            {openPositions.length === 0 ? (
              <p className="text-text-muted text-sm text-center py-4">暂无持仓，选择币种开始分析</p>
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
                <div key={pos.id} onClick={() => setSelectedPosition(pos)}
                  className="border border-card-border rounded-lg p-3 mb-2 cursor-pointer hover:border-accent-blue/40">
                  <div className="flex justify-between items-center">
                    <div>
                      <span className="font-bold">{pos.coin}/USDT</span>
                      <span className={`ml-2 text-xs px-2 py-0.5 rounded ${pos.direction === "LONG" ? "bg-accent-green/20 text-accent-green" : "bg-accent-red/20 text-accent-red"}`}>
                        {pos.direction === "LONG" ? "做多" : "做空"} {pos.leverage}x
                      </span>
                      <span className={`ml-1 text-xs px-2 py-0.5 rounded ${pos.status === "OPEN" ? "bg-accent-blue/20 text-accent-blue" : "bg-accent-yellow/20 text-accent-yellow"}`}>
                        {pos.status === "OPEN" ? "持仓中" : "等待成交"}
                      </span>
                    </div>
                    <button onClick={(e) => { e.stopPropagation(); closePos(pos.id); }}
                      className="px-3 py-1 bg-accent-red/20 text-accent-red rounded text-xs hover:bg-accent-red/30">
                      {pos.status === "PENDING" ? "取消" : "平仓"}
                    </button>
                  </div>
                  <div className="grid grid-cols-4 gap-2 mt-2 text-xs">
                    <div><span className="text-text-muted">入场</span><div className="font-mono">${entry}</div></div>
                    <div><span className="text-text-muted">现价</span><div className="font-mono">${price?.toFixed(6) || "..."}</div></div>
                    <div><span className="text-text-muted">浮动盈亏</span>
                      <div className={`font-mono font-bold ${livePnl >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                        {pos.status === "OPEN" ? `${livePnl >= 0 ? "+" : ""}${livePnl.toFixed(2)}%` : "等待中"}
                      </div>
                    </div>
                    <div><span className="text-text-muted">保证金</span><div className="font-mono">${pos.margin.toFixed(2)}</div></div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT: Trade History */}
        <div className="lg:col-span-3 space-y-4">
          <div className="bg-card-bg border border-card-border rounded-xl p-4">
            <h3 className="text-sm font-semibold mb-3">📋 交易记录</h3>
            {closedPositions.length === 0 ? (
              <p className="text-text-muted text-sm text-center py-4">暂无历史交易</p>
            ) : (
              <div className="space-y-2 max-h-[500px] overflow-y-auto">
                {closedPositions.map(pos => (
                  <div key={pos.id} className="border border-card-border rounded-lg p-2 text-sm">
                    <div className="flex justify-between items-center">
                      <span className="font-medium">{pos.coin}
                        <span className={`ml-1 ${pos.direction === "LONG" ? "text-accent-green" : "text-accent-red"}`}>
                          {pos.direction === "LONG" ? "多" : "空"}
                        </span>
                      </span>
                      <span className={`font-mono font-bold ${(pos.pnl || 0) >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                        {(pos.pnl_pct || 0) >= 0 ? "+" : ""}{pos.pnl_pct?.toFixed(1)}% (${pos.pnl?.toFixed(2)})
                      </span>
                    </div>
                    <div className="text-xs text-text-muted mt-1">
                      MAE: {pos.mae?.toFixed(1)}% | MFE: {pos.mfe?.toFixed(1)}% | {pos.status === "LIQUIDATED" ? "💥 爆仓" : ""}
                    </div>
                    {pos.factor_review ? (
                      <details className="mt-1"><summary className="text-xs text-accent-blue cursor-pointer">查看复盘</summary>
                        <pre className="text-xs text-text-muted mt-1 whitespace-pre-wrap max-h-48 overflow-y-auto">
                          {JSON.stringify(pos.factor_review, null, 2)}
                        </pre>
                      </details>
                    ) : pos.status !== "PENDING" && (
                      <button onClick={() => reviewPos(pos.id)} disabled={reviewing}
                        className="mt-1 text-xs text-accent-blue hover:underline">
                        {reviewing ? "复盘中..." : "🔬 生成复盘"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
