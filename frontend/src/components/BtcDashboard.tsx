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


interface Props {
  symbol?: string;
}

export default function BtcDashboard({ symbol = "BTC" }: Props) {
  const [data, setData] = useState<BtcDerivativesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${API}/derivatives/${symbol}`);
        if (res.ok) setData(await res.json());
      } catch { /* ignore */ }
      finally { setLoading(false); }
    };
    load();
    const iv = setInterval(load, 60000);
    return () => clearInterval(iv);
  }, [symbol]);

  if (loading) return <div className="text-text-muted text-sm py-4">{symbol} 衍生品数据加载中...</div>;
  if (!data) return null;

  const { core: c, technical: t, advanced: a } = data;

  // Volume profile bar max
  const vpMax = a.volume_profile ? Math.max(...a.volume_profile.map(l => l.volume)) : 1;

  return (
    <div>
      {/* Toggle button */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-text-muted hover:text-white transition-colors mb-3"
      >
        <span>{expanded ? "▲ 收起衍生品详情" : "▼ 展开衍生品详情"}</span>
      </button>

      {expanded && (
        <div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
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
              <p className="text-xs text-text-muted">{fmt(c.oi_coin)} {symbol}</p>
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

            {/* Volume Profile */}
            <div className="bg-card-bg border border-card-border rounded-xl p-3">
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-xs font-semibold text-text-muted">📊 成交量分布</h3>
                <span className="text-xs text-text-muted" title="POC=最大成交量价格">ⓘ</span>
              </div>
              {a.poc_price && (
                <div className="grid grid-cols-3 gap-1 text-xs mb-2">
                  <div className="bg-accent-blue/10 rounded p-1 text-center">
                    <span className="text-text-muted block text-[10px]">POC</span>
                    <span className="font-mono font-bold">${fmt(a.poc_price, 0)}</span>
                  </div>
                  <div className="bg-accent-green/10 rounded p-1 text-center">
                    <span className="text-text-muted block text-[10px]">VAH</span>
                    <span className="font-mono">${fmt(a.value_area_high, 0)}</span>
                  </div>
                  <div className="bg-accent-red/10 rounded p-1 text-center">
                    <span className="text-text-muted block text-[10px]">VAL</span>
                    <span className="font-mono">${fmt(a.value_area_low, 0)}</span>
                  </div>
                </div>
              )}
              <div className="space-y-0.5">
                {a.volume_profile?.slice(-6).map((l, i) => (
                  <div key={i} className="flex items-center gap-1 text-xs">
                    <span className="w-14 text-right font-mono text-text-muted text-[10px]">${fmt(l.price, 0)}</span>
                    <div className="flex-1 bg-gray-700 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full ${
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

        </div>
      )}
    </div>
  );
}

