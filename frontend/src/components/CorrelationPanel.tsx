"use client";

import { useState } from "react";
import type { CorrelationMatrix } from "@/lib/types";

function getCorrColor(value: number): string {
  if (value >= 0.7) return "bg-green-600";
  if (value >= 0.4) return "bg-green-800";
  if (value >= 0.1) return "bg-green-900/60";
  if (value >= -0.1) return "bg-gray-700";
  if (value >= -0.4) return "bg-red-900/60";
  if (value >= -0.7) return "bg-red-800";
  return "bg-red-600";
}

function getCorrTextColor(value: number): string {
  if (Math.abs(value) >= 0.5) return "text-white";
  return "text-text-muted";
}

export default function CorrelationPanel({ data }: { data: CorrelationMatrix | null }) {
  const [period, setPeriod] = useState<"7d" | "30d">("30d");

  if (!data) {
    return (
      <div className="bg-card-bg border border-card-border rounded-xl p-6 text-center text-text-muted">
        相关性数据加载中...
      </div>
    );
  }

  const matrix = period === "7d" ? data.matrix_7d : data.matrix_30d;

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">📐 相关性矩阵</h3>
        <div className="flex gap-1">
          <button
            onClick={() => setPeriod("7d")}
            className={`px-2 py-0.5 text-xs rounded ${period === "7d" ? "bg-accent-blue text-white" : "bg-bg-primary text-text-muted"}`}
          >
            7天
          </button>
          <button
            onClick={() => setPeriod("30d")}
            className={`px-2 py-0.5 text-xs rounded ${period === "30d" ? "bg-accent-blue text-white" : "bg-bg-primary text-text-muted"}`}
          >
            30天
          </button>
        </div>
      </div>

      {/* Matrix Grid */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="p-1"></th>
              {data.assets.map((a) => (
                <th key={a} className="p-1 text-center text-text-muted font-medium">{a}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.assets.map((rowAsset, i) => (
              <tr key={rowAsset}>
                <td className="p-1 text-text-muted font-medium">{rowAsset}</td>
                {data.assets.map((_, j) => {
                  const val = matrix[i][j];
                  return (
                    <td key={j} className="p-0.5">
                      <div
                        className={`${getCorrColor(val)} ${getCorrTextColor(val)} rounded p-1 text-center text-[10px] font-mono`}
                        title={`${rowAsset} vs ${data.assets[j]}: ${val.toFixed(4)}`}
                      >
                        {val.toFixed(2)}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Notable Pairs */}
      {data.pairs.length > 0 && (
        <div className="mt-3 pt-3 border-t border-card-border">
          <div className="text-xs text-text-muted mb-1">显著相关性:</div>
          <div className="flex flex-wrap gap-1">
            {data.pairs.slice(0, 5).map((p, i) => {
              const val = period === "7d" ? p.correlation_7d : p.correlation_30d;
              return (
                <span
                  key={i}
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    val > 0 ? "bg-green-900/40 text-accent-green" : "bg-red-900/40 text-accent-red"
                  }`}
                >
                  {p.asset_a}/{p.asset_b}: {val >= 0 ? "+" : ""}{val.toFixed(2)}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

