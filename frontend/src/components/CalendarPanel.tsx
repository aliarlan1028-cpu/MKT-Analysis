"use client";

import type { CalendarEvent } from "@/lib/types";

const IMPACT_STYLES: Record<string, { bg: string; text: string }> = {
  HIGH: { bg: "bg-accent-red/15", text: "text-accent-red" },
  MEDIUM: { bg: "bg-accent-yellow/15", text: "text-accent-yellow" },
  LOW: { bg: "bg-accent-blue/15", text: "text-accent-blue" },
};

function groupByDate(events: CalendarEvent[]): Record<string, CalendarEvent[]> {
  const groups: Record<string, CalendarEvent[]> = {};
  for (const e of events) {
    if (!groups[e.date]) groups[e.date] = [];
    groups[e.date].push(e);
  }
  return groups;
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr + "T00:00:00");
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return `${d.getMonth() + 1}/${d.getDate()} ${weekdays[d.getDay()]}`;
}

export default function CalendarPanel({ events }: { events: CalendarEvent[] }) {
  if (!events.length) {
    return (
      <div className="bg-card-bg border border-card-border rounded-xl p-5">
        <h3 className="text-lg font-bold mb-3">🇺🇸 美国经济事件日历</h3>
        <p className="text-text-muted text-sm">暂无近期事件数据，等待下次分析更新</p>
      </div>
    );
  }

  const grouped = groupByDate(events);
  const sortedDates = Object.keys(grouped).sort();

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-5">
      <h3 className="text-lg font-bold mb-4">🇺🇸 未来7日美国经济事件</h3>

      <div className="space-y-4">
        {sortedDates.map((date) => (
          <div key={date}>
            <div className="text-sm font-semibold text-accent-blue mb-2">
              📅 {formatDate(date)}
            </div>
            <div className="space-y-2 ml-4">
              {grouped[date].map((event, idx) => {
                const style = IMPACT_STYLES[event.impact] || IMPACT_STYLES.LOW;
                return (
                  <div
                    key={idx}
                    className="flex items-start gap-3 bg-background/50 rounded-lg p-3"
                  >
                    <span className={`${style.bg} ${style.text} text-xs px-2 py-0.5 rounded shrink-0 mt-0.5`}>
                      {event.impact}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">{event.title}</span>
                        {event.time && event.time !== "TBD" && (
                          <span className="text-xs text-text-muted">{event.time}</span>
                        )}
                      </div>
                      {(event.previous || event.forecast) && (
                        <div className="text-xs text-text-muted mt-1">
                          {event.previous && <span>前值: {event.previous}</span>}
                          {event.previous && event.forecast && <span className="mx-2">|</span>}
                          {event.forecast && <span>预期: {event.forecast}</span>}
                        </div>
                      )}
                      {event.description && (
                        <p className="text-xs text-text-muted mt-1">{event.description}</p>
                      )}
                      {(event.impact_if_met || event.impact_if_missed) && (
                        <div className="mt-2 space-y-1 border-t border-card-border pt-2">
                          {event.impact_if_met && (
                            <div className="text-xs">
                              <span className="text-accent-green font-medium">✅ 达预期: </span>
                              <span className="text-text-secondary">{event.impact_if_met}</span>
                            </div>
                          )}
                          {event.impact_if_missed && (
                            <div className="text-xs">
                              <span className="text-accent-red font-medium">❌ 未达预期: </span>
                              <span className="text-text-secondary">{event.impact_if_missed}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

