"use client";
import dynamic from "next/dynamic";
const TrackerApp = dynamic(() => import("@/components/tracker/TrackerApp"), { ssr: false });

export default function SimPage() {
  return (
    <main className="max-w-7xl mx-auto px-4 py-6">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold"><span className="text-accent-yellow">🎮</span> 模拟盘</h1>
          <p className="text-sm text-text-muted">实时行情 · 信号扫描 · 手动/自动交易 · 交易日记</p>
        </div>
        <a href="/" className="text-sm text-accent-blue hover:underline">← 返回主面板</a>
      </header>
      <TrackerApp />
    </main>
  );
}
