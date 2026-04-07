"use client";

import { useEffect, useRef } from "react";
import { createChart, CandlestickSeries, LineSeries } from "lightweight-charts";
import type { IChartApi, CandlestickData, DeepPartial, ChartOptions } from "lightweight-charts";

interface SimEvent {
  timestamp: string;
  event_type: string;
  price: number;
  ai_analysis?: string;
}

interface SimChartProps {
  coin: string;
  klines: CandlestickData[];
  entryPrice?: number;
  stopLoss?: number;
  takeProfit1?: number;
  takeProfit2?: number;
  events?: SimEvent[];
  direction?: string;
}

export default function SimChart({ coin, klines, entryPrice, stopLoss, takeProfit1, takeProfit2, events, direction }: SimChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || klines.length === 0) return;

    // Create chart
    const chart = createChart(containerRef.current, {
      layout: { background: { color: "#0a0f1a" }, textColor: "#94a3b8" },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      width: containerRef.current.clientWidth,
      height: 400,
      timeScale: { timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    });
    chartRef.current = chart;

    // Candlestick series (v5 API)
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    series.setData(klines);

    // Price lines
    if (entryPrice) {
      series.createPriceLine({
        price: entryPrice, color: "#3b82f6", lineWidth: 2,
        lineStyle: 0, title: `入场 $${entryPrice}`,
      });
    }
    if (stopLoss) {
      series.createPriceLine({
        price: stopLoss, color: "#ef4444", lineWidth: 1,
        lineStyle: 2, title: `止损 $${stopLoss}`,
      });
    }
    if (takeProfit1) {
      series.createPriceLine({
        price: takeProfit1, color: "#22c55e", lineWidth: 1,
        lineStyle: 2, title: `止盈1 $${takeProfit1}`,
      });
    }
    if (takeProfit2) {
      series.createPriceLine({
        price: takeProfit2, color: "#22c55e", lineWidth: 1,
        lineStyle: 2, title: `止盈2 $${takeProfit2}`,
      });
    }

    chart.timeScale().fitContent();

    const resizeHandler = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", resizeHandler);

    return () => {
      window.removeEventListener("resize", resizeHandler);
      chart.remove();
    };
  }, [klines, entryPrice, stopLoss, takeProfit1, takeProfit2, events, direction]);

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-4">
      <h3 className="text-sm font-semibold mb-2">📈 {coin}/USDT 实时行情</h3>
      <div ref={containerRef} />
    </div>
  );
}
