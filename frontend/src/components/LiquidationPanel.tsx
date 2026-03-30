"use client";

import { useState } from "react";
import type { LiquidationMap } from "@/lib/types";

function formatUSD(value: number): string {
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

export default function LiquidationPanel({ data }: { data: LiquidationMap[] }) {
  const [selected, setSelected] = useState(0);

  if (!data || data.length === 0) {
    return (
      <div className="bg-card-bg border border-card-border rounded-xl p-6 text-center text-text-muted">
        清算数据加载中...
      </div>
    );
  }

  const map = data[selected];
  const maxLiq = Math.max(...map.levels.map((l) => Math.max(l.long_liq_usd, l.short_liq_usd)), 1);

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-4">
      <h3 className="text-sm font-semibold mb-3">🔥 清算热力图</h3>

      {/* Symbol Selector */}
      <div className="flex gap-1 mb-3">
        {data.map((d, i) => (
          <button
            key={d.symbol}
            onClick={() => setSelected(i)}
            className={`px-2 py-1 text-xs rounded ${
              i === selected ? "bg-accent-blue text-white" : "bg-bg-primary text-text-muted hover:text-white"
            }`}
          >
            {d.symbol.replace("USDT", "")}
          </button>
        ))}
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="text-center bg-bg-primary rounded p-2">
          <div className="text-sm font-bold text-accent-green">{formatUSD(map.total_long_liq)}</div>
          <div className="text-xs text-text-muted">多头清算量</div>
        </div>
        <div className="text-center bg-bg-primary rounded p-2">
          <div className="text-sm font-bold text-accent-red">{formatUSD(map.total_short_liq)}</div>
          <div className="text-xs text-text-muted">空头清算量</div>
        </div>
      </div>

      {/* Heatmap Bars */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs text-text-muted mb-1">
          <span>当前价: ${map.current_price.toLocaleString()}</span>
        </div>
        {map.levels.map((level, i) => {
          const isAbove = level.price > map.current_price;
          const liqAmount = level.long_liq_usd || level.short_liq_usd;
          const pct = (liqAmount / maxLiq) * 100;
          const isLong = level.long_liq_usd > 0;
          return (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className="w-20 text-right text-text-muted">${level.price.toLocaleString()}</span>
              <div className="flex-1 h-3 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${isLong ? "bg-green-500/60" : "bg-red-500/60"}`}
                  style={{ width: `${Math.max(pct, 3)}%` }}
                />
              </div>
              <span className="w-12 text-xs text-text-muted">{level.leverage}</span>
              <span className={`w-16 text-right ${isLong ? "text-accent-green" : "text-accent-red"}`}>
                {formatUSD(liqAmount)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

