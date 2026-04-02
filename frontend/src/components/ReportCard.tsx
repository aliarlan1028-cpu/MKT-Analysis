"use client";

import type { AnalysisReport } from "@/lib/types";

const SESSION_LABELS: Record<string, string> = {
  morning: "☀️ 早盘 06:00",
  evening: "🌙 晚盘 20:00",
};

function DirectionBadge({ direction, confidence }: { direction: string; confidence: number }) {
  const config: Record<string, { bg: string; text: string; label: string }> = {
    LONG: { bg: "bg-accent-green/15", text: "text-accent-green", label: "🟢 做多" },
    SHORT: { bg: "bg-accent-red/15", text: "text-accent-red", label: "🔴 做空" },
    NEUTRAL: { bg: "bg-accent-yellow/15", text: "text-accent-yellow", label: "⚪ 观望" },
  };
  const c = config[direction] || config.NEUTRAL;
  return (
    <div className={`${c.bg} ${c.text} rounded-lg px-4 py-2 text-center`}>
      <div className="text-xl font-bold">{c.label}</div>
      <div className="text-sm opacity-80">置信度 {confidence}%</div>
    </div>
  );
}

function Section({ section }: { section: { title: string; content: string; bullets: string[] } }) {
  return (
    <div className="mb-4">
      <h4 className="font-semibold text-accent-blue mb-1">{section.title}</h4>
      <p className="text-sm text-text-muted mb-2">{section.content}</p>
      <ul className="text-sm space-y-1">
        {section.bullets.map((b, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-accent-yellow mt-0.5">•</span>
            <span>{b}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ReportCard({ report }: { report: AnalysisReport }) {
  const ts = new Date(report.timestamp);
  const timeStr = ts.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold">
              {report.name} {SESSION_LABELS[report.session] || report.session}
            </h2>
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
              report.ai_provider === "deepseek"
                ? "bg-blue-500/10 text-blue-400 border-blue-500/30"
                : "bg-purple-500/10 text-purple-400 border-purple-500/30"
            }`}>
              {report.ai_provider === "deepseek" ? "🧠 DeepSeek" : "✨ Gemini"}
            </span>
          </div>
          <p className="text-sm text-text-muted">{timeStr}</p>
        </div>
        <div className="text-right">
          <p className="text-sm text-text-muted">分析时价格</p>
          <p className="text-lg font-mono font-bold">${report.price_at_analysis.toLocaleString("en-US", { minimumFractionDigits: 2 })}</p>
        </div>
      </div>

      {/* Signal */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <DirectionBadge direction={report.signal.direction} confidence={report.signal.confidence} />
        <div className="bg-card-bg border border-card-border rounded-lg px-3 py-2 text-center">
          <div className="text-xs text-text-muted">入场区间</div>
          <div className="font-mono text-sm">${report.signal.entry_zone[0]?.toLocaleString()} - ${report.signal.entry_zone[1]?.toLocaleString()}</div>
        </div>
        <div className="bg-card-bg border border-card-border rounded-lg px-3 py-2 text-center">
          <div className="text-xs text-text-muted">止损</div>
          <div className="font-mono text-sm text-accent-red">${report.signal.stop_loss.toLocaleString()}</div>
        </div>
        <div className="bg-card-bg border border-card-border rounded-lg px-3 py-2 text-center">
          <div className="text-xs text-text-muted">止盈</div>
          <div className="font-mono text-sm text-accent-green">
            {report.signal.take_profit.map((t) => `$${t.toLocaleString()}`).join(" / ")}
          </div>
        </div>
      </div>

      {/* Leverage & RR */}
      <div className="flex gap-4 mb-6 text-sm">
        <span className="bg-accent-yellow/10 text-accent-yellow px-3 py-1 rounded">
          杠杆: {report.signal.leverage_suggestion}
        </span>
        {report.signal.risk_reward_ratio && (
          <span className="bg-accent-blue/10 text-accent-blue px-3 py-1 rounded">
            盈亏比: {report.signal.risk_reward_ratio}
          </span>
        )}
      </div>

      {/* Key Support & Resistance */}
      {(report.technical.key_support?.length || report.technical.key_resistance?.length) && (
        <div className="grid grid-cols-2 gap-3 mb-6">
          <div className="bg-accent-green/5 border border-accent-green/20 rounded-lg px-3 py-2">
            <div className="text-xs text-accent-green font-semibold mb-1">🟢 关键支撑位</div>
            <div className="font-mono text-sm space-y-0.5">
              {report.technical.key_support?.map((p, i) => (
                <div key={i} className="text-accent-green">${p.toLocaleString()}</div>
              )) || <div className="text-text-muted">N/A</div>}
            </div>
          </div>
          <div className="bg-accent-red/5 border border-accent-red/20 rounded-lg px-3 py-2">
            <div className="text-xs text-accent-red font-semibold mb-1">🔴 关键阻力位</div>
            <div className="font-mono text-sm space-y-0.5">
              {report.technical.key_resistance?.map((p, i) => (
                <div key={i} className="text-accent-red">${p.toLocaleString()}</div>
              )) || <div className="text-text-muted">N/A</div>}
            </div>
          </div>
        </div>
      )}

      {/* Analysis Sections */}
      <div className="grid md:grid-cols-2 gap-4">
        <Section section={report.technical} />
        <Section section={report.fundamental} />
        <Section section={report.sentiment} />
        <Section section={report.macro} />
      </div>

      {/* Risk Warning */}
      <div className="mt-4 bg-accent-red/5 border border-accent-red/20 rounded-lg p-4">
        <Section section={report.risk_warning} />
      </div>
    </div>
  );
}

