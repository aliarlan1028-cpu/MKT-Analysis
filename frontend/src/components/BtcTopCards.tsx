"use client";

import { useEffect, useState } from "react";
import type { BtcDerivativesData } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

function fmt(n: number | null | undefined, d = 2): string {
  if (n == null) return "N/A";
  return n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

const TREND_LABELS: Record<string, { text: string; color: string }> = {
  strong_bull: { text: "强势多头 🟢🟢", color: "text-accent-green" },
  bull: { text: "偏多 🟢", color: "text-accent-green" },
  neutral: { text: "震荡 ⚪", color: "text-text-muted" },
  bear: { text: "偏空 🔴", color: "text-accent-red" },
  strong_bear: { text: "强势空头 🔴🔴", color: "text-accent-red" },
};

export default function BtcTopCards() {
  const [data, setData] = useState<BtcDerivativesData | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${API}/btc-derivatives`);
        if (res.ok) setData(await res.json());
      } catch { /* ignore */ }
    };
    load();
    const iv = setInterval(load, 60000);
    return () => clearInterval(iv);
  }, []);

  if (!data) return null;

  const { technical: t, advanced: a } = data;
  const trendInfo = TREND_LABELS[t.ema_trend] || TREND_LABELS.neutral;

  return (
    <>
      {/* 📐 EMA 趋势 */}
      <div className="bg-card-bg border border-card-border rounded-xl p-5 hover:border-accent-blue/40 transition-colors">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-lg font-bold">📐 EMA趋势</h3>
            <span className="text-sm text-text-muted">BTC 4H</span>
          </div>
          <span className={`text-xs px-2 py-1 rounded ${
            t.ema_trend?.includes("bull") ? "bg-accent-green/10 text-accent-green" :
            t.ema_trend?.includes("bear") ? "bg-accent-red/10 text-accent-red" :
            "bg-gray-700 text-text-muted"
          }`}>
            {trendInfo.text}
          </span>
        </div>
        <div className={`text-2xl font-bold mb-4 ${trendInfo.color}`}>
          ${fmt(t.price, 0)}
        </div>
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <span className="text-text-muted">EMA 21</span>
            <p className="font-mono">${fmt(t.ema_21, 0)}</p>
          </div>
          <div>
            <span className="text-text-muted">EMA 55</span>
            <p className="font-mono">${fmt(t.ema_55, 0)}</p>
          </div>
          <div>
            <span className="text-text-muted">EMA 200</span>
            <p className="font-mono">${fmt(t.ema_200, 0)}</p>
          </div>
        </div>
      </div>

      {/* 🛡️ ATR 止损 */}
      <div className="bg-card-bg border border-card-border rounded-xl p-5 hover:border-accent-blue/40 transition-colors">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-lg font-bold">🛡️ ATR止损</h3>
            <span className="text-sm text-text-muted">波动率止损止盈</span>
          </div>
          <span className="text-xs px-2 py-1 rounded bg-accent-blue/10 text-accent-blue">
            ATR ${fmt(t.atr, 0)}
          </span>
        </div>
        <div className="space-y-3">
          <div className="bg-accent-green/5 border border-accent-green/20 rounded-lg p-3">
            <p className="text-sm text-accent-green font-semibold mb-2">📈 做多</p>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-text-muted">止损</span>
                <p className="font-mono text-accent-red">${fmt(t.long_stop_loss, 0)}</p>
              </div>
              <div>
                <span className="text-text-muted">止盈</span>
                <p className="font-mono text-accent-green">${fmt(t.long_take_profit, 0)}</p>
              </div>
            </div>
          </div>
          <div className="bg-accent-red/5 border border-accent-red/20 rounded-lg p-3">
            <p className="text-sm text-accent-red font-semibold mb-2">📉 做空</p>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-text-muted">止损</span>
                <p className="font-mono text-accent-red">${fmt(t.short_stop_loss, 0)}</p>
              </div>
              <div>
                <span className="text-text-muted">止盈</span>
                <p className="font-mono text-accent-green">${fmt(t.short_take_profit, 0)}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 🌊 CVD 累积量差 */}
      <div className="bg-card-bg border border-card-border rounded-xl p-5 hover:border-accent-blue/40 transition-colors">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-lg font-bold">🌊 CVD</h3>
            <span className="text-sm text-text-muted">累积量差</span>
          </div>
          <span className={`text-xs px-2 py-1 rounded ${
            a.cvd_trend === "accumulation" ? "bg-accent-green/10 text-accent-green" : "bg-accent-red/10 text-accent-red"
          }`}>
            {a.cvd_trend === "accumulation" ? "🟢 吸筹" : "🔴 派发"}
          </span>
        </div>
        <div className={`text-2xl font-bold mb-4 ${a.cvd_trend === "accumulation" ? "text-accent-green" : "text-accent-red"}`}>
          {a.cvd_trend === "accumulation" ? "买方主导" : "卖方主导"}
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-text-muted">24h变化</span>
            <p className={`font-mono ${a.cvd_24h_change >= 0 ? "text-accent-green" : "text-accent-red"}`}>
              {a.cvd_24h_change >= 0 ? "+" : ""}{fmt(a.cvd_24h_change, 0)}
            </p>
          </div>
          <div>
            <span className="text-text-muted">状态</span>
            <p className="text-sm">{a.cvd_trend === "accumulation" ? "持续吸筹中" : "派发出货中"}</p>
          </div>
        </div>
      </div>
    </>
  );
}

