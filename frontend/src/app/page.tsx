"use client";

import { useEffect, useState, useCallback } from "react";
import MarketCard from "@/components/MarketCard";
import FearGreedGauge from "@/components/FearGreedGauge";
import ReportCard from "@/components/ReportCard";
import CalendarPanel from "@/components/CalendarPanel";
import PriceSpikePanel from "@/components/PriceSpikePanel";
import PostMortemPanel from "@/components/PostMortemPanel";
import WhaleAlertPanel from "@/components/WhaleAlertPanel";
import LiquidationPanel from "@/components/LiquidationPanel";
import CorrelationPanel from "@/components/CorrelationPanel";
import PumpScannerPanel from "@/components/PumpScannerPanel";
import BtcDashboard from "@/components/BtcDashboard";
import BtcVerdictCard from "@/components/BtcVerdictCard";
import BtcTopCards from "@/components/BtcTopCards";
import type {
  DashboardResponse, AnalysisReport, ReportListItem, ProfessionalDashboard,
} from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export default function Home() {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [activeReport, setActiveReport] = useState<AnalysisReport | null>(null);
  const [proDash, setProDash] = useState<ProfessionalDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"reports" | "pro">("reports");
  const [selectedSymbol, setSelectedSymbol] = useState<string>("BTC");
  const [analyzing, setAnalyzing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [dashRes, reportsRes, proRes] = await Promise.allSettled([
        fetch(`${API}/dashboard`).then((r) => r.ok ? r.json() : null),
        fetch(`${API}/reports?limit=10`).then((r) => r.ok ? r.json() : []),
        fetch(`${API}/professional`).then((r) => r.ok ? r.json() : null),
      ]);
      const dash = dashRes.status === "fulfilled" ? dashRes.value : null;
      const reps = reportsRes.status === "fulfilled" ? reportsRes.value : [];
      const pro = proRes.status === "fulfilled" ? proRes.value : null;

      if (dash) setDashboard(dash);
      if (pro) setProDash(pro);
      if (reps?.length) {
        setReports(reps);
        try {
          const latestRes = await fetch(`${API}/reports/${reps[0].id}`);
          if (latestRes.ok) setActiveReport(await latestRes.json());
        } catch { /* ignore */ }
      }
      // Only show error if nothing loaded at all
      if (!dash && !reps?.length && !pro) {
        setError("无法连接后端服务，请确保后端已启动");
      } else {
        setError(null);
      }
    } catch {
      setError("无法连接后端服务，请确保后端已启动");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const loadReport = async (id: string) => {
    const res = await fetch(`${API}/reports/${id}`);
    if (res.ok) setActiveReport(await res.json());
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-accent-blue border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-text-muted">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <main className="max-w-7xl mx-auto px-4 py-6">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">
            <span className="text-accent-yellow">⚡</span> CryptoEdge Pro
          </h1>
          <p className="text-sm text-text-muted">AI 驱动合约交易分析 · 每日 06:00 / 20:00</p>
        </div>
        {dashboard && (
          <span className="text-xs text-text-muted">
            更新于 {new Date(dashboard.last_updated).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}
          </span>
        )}
      </header>

      {error && (
        <div className="bg-accent-red/10 border border-accent-red/30 text-accent-red rounded-lg p-4 mb-6">
          {error}
        </div>
      )}

      {dashboard && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-4">📊 实时行情</h2>
          {/* Row 1: Market cards + EMA + ATR + CVD (same size) */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-4">
            {dashboard.markets.map((m) => (
              <MarketCard key={m.symbol} data={m} />
            ))}
            <FearGreedGauge data={dashboard.fear_greed} />
            <BtcTopCards symbol={selectedSymbol} />
          </div>
          {/* Row 2: AI Verdict (full width) */}
          <BtcVerdictCard selectedSymbol={selectedSymbol} onSymbolChange={setSelectedSymbol} />
          {/* Row 3: Collapsible BTC derivatives details */}
          <BtcDashboard symbol={selectedSymbol} />
        </section>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-2 mb-6 border-b border-card-border pb-2">
        <button
          onClick={() => setTab("reports")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
            tab === "reports"
              ? "bg-card-bg text-accent-blue border-b-2 border-accent-blue"
              : "text-text-muted hover:text-white"
          }`}
        >
          📋 AI 分析报告
        </button>
        <button
          onClick={() => setTab("pro")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
            tab === "pro"
              ? "bg-card-bg text-accent-blue border-b-2 border-accent-blue"
              : "text-text-muted hover:text-white"
          }`}
        >
          🎯 专业仪表盘
        </button>
      </div>

      {tab === "reports" && (
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            {/* Always visible: manual trigger button + report selector */}
            <div className="flex items-center gap-2 overflow-x-auto pb-2">
              <button
                onClick={async () => {
                  setAnalyzing(true);
                  try {
                    const res = await fetch(`${API}/analyze/all`, { method: "POST" });
                    if (res.ok) {
                      await fetchData();
                    } else {
                      alert("分析触发失败，请稍后重试");
                    }
                  } catch {
                    alert("无法连接后端服务");
                  } finally {
                    setAnalyzing(false);
                  }
                }}
                disabled={analyzing}
                className="shrink-0 px-3 py-2 bg-accent-blue text-white rounded-lg text-sm hover:bg-accent-blue/80 transition-colors disabled:opacity-50"
              >
                {analyzing ? "⏳ 分析中..." : "🚀 手动推送"}
              </button>
              {reports.map((r) => (
                <button
                  key={r.id}
                  onClick={() => loadReport(r.id)}
                  className={`shrink-0 px-3 py-2 rounded-lg text-sm border transition-colors ${
                    activeReport?.id === r.id
                      ? "border-accent-blue bg-accent-blue/10 text-accent-blue"
                      : "border-card-border bg-card-bg text-text-muted hover:border-accent-blue/40"
                  }`}
                >
                  <span className={r.direction === "LONG" ? "text-accent-green" : r.direction === "SHORT" ? "text-accent-red" : "text-accent-yellow"}>●</span>
                  {" "}{r.name} · {new Date(r.timestamp).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </button>
              ))}
            </div>
            {activeReport ? (
              <ReportCard report={activeReport} />
            ) : (
              <div className="bg-card-bg border border-card-border rounded-xl p-8 text-center text-text-muted">
                <p>暂无分析报告，请点击上方「🚀 手动推送」按钮生成</p>
              </div>
            )}
          </div>
          <div>
            <h2 className="text-lg font-semibold mb-4">📅 事件日历</h2>
            <CalendarPanel events={activeReport?.calendar_events || []} />
          </div>
        </div>
      )}

      {tab === "pro" && proDash && (
        <div className="space-y-6">
          {/* Row 1: Price Spike Monitor + Post-Mortem */}
          <div className="grid lg:grid-cols-2 gap-6">
            <PriceSpikePanel data={proDash.price_spikes || []} />
            <PostMortemPanel postmortems={proDash.postmortems} winRate={proDash.win_rate} />
          </div>

          {/* Row 2: Whale Alerts + Liquidation */}
          <div className="grid lg:grid-cols-2 gap-6">
            <WhaleAlertPanel data={proDash.whale_alerts} />
            <LiquidationPanel data={proDash.liquidation || []} />
          </div>

          {/* Row 3: Pump & Dump Scanner */}
          <PumpScannerPanel data={proDash.pump_scanner || null} postmortems={proDash.scanner_postmortems || null} />

          {/* Row 4: Correlation Matrix */}
          <CorrelationPanel data={proDash.correlation} />
        </div>
      )}

      {tab === "pro" && !proDash && (
        <div className="bg-card-bg border border-card-border rounded-xl p-8 text-center text-text-muted">
          专业数据加载中...
        </div>
      )}
    </main>
  );
}
