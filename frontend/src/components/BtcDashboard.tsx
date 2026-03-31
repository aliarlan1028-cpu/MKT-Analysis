"use client";

import { useEffect, useState } from "react";
import type { BtcDerivativesData } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

function fmt(n: number | null | undefined, d = 2): string {
  if (n == null) return "N/A";
  return n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function fmtUsd(n: number | null | undefined): string {
  if (n == null) return "N/A";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

const TREND_LABELS: Record<string, { text: string; color: string }> = {
  strong_bull: { text: "强势多头 🟢🟢", color: "text-accent-green" },
  bull: { text: "偏多 🟢", color: "text-accent-green" },
  neutral: { text: "震荡 ⚪", color: "text-text-muted" },
  bear: { text: "偏空 🔴", color: "text-accent-red" },
  strong_bear: { text: "强势空头 🔴🔴", color: "text-accent-red" },
};

export default function BtcDashboard() {
  const [data, setData] = useState<BtcDerivativesData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${API}/btc-derivatives`);
        if (res.ok) setData(await res.json());
      } catch { /* ignore */ }
      finally { setLoading(false); }
    };
    load();
    const iv = setInterval(load, 60000);
    return () => clearInterval(iv);
  }, []);

  if (loading) return <div className="text-text-muted text-sm py-4">BTC 衍生品数据加载中...</div>;
  if (!data) return null;

  const { core: c, technical: t, advanced: a } = data;
  const trendInfo = TREND_LABELS[t.ema_trend] || TREND_LABELS.neutral;

  // Volume profile bar max
  const vpMax = a.volume_profile ? Math.max(...a.volume_profile.map(l => l.volume)) : 1;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">📈 BTC 衍生品仪表盘</h2>

      {/* ── CORE + TECHNICAL (6 cards in one row) ── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Funding Rate */}
        <div className="bg-card-bg border border-card-border rounded-xl p-3">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-xs font-semibold text-text-muted">💰 资金费率</h3>
            <span className="text-xs text-text-muted" title="正费率=多头付费给空头；负费率反之">ⓘ</span>
          </div>
          <div className={`text-lg font-bold ${(c.funding_rate ?? 0) >= 0 ? "text-accent-green" : "text-accent-red"}`}>
            {c.funding_rate != null ? `${(c.funding_rate * 100).toFixed(4)}%` : "N/A"}
          </div>
          {c.next_funding_rate != null && (
            <p className="text-xs text-text-muted mt-0.5">
              预测: <span className={(c.next_funding_rate >= 0) ? "text-accent-green" : "text-accent-red"}>
                {(c.next_funding_rate * 100).toFixed(4)}%
              </span>
            </p>
          )}
          <p className="text-xs text-text-muted mt-1">
            {(c.funding_rate ?? 0) > 0.0003 ? "⚠️ 多头拥挤" :
             (c.funding_rate ?? 0) < -0.0003 ? "⚠️ 空头拥挤" :
             "✅ 正常"}
          </p>
        </div>

        {/* Open Interest */}
        <div className="bg-card-bg border border-card-border rounded-xl p-3">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-xs font-semibold text-text-muted">📊 持仓量</h3>
            <span className="text-xs text-text-muted" title="OI↑+价格↑=趋势确认；OI↓=平仓潮">ⓘ</span>
          </div>
          <div className="text-lg font-bold">{fmtUsd(c.oi_usd)}</div>
          <p className="text-xs text-text-muted">{fmt(c.oi_coin)} BTC</p>
          {c.oi_change_pct != null && (
            <p className={`text-xs font-mono mt-0.5 ${c.oi_change_pct >= 0 ? "text-accent-green" : "text-accent-red"}`}>
              24h: {c.oi_change_pct >= 0 ? "+" : ""}{c.oi_change_pct}%
            </p>
          )}
        </div>

        {/* Liquidations */}
        <div className="bg-card-bg border border-card-border rounded-xl p-3">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-xs font-semibold text-text-muted">💥 清算</h3>
            <span className="text-xs text-text-muted" title="多头清算多=可能到底；空头清算多=可能到顶">ⓘ</span>
          </div>
          <div className="space-y-0.5 text-xs">
            <div className="flex justify-between">
              <span className="text-accent-red">多头</span>
              <span className="font-mono">{fmtUsd(c.liq_long_usd)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-accent-green">空头</span>
              <span className="font-mono">{fmtUsd(c.liq_short_usd)}</span>
            </div>
          </div>
          <p className="text-xs text-text-muted mt-1">{c.liq_count}笔 {c.liq_ratio != null ? `| 比${c.liq_ratio}` : ""}</p>
        </div>

        {/* EMA Trend */}
        <div className="bg-card-bg border border-card-border rounded-xl p-3">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-xs font-semibold text-text-muted">📐 EMA趋势</h3>
            <span className="text-xs text-text-muted" title="价格>EMA21>55>200=强多头排列">ⓘ</span>
          </div>
          <div className={`text-sm font-bold ${trendInfo.color}`}>{trendInfo.text}</div>
          <div className="grid grid-cols-3 gap-1 mt-1 text-xs">
            <div><span className="text-text-muted">21</span><p className="font-mono">${fmt(t.ema_21, 0)}</p></div>
            <div><span className="text-text-muted">55</span><p className="font-mono">${fmt(t.ema_55, 0)}</p></div>
            <div><span className="text-text-muted">200</span><p className="font-mono">${fmt(t.ema_200, 0)}</p></div>
          </div>
        </div>

        {/* RSI */}
        <div className="bg-card-bg border border-card-border rounded-xl p-3">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-xs font-semibold text-text-muted">📉 RSI</h3>
            <span className="text-xs text-text-muted" title="RSI>70超买，<30超卖">ⓘ</span>
          </div>
          <div className={`text-lg font-bold ${
            (t.rsi ?? 50) > 70 ? "text-accent-red" :
            (t.rsi ?? 50) < 30 ? "text-accent-green" : ""
          }`}>
            {t.rsi ?? "N/A"}
          </div>
          <div className="w-full bg-gray-700 rounded-full h-1.5 mt-1">
            <div className="h-1.5 rounded-full" style={{
              width: `${Math.min(t.rsi ?? 50, 100)}%`,
              background: (t.rsi ?? 50) > 70 ? "#ef4444" : (t.rsi ?? 50) < 30 ? "#22c55e" : "#3b82f6"
            }} />
          </div>
          {t.rsi_divergence && (
            <p className={`text-xs font-semibold mt-1 ${t.rsi_divergence === "bullish" ? "text-accent-green" : "text-accent-red"}`}>
              ⚡ {t.rsi_divergence === "bullish" ? "看涨背离" : "看跌背离"}
            </p>
          )}
        </div>

        {/* ATR Stop-Loss */}
        <div className="bg-card-bg border border-card-border rounded-xl p-3">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-xs font-semibold text-text-muted">🛡️ ATR止损</h3>
            <span className="text-xs text-text-muted" title="1.5x ATR 止损，3x ATR 止盈">ⓘ</span>
          </div>
          <p className="text-xs text-text-muted">ATR=${fmt(t.atr, 0)}</p>
          <div className="space-y-1 mt-1">
            <div className="bg-accent-green/10 rounded p-1.5">
              <p className="text-xs text-accent-green font-semibold">📈 多</p>
              <div className="flex justify-between text-xs">
                <span className="text-text-muted">SL</span><span className="font-mono text-accent-red">${fmt(t.long_stop_loss, 0)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-text-muted">TP</span><span className="font-mono text-accent-green">${fmt(t.long_take_profit, 0)}</span>
              </div>
            </div>
            <div className="bg-accent-red/10 rounded p-1.5">
              <p className="text-xs text-accent-red font-semibold">📉 空</p>
              <div className="flex justify-between text-xs">
                <span className="text-text-muted">SL</span><span className="font-mono text-accent-red">${fmt(t.short_stop_loss, 0)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-text-muted">TP</span><span className="font-mono text-accent-green">${fmt(t.short_take_profit, 0)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── ADVANCED ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* CVD */}
        <div className="bg-card-bg border border-card-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-text-muted">🌊 CVD 累积量差</h3>
            <span className="text-xs text-text-muted" title="CVD上升=买方主导(吸筹)，CVD下降=卖方主导(派发)">ⓘ</span>
          </div>
          <div className={`text-xl font-bold ${a.cvd_trend === "accumulation" ? "text-accent-green" : "text-accent-red"}`}>
            {a.cvd_trend === "accumulation" ? "🟢 吸筹中" : "🔴 派发中"}
          </div>
          <p className="text-sm font-mono mt-1">
            24h变化: <span className={a.cvd_24h_change >= 0 ? "text-accent-green" : "text-accent-red"}>
              {a.cvd_24h_change >= 0 ? "+" : ""}{fmt(a.cvd_24h_change, 0)}
            </span>
          </p>
          <p className="text-xs text-text-muted mt-2 leading-relaxed">
            {a.cvd_trend === "accumulation"
              ? "买方持续吸筹，配合价格上涨可确认趋势"
              : "卖方主导派发，配合价格下跌需警惕"}
          </p>
        </div>

        {/* Volume Profile */}
        <div className="bg-card-bg border border-card-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-text-muted">📊 成交量分布</h3>
            <span className="text-xs text-text-muted" title="POC=最大成交量价格(强支撑/阻力)；VAH/VAL=价值区间">ⓘ</span>
          </div>
          {a.poc_price && (
            <div className="grid grid-cols-3 gap-2 text-xs mb-3">
              <div className="bg-accent-blue/10 rounded p-1.5 text-center">
                <span className="text-text-muted block">POC</span>
                <span className="font-mono font-bold">${fmt(a.poc_price, 0)}</span>
              </div>
              <div className="bg-accent-green/10 rounded p-1.5 text-center">
                <span className="text-text-muted block">VAH</span>
                <span className="font-mono">${fmt(a.value_area_high, 0)}</span>
              </div>
              <div className="bg-accent-red/10 rounded p-1.5 text-center">
                <span className="text-text-muted block">VAL</span>
                <span className="font-mono">${fmt(a.value_area_low, 0)}</span>
              </div>
            </div>
          )}
          {/* Mini volume profile chart */}
          <div className="space-y-0.5">
            {a.volume_profile?.slice(-10).map((l, i) => (
              <div key={i} className="flex items-center gap-1 text-xs">
                <span className="w-16 text-right font-mono text-text-muted">${fmt(l.price, 0)}</span>
                <div className="flex-1 bg-gray-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${
                      a.poc_price && Math.abs(l.price - a.poc_price) < 100 ? "bg-accent-yellow" : "bg-accent-blue/60"
                    }`}
                    style={{ width: `${(l.volume / vpMax) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Usage Guide ── */}
      <div className="bg-card-bg border border-card-border rounded-xl p-4">
        <h3 className="text-sm font-semibold mb-2">🧭 组合使用指南</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-text-muted leading-relaxed">
          <div>
            <p className="text-white font-semibold mb-1">🟢 做多信号确认</p>
            <p>资金费率为负 + OI上升 + EMA多头排列 + RSI看涨背离 + CVD吸筹 → 高概率做多</p>
          </div>
          <div>
            <p className="text-white font-semibold mb-1">🔴 做空信号确认</p>
            <p>费率极高 + 大量多头清算 + EMA空头排列 + RSI看跌背离 + CVD派发 → 高概率做空</p>
          </div>
          <div>
            <p className="text-white font-semibold mb-1">⚡ 关键支撑/阻力</p>
            <p>POC价格为最强支撑/阻力；VAH上方突破看涨，VAL下方跌破看跌；ATR止损控制风险</p>
          </div>
        </div>
      </div>
    </div>
  );
}

