"use client";

import type { MarketData } from "@/lib/types";

function formatPrice(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatVolume(n: number) {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

export default function MarketCard({ data, onRemove }: { data: MarketData; onRemove?: () => void }) {
  const isUp = data.price_change_pct_24h >= 0;
  const color = isUp ? "text-accent-green" : "text-accent-red";
  const arrow = isUp ? "▲" : "▼";

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-5 hover:border-accent-blue/40 transition-colors relative group">
      {onRemove && (
        <button
          onClick={onRemove}
          className="absolute top-2 right-2 w-5 h-5 flex items-center justify-center rounded-full bg-accent-red/20 text-accent-red text-xs opacity-0 group-hover:opacity-100 transition-opacity hover:bg-accent-red/40"
          title="移除"
        >✕</button>
      )}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-lg font-bold">{data.name}</h3>
          <span className="text-sm text-text-muted">{data.symbol}</span>
        </div>
        <span className={`text-xs px-2 py-1 rounded ${isUp ? "bg-accent-green/10 text-accent-green" : "bg-accent-red/10 text-accent-red"}`}>
          {arrow} {Math.abs(data.price_change_pct_24h)}%
        </span>
      </div>

      <div className={`text-2xl font-bold mb-4 ${color}`}>
        ${formatPrice(data.price)}
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="text-text-muted">24h 最高</span>
          <p className="font-mono">${formatPrice(data.high_24h)}</p>
        </div>
        <div>
          <span className="text-text-muted">24h 最低</span>
          <p className="font-mono">${formatPrice(data.low_24h)}</p>
        </div>
        <div>
          <span className="text-text-muted">成交量</span>
          <p className="font-mono">{formatVolume(data.volume_24h)}</p>
        </div>
        <div>
          <span className="text-text-muted">资金费率</span>
          <p className={`font-mono ${(data.funding_rate ?? 0) >= 0 ? "text-accent-green" : "text-accent-red"}`}>
            {data.funding_rate != null ? `${(data.funding_rate * 100).toFixed(4)}%` : "N/A"}
          </p>
        </div>
        {data.long_short_ratio != null && (
          <div>
            <span className="text-text-muted">多空比</span>
            <p className="font-mono">{data.long_short_ratio.toFixed(2)}</p>
          </div>
        )}
        {data.open_interest_change_pct != null && (
          <div>
            <span className="text-text-muted">OI变化</span>
            <p className={`font-mono ${data.open_interest_change_pct >= 0 ? "text-accent-green" : "text-accent-red"}`}>
              {data.open_interest_change_pct >= 0 ? "+" : ""}{data.open_interest_change_pct}%
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

