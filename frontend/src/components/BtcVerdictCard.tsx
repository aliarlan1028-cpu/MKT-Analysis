"use client";

import { useEffect, useState } from "react";
import type { BtcVerdict } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

function fmt(n: number | null | undefined, d = 0): string {
  if (n == null) return "N/A";
  return n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

const DIR_STYLES: Record<string, { bg: string; border: string; glow: string }> = {
  bullish:  { bg: "bg-accent-green/5",  border: "border-accent-green/40", glow: "shadow-accent-green/10" },
  bearish:  { bg: "bg-accent-red/5",    border: "border-accent-red/40",   glow: "shadow-accent-red/10" },
  neutral:  { bg: "bg-card-bg",         border: "border-card-border",     glow: "" },
};

export default function BtcVerdictCard() {
  const [verdict, setVerdict] = useState<BtcVerdict | null>(null);
  const [ts, setTs] = useState<string>("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${API}/btc-derivatives`);
        if (res.ok) {
          const data = await res.json();
          setVerdict(data.verdict);
          setTs(data.timestamp);
        }
      } catch { /* ignore */ }
    };
    load();
    const iv = setInterval(load, 60000);
    return () => clearInterval(iv);
  }, []);

  if (!verdict) {
    return (
      <div className="bg-card-bg border border-card-border rounded-xl p-4">
        <p className="text-text-muted text-sm">🤖 AI 研判加载中...</p>
      </div>
    );
  }

  const style = DIR_STYLES[verdict.direction] || DIR_STYLES.neutral;
  const strengthLabel = verdict.strength === "strong" ? "强" : verdict.strength === "moderate" ? "中" : "弱";

  return (
    <div className={`${style.bg} border ${style.border} rounded-xl p-4 shadow-lg ${style.glow}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold">🤖 AI 综合研判</h3>
        {ts && (
          <span className="text-xs text-text-muted">
            {new Date(ts).toLocaleTimeString("zh-CN", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Direction + Score */}
        <div>
          <div className="text-2xl font-bold mb-1">{verdict.direction_cn}</div>
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span>综合评分: <span className="font-mono font-bold">{verdict.score > 0 ? "+" : ""}{verdict.score}</span></span>
            <span>| 信号强度: {strengthLabel}</span>
          </div>
          <p className="text-sm mt-2 leading-relaxed">{verdict.summary}</p>
        </div>

        {/* Signals */}
        <div>
          <p className="text-xs text-text-muted font-semibold mb-1">📡 信号明细</p>
          <div className="flex flex-wrap gap-1">
            {verdict.signals.map((s, i) => (
              <span key={i} className={`text-xs px-2 py-0.5 rounded-full ${
                s.includes("多") || s.includes("涨") || s.includes("吸筹") || s.includes("超卖") || s.includes("利多")
                  ? "bg-accent-green/15 text-accent-green"
                  : s.includes("空") || s.includes("跌") || s.includes("派发") || s.includes("超买") || s.includes("利空")
                  ? "bg-accent-red/15 text-accent-red"
                  : "bg-gray-700 text-text-muted"
              }`}>
                {s}
              </span>
            ))}
          </div>
        </div>

        {/* Key Levels */}
        <div>
          <p className="text-xs text-text-muted font-semibold mb-1">📍 关键价位 (当前 ${fmt(verdict.price)})</p>
          <div className="space-y-0.5">
            {verdict.key_levels.map((l, i) => (
              <div key={i} className="flex justify-between text-xs">
                <span className={`${
                  l.label.includes("止盈") || l.label.includes("支撑") ? "text-accent-green" :
                  l.label.includes("止损") || l.label.includes("阻力") ? "text-accent-red" :
                  "text-accent-blue"
                }`}>{l.label}</span>
                <span className="font-mono">${fmt(l.price)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

