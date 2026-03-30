"use client";

import type { PriceSpikeAlert } from "@/lib/types";

const categoryIcons: Record<string, string> = {
  news: "📰",
  whale: "🐋",
  liquidation: "💥",
  macro: "📊",
  fed: "🏛️",
  technical: "📈",
  other: "🔄",
};

const categoryLabels: Record<string, string> = {
  news: "突发新闻",
  whale: "鲸鱼异动",
  liquidation: "清算连锁",
  macro: "宏观数据",
  fed: "美联储",
  technical: "技术突破",
  other: "其他",
};

const confidenceColors: Record<string, string> = {
  high: "text-accent-green",
  medium: "text-accent-yellow",
  low: "text-text-muted",
};

function timeAgo(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
}

export default function PriceSpikePanel({ data }: { data: PriceSpikeAlert[] }) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-card-bg border border-card-border rounded-xl p-6">
        <h3 className="text-sm font-semibold mb-3">⚡ BTC 价格异动监控</h3>
        <p className="text-text-muted text-sm text-center py-4">
          监控运行中，等待检测到价格异动...
        </p>
        <p className="text-xs text-text-muted text-center">
          当 BTC 在 5 分钟内波动 ≥1% 时自动触发 AI 归因分析
        </p>
      </div>
    );
  }

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-4">
      <h3 className="text-sm font-semibold mb-3">
        ⚡ BTC 价格异动监控
        <span className="ml-2 text-xs text-text-muted font-normal">
          共 {data.length} 条警报
        </span>
      </h3>
      <div className="space-y-3 max-h-[500px] overflow-y-auto">
        {data.map((alert, i) => {
          const isPump = alert.direction === "pump";
          const cat = alert.analysis?.category || "other";
          return (
            <div
              key={i}
              className="border border-card-border rounded-lg p-3 hover:border-accent-blue/40 transition-colors"
            >
              {/* Header: direction + price change */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-lg font-bold ${isPump ? "text-accent-green" : "text-accent-red"}`}>
                    {isPump ? "🚀" : "💣"} {alert.change_pct > 0 ? "+" : ""}{alert.change_pct}%
                  </span>
                  <span className="text-xs text-text-muted">
                    ${alert.price_before.toLocaleString()} → ${alert.price_after.toLocaleString()}
                  </span>
                </div>
                <span className="text-xs text-text-muted">{timeAgo(alert.detected_at)}</span>
              </div>

              {/* Category badge */}
              <div className="flex items-center gap-2 mb-2">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-bg-primary text-xs font-medium">
                  {categoryIcons[cat] || "🔄"} {categoryLabels[cat] || cat}
                </span>
                <span className={`text-xs ${confidenceColors[alert.analysis?.confidence] || ""}`}>
                  置信度: {alert.analysis?.confidence || "N/A"}
                </span>
              </div>

              {/* Primary cause */}
              <p className="text-sm font-medium mb-1">
                {alert.analysis?.primary_cause || "分析中..."}
              </p>

              {/* Details */}
              <p className="text-xs text-text-muted leading-relaxed">
                {alert.analysis?.details || ""}
              </p>

              {/* Sources */}
              {alert.analysis?.sources && alert.analysis.sources.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {alert.analysis.sources.map((src, j) => (
                    <span key={j} className="text-xs text-accent-blue/70 bg-accent-blue/5 px-1.5 py-0.5 rounded">
                      {src}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

