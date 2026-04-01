"use client";

import type { PumpScannerResult, PumpCandidate } from "@/lib/types";

function scoreColor(score: number): string {
  if (score >= 70) return "text-accent-green";
  if (score >= 50) return "text-accent-yellow";
  if (score >= 30) return "text-orange-400";
  return "text-text-muted";
}

function scoreBar(score: number, color: string): React.ReactElement {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-bg-primary rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(score, 100)}%` }} />
      </div>
      <span className={`text-xs font-bold min-w-[32px] text-right ${score >= 60 ? "text-white" : "text-text-muted"}`}>
        {score}
      </span>
    </div>
  );
}

function CoinRow({ c, type }: { c: PumpCandidate; type: "pump" | "dump" }) {
  const isPump = type === "pump";
  const barColor = isPump ? "bg-accent-green" : "bg-accent-red";
  const fr = c.funding_rate != null ? (c.funding_rate * 100).toFixed(4) + "%" : "N/A";
  const frColor =
    c.funding_rate != null
      ? c.funding_rate > 0.0005
        ? "text-accent-red"
        : c.funding_rate > 0.0001
          ? "text-accent-yellow"
          : "text-accent-green"
      : "text-text-muted";

  return (
    <div className="border border-card-border rounded-lg p-3 hover:border-accent-blue/40 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-bold text-sm">{c.coin}</span>
          <span className="text-xs text-text-muted">${c.price}</span>
          <span className={`text-xs font-medium ${c.change_pct_24h >= 0 ? "text-accent-green" : "text-accent-red"}`}>
            {c.change_pct_24h >= 0 ? "+" : ""}{c.change_pct_24h.toFixed(2)}%
          </span>
        </div>
        <span className={`text-sm font-bold ${scoreColor(c.score)}`}>
          {isPump ? "🟢" : "🔴"} {c.score}分
        </span>
      </div>

      {scoreBar(c.score, barColor)}

      <div className="grid grid-cols-3 gap-2 mt-2 text-xs text-text-muted">
        <div>
          <span className="block text-[10px] opacity-60">资金费率</span>
          <span className={frColor}>{fr}</span>
        </div>
        <div>
          <span className="block text-[10px] opacity-60">RSI</span>
          <span className={c.rsi != null ? (c.rsi > 70 ? "text-accent-red" : c.rsi < 30 ? "text-accent-green" : "text-white") : ""}>
            {c.rsi != null ? c.rsi.toFixed(1) : "N/A"}
          </span>
        </div>
        <div>
          <span className="block text-[10px] opacity-60">7日涨幅</span>
          <span className={c.cumulative_return_7d > 10 ? "text-accent-yellow" : "text-white"}>
            {c.cumulative_return_7d.toFixed(1)}%
          </span>
        </div>
        <div>
          <span className="block text-[10px] opacity-60">量比</span>
          <span className={c.volume_ratio != null && c.volume_ratio > 2 ? "text-accent-green" : "text-white"}>
            {c.volume_ratio != null ? c.volume_ratio.toFixed(2) + "x" : "N/A"}
          </span>
        </div>
        <div>
          <span className="block text-[10px] opacity-60">EMA偏离</span>
          <span className={c.ema_deviation_pct > 15 ? "text-accent-red" : "text-white"}>
            {c.ema_deviation_pct.toFixed(1)}%
          </span>
        </div>
        <div>
          <span className="block text-[10px] opacity-60">连涨天数</span>
          <span>{c.consecutive_up_days}天</span>
        </div>
      </div>

      {/* Entry / SL / TP levels */}
      {c.entry_price != null && (
        <div className={`mt-2 p-2 rounded-md border ${isPump ? "border-accent-green/20 bg-accent-green/5" : "border-accent-red/20 bg-accent-red/5"}`}>
          <div className="text-[10px] font-semibold mb-1 opacity-70">
            {isPump ? "📈 做多点位" : "📉 做空点位"}
          </div>
          <div className="grid grid-cols-4 gap-1 text-[11px] font-mono">
            <div>
              <span className="block text-[9px] opacity-50">入场</span>
              <span className="text-accent-blue">${c.entry_price}</span>
            </div>
            <div>
              <span className="block text-[9px] opacity-50">止损</span>
              <span className="text-accent-red">${c.stop_loss}</span>
            </div>
            <div>
              <span className="block text-[9px] opacity-50">止盈1</span>
              <span className="text-accent-green">${c.take_profit_1}</span>
            </div>
            <div>
              <span className="block text-[9px] opacity-50">止盈2</span>
              <span className="text-accent-green">${c.take_profit_2}</span>
            </div>
          </div>
        </div>
      )}

      {/* DeepSeek AI Analysis */}
      {c.ai_analysis && typeof c.ai_analysis === "object" && "verdict" in c.ai_analysis && (
        <div className="mt-2 p-2 rounded-md border border-accent-blue/20 bg-accent-blue/5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-semibold opacity-70">🤖 DeepSeek 分析</span>
            <span className={`text-[10px] font-bold ${
              c.ai_analysis.verdict === "看涨" ? "text-accent-green" :
              c.ai_analysis.verdict === "看跌" ? "text-accent-red" : "text-accent-yellow"
            }`}>
              {c.ai_analysis.verdict}
              {c.ai_analysis.confidence != null && ` (${c.ai_analysis.confidence}%)`}
            </span>
          </div>
          {c.ai_analysis.reasoning && (
            <p className="text-[10px] text-text-muted leading-relaxed mb-1">{c.ai_analysis.reasoning}</p>
          )}
          {c.ai_analysis.market_style && (
            <p className="text-[10px] text-accent-yellow/80 mb-1">💡 做市风格: {c.ai_analysis.market_style}</p>
          )}
          {c.ai_analysis.historical_pattern && (
            <p className="text-[10px] text-purple-400/80 mb-1">📊 历史模式: {c.ai_analysis.historical_pattern}</p>
          )}
          {c.ai_analysis.continuation_signal && (
            <p className="text-[10px] text-orange-400/90 mb-1">🔥 持续信号: {c.ai_analysis.continuation_signal}</p>
          )}
          {c.ai_analysis.suggestion && (
            <p className="text-[10px] text-accent-blue/90 font-medium">📋 {c.ai_analysis.suggestion}</p>
          )}
          {c.ai_analysis.risk_warning && (
            <p className="text-[10px] text-accent-red/80 mt-1">⚠️ {c.ai_analysis.risk_warning}</p>
          )}
        </div>
      )}
      {c.ai_analysis && typeof c.ai_analysis === "string" && (
        <div className="mt-2 p-2 rounded-md border border-accent-blue/20 bg-accent-blue/5">
          <span className="text-[10px] font-semibold opacity-70">🤖 DeepSeek: </span>
          <span className="text-[10px] text-text-muted">{c.ai_analysis}</span>
        </div>
      )}

    </div>
  );
}

export default function PumpScannerPanel({ data }: { data: PumpScannerResult | null }) {
  if (!data || (data.pre_pump.length === 0 && data.dump_risk.length === 0)) {
    return (
      <div className="bg-card-bg border border-card-border rounded-xl p-6">
        <h3 className="text-sm font-semibold mb-3">🔍 Pump & Dump 扫描器</h3>
        <p className="text-text-muted text-sm text-center py-4">扫描中，请稍候...</p>
      </div>
    );
  }

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold">🔍 Pump & Dump 扫描器</h3>
        <span className="text-xs text-text-muted">
          已扫描 {data.total_scanned} 个合约 · Top 3
        </span>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {/* Pre-Pump Column */}
        <div>
          <h4 className="text-xs font-semibold text-accent-green mb-2 flex items-center gap-1">
            🚀 潜力拉升榜 <span className="text-text-muted font-normal">— 蓄势待发</span>
          </h4>
          <div className="space-y-2">
            {data.pre_pump.slice(0, 3).map((c) => (
              <CoinRow key={c.inst_id} c={c} type="pump" />
            ))}
            {data.pre_pump.length === 0 && (
              <p className="text-text-muted text-xs text-center py-3">暂无达标币种</p>
            )}
          </div>
        </div>

        {/* Dump-Risk Column */}
        <div>
          <h4 className="text-xs font-semibold text-accent-red mb-2 flex items-center gap-1">
            💣 暴跌预警榜 <span className="text-text-muted font-normal">— 过度拉伸</span>
          </h4>
          <div className="space-y-2">
            {data.dump_risk.slice(0, 3).map((c) => (
              <CoinRow key={c.inst_id} c={c} type="dump" />
            ))}
            {data.dump_risk.length === 0 && (
              <p className="text-text-muted text-xs text-center py-3">暂无达标币种</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

