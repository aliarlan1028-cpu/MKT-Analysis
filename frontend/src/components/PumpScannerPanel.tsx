"use client";

import { useState } from "react";
import type { PumpScannerResult, PumpCandidate, ScannerPostmortems, ScannerPMRecord } from "@/lib/types";

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

const resultColors: Record<string, string> = {
  STRONG_WIN: "text-accent-green",
  WIN: "text-accent-green",
  PARTIAL_WIN: "text-accent-yellow",
  NEUTRAL: "text-text-muted",
  LOSS: "text-accent-red",
  NO_AI: "text-text-muted",
};

const resultIcons: Record<string, string> = {
  STRONG_WIN: "🎯",
  WIN: "✅",
  PARTIAL_WIN: "⚡",
  NEUTRAL: "➖",
  LOSS: "❌",
  NO_AI: "—",
};

function PMRecord({ r }: { r: ScannerPMRecord }) {
  const isPump = r.category === "pre_pump";
  const changePct = r.change_after_24h ?? 0;
  return (
    <div className="flex items-center justify-between text-xs py-1.5 border-b border-card-border/50 last:border-0">
      <div className="flex items-center gap-2 min-w-0">
        <span className={`text-[10px] px-1 rounded ${isPump ? "bg-accent-green/10 text-accent-green" : "bg-accent-red/10 text-accent-red"}`}>
          {isPump ? "拉升" : "暴跌"}
        </span>
        <span className="font-medium">{r.coin}</span>
        <span className="text-text-muted text-[10px]">{r.score}分</span>
      </div>
      <div className="flex items-center gap-3">
        {/* Code signal result */}
        <span className={resultColors[r.result]}>
          {resultIcons[r.result]} {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
        </span>
        {/* AI verdict result */}
        {r.ai_verdict && r.ai_result && r.ai_result !== "NO_AI" && (
          <span className={`text-[10px] ${resultColors[r.ai_result]}`}>
            AI({r.ai_verdict}){resultIcons[r.ai_result]}
          </span>
        )}
      </div>
    </div>
  );
}

function PostmortemSection({ pm }: { pm: ScannerPostmortems }) {
  const [showRecords, setShowRecords] = useState(false);
  const ppStats = pm.stats.pre_pump;
  const drStats = pm.stats.dump_risk;
  const ai = pm.ai_stats;

  return (
    <div className="mt-4 border-t border-card-border pt-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-xs font-semibold">📊 信号复盘 (24h后评估)</h4>
        {pm.records.length > 0 && (
          <button
            onClick={() => setShowRecords(!showRecords)}
            className="text-[10px] text-accent-blue hover:underline"
          >
            {showRecords ? "收起记录" : `查看记录 (${pm.records.length})`}
          </button>
        )}
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        {/* Pre-pump stats */}
        <div className="bg-bg-primary rounded-lg p-2 text-center">
          <div className="text-[10px] text-accent-green mb-1">🚀 拉升榜胜率</div>
          <div className="text-lg font-bold text-accent-green">{ppStats.win_rate}%</div>
          <div className="text-[10px] text-text-muted">
            {ppStats.wins}胜 {ppStats.losses}负 / {ppStats.total}总
          </div>
          {ppStats.total > 0 && (
            <div className="text-[10px] text-text-muted">
              平均24h: <span className={ppStats.avg_change_24h >= 0 ? "text-accent-green" : "text-accent-red"}>
                {ppStats.avg_change_24h >= 0 ? "+" : ""}{ppStats.avg_change_24h}%
              </span>
            </div>
          )}
        </div>

        {/* Dump-risk stats */}
        <div className="bg-bg-primary rounded-lg p-2 text-center">
          <div className="text-[10px] text-accent-red mb-1">💣 暴跌榜胜率</div>
          <div className="text-lg font-bold text-accent-red">{drStats.win_rate}%</div>
          <div className="text-[10px] text-text-muted">
            {drStats.wins}胜 {drStats.losses}负 / {drStats.total}总
          </div>
          {drStats.total > 0 && (
            <div className="text-[10px] text-text-muted">
              平均24h: <span className={drStats.avg_change_24h <= 0 ? "text-accent-green" : "text-accent-red"}>
                {drStats.avg_change_24h >= 0 ? "+" : ""}{drStats.avg_change_24h}%
              </span>
            </div>
          )}
        </div>

        {/* AI verdict stats */}
        <div className="bg-bg-primary rounded-lg p-2 text-center">
          <div className="text-[10px] text-accent-blue mb-1">🤖 AI研判胜率</div>
          <div className="text-lg font-bold text-accent-blue">{ai.win_rate}%</div>
          <div className="text-[10px] text-text-muted">
            {ai.wins}胜 {ai.losses}负 / {ai.total}总
          </div>
          {ai.total > 0 && (
            <div className="text-[10px] text-text-muted space-x-1">
              <span className="text-accent-green">涨{ai.by_verdict["看涨"]?.win_rate ?? 0}%</span>
              <span className="text-accent-red">跌{ai.by_verdict["看跌"]?.win_rate ?? 0}%</span>
              <span>望{ai.by_verdict["观望"]?.win_rate ?? 0}%</span>
            </div>
          )}
        </div>
      </div>

      {/* No data hint */}
      {ppStats.total === 0 && drStats.total === 0 && (
        <p className="text-text-muted text-[10px] text-center py-2">暂无复盘数据，信号需等待24小时后自动评估</p>
      )}

      {/* Records list */}
      {showRecords && pm.records.length > 0 && (
        <div className="bg-bg-primary rounded-lg p-2 max-h-48 overflow-y-auto">
          {pm.records.map((r, i) => (
            <PMRecord key={`${r.coin}-${r.scanned_at}-${i}`} r={r} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function PumpScannerPanel({ data, postmortems }: { data: PumpScannerResult | null; postmortems: ScannerPostmortems | null }) {
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

      {/* Scanner Postmortem Section */}
      {postmortems && <PostmortemSection pm={postmortems} />}
    </div>
  );
}

