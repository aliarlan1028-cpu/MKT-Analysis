"use client";

import type { PostMortem, WinRateStats } from "@/lib/types";

const resultColors: Record<string, string> = {
  WIN: "text-accent-green",
  LOSS: "text-accent-red",
  BREAKEVEN: "text-accent-yellow",
  NEUTRAL: "text-text-muted",
};

const resultIcons: Record<string, string> = {
  WIN: "✅",
  LOSS: "❌",
  BREAKEVEN: "⚪",
  NEUTRAL: "➖",
};

export default function PostMortemPanel({
  postmortems,
  winRate,
}: {
  postmortems: PostMortem[];
  winRate: WinRateStats;
}) {
  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-4">
      <h3 className="text-sm font-semibold mb-3">📊 信号复盘</h3>

      {/* Win Rate Stats */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        <div className="text-center bg-bg-primary rounded p-2">
          <div className="text-lg font-bold text-accent-blue">{winRate.win_rate}%</div>
          <div className="text-xs text-text-muted">胜率</div>
        </div>
        <div className="text-center bg-bg-primary rounded p-2">
          <div className="text-lg font-bold text-accent-green">{winRate.wins}</div>
          <div className="text-xs text-text-muted">盈利</div>
        </div>
        <div className="text-center bg-bg-primary rounded p-2">
          <div className="text-lg font-bold text-accent-red">{winRate.losses}</div>
          <div className="text-xs text-text-muted">亏损</div>
        </div>
        <div className="text-center bg-bg-primary rounded p-2">
          <div className={`text-lg font-bold ${winRate.total_pnl_pct >= 0 ? "text-accent-green" : "text-accent-red"}`}>
            {winRate.total_pnl_pct >= 0 ? "+" : ""}{winRate.total_pnl_pct}%
          </div>
          <div className="text-xs text-text-muted">累计PnL</div>
        </div>
      </div>

      {/* Recent Post-Mortems */}
      {postmortems.length === 0 ? (
        <p className="text-text-muted text-sm text-center py-4">暂无复盘数据，等待信号过期后自动评估</p>
      ) : (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {postmortems.map((pm) => (
            <div key={pm.report_id} className="border border-card-border rounded-lg p-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">
                  {pm.name}{" "}
                  <span className={pm.direction === "LONG" ? "text-accent-green" : "text-accent-red"}>
                    {pm.direction}
                  </span>
                </span>
                <span className={resultColors[pm.result]}>
                  {resultIcons[pm.result]} {pm.pnl_pct >= 0 ? "+" : ""}{pm.pnl_pct}%
                </span>
              </div>
              <div className="text-xs text-text-muted mt-1">
                入场 ${pm.entry_zone[0]?.toLocaleString()} → 到期 ${pm.price_at_expiry?.toLocaleString()}
                {pm.hit_tp > 0 && <span className="text-accent-green ml-2">TP{pm.hit_tp} ✓</span>}
                {pm.hit_sl && <span className="text-accent-red ml-2">SL ✗</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

