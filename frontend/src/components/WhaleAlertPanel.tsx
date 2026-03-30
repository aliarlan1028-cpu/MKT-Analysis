"use client";

import type { WhaleAlertResponse } from "@/lib/types";

const txTypeLabels: Record<string, { label: string; color: string }> = {
  exchange_inflow: { label: "🔴 流入交易所", color: "text-accent-red" },
  exchange_outflow: { label: "🟢 流出交易所", color: "text-accent-green" },
  inter_exchange: { label: "🔄 交易所间", color: "text-accent-yellow" },
  transfer: { label: "📤 转账", color: "text-text-muted" },
};

function formatUSD(value: number): string {
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

export default function WhaleAlertPanel({ data }: { data: WhaleAlertResponse | null }) {
  if (!data) {
    return (
      <div className="bg-card-bg border border-card-border rounded-xl p-6 text-center text-text-muted">
        🐋 鲸鱼警报加载中...
      </div>
    );
  }

  const { summary } = data;
  const signalColor = summary.signal === "bullish" ? "text-accent-green" : summary.signal === "bearish" ? "text-accent-red" : "text-accent-yellow";

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-4">
      <h3 className="text-sm font-semibold mb-3">🐋 鲸鱼警报</h3>

      {/* Flow Summary */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="text-center bg-bg-primary rounded p-2">
          <div className="text-sm font-bold text-accent-red">{formatUSD(summary.total_inflow_usd)}</div>
          <div className="text-xs text-text-muted">流入交易所</div>
        </div>
        <div className="text-center bg-bg-primary rounded p-2">
          <div className="text-sm font-bold text-accent-green">{formatUSD(summary.total_outflow_usd)}</div>
          <div className="text-xs text-text-muted">流出交易所</div>
        </div>
        <div className="text-center bg-bg-primary rounded p-2">
          <div className={`text-sm font-bold ${signalColor}`}>
            {summary.net_flow >= 0 ? "+" : ""}{formatUSD(Math.abs(summary.net_flow))}
          </div>
          <div className="text-xs text-text-muted">净流向</div>
        </div>
      </div>

      {/* Signal Badge */}
      <div className={`text-center text-sm font-medium mb-3 ${signalColor}`}>
        信号: {summary.signal === "bullish" ? "📈 看多（资金流出交易所）" : summary.signal === "bearish" ? "📉 看空（资金流入交易所）" : "⚖️ 中性"}
      </div>

      {/* Transaction List */}
      {data.transactions.length === 0 ? (
        <p className="text-text-muted text-sm text-center py-2">暂无大额转账记录</p>
      ) : (
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {data.transactions.slice(0, 8).map((tx, i) => {
            const txInfo = txTypeLabels[tx.tx_type] || txTypeLabels.transfer;
            return (
              <div key={`${tx.hash}-${i}`} className="flex items-center justify-between text-xs border-b border-card-border pb-1">
                <span className={txInfo.color}>{txInfo.label}</span>
                <span className="text-text-muted">{tx.amount.toLocaleString()} {tx.symbol}</span>
                <span className="font-medium">{formatUSD(tx.amount_usd)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

