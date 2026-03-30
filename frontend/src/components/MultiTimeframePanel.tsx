"use client";

import type { MultiTimeframe } from "@/lib/types";

const directionColors: Record<string, string> = {
  LONG: "text-accent-green",
  SHORT: "text-accent-red",
  NEUTRAL: "text-accent-yellow",
  STRONG_LONG: "text-accent-green",
  STRONG_SHORT: "text-accent-red",
};

const directionLabels: Record<string, string> = {
  LONG: "📈 做多",
  SHORT: "📉 做空",
  NEUTRAL: "⚖️ 中性",
  STRONG_LONG: "🚀 强烈做多",
  STRONG_SHORT: "💥 强烈做空",
};

export default function MultiTimeframePanel({ data }: { data: MultiTimeframe[] }) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-card-bg border border-card-border rounded-xl p-6 text-center text-text-muted">
        多时间框架数据加载中...
      </div>
    );
  }

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-4">
      <h3 className="text-sm font-semibold mb-3">🕐 多时间框架分析</h3>
      <div className="space-y-3">
        {data.map((item) => (
          <div key={item.symbol} className="border border-card-border rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium">{item.name}</span>
              <span className={`text-sm font-bold ${directionColors[item.consensus] || "text-text-muted"}`}>
                {directionLabels[item.consensus] || item.consensus}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {item.timeframes.map((tf) => (
                <div key={tf.timeframe} className="text-center bg-bg-primary rounded p-2">
                  <div className="text-xs text-text-muted mb-1">{tf.timeframe.toUpperCase()}</div>
                  <div className={`text-sm font-bold ${directionColors[tf.direction] || ""}`}>
                    {tf.direction}
                  </div>
                  <div className="text-xs text-text-muted mt-1">
                    {tf.rsi !== null && <span>RSI: {tf.rsi?.toFixed(1)}</span>}
                  </div>
                  {/* Strength bar */}
                  <div className="mt-1 h-1 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        tf.direction === "LONG" ? "bg-accent-green" : tf.direction === "SHORT" ? "bg-accent-red" : "bg-accent-yellow"
                      }`}
                      style={{ width: `${tf.strength}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

