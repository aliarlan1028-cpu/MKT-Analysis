"use client";

import type { FearGreedIndex } from "@/lib/types";

function getColor(value: number) {
  if (value <= 20) return "#ff4757";
  if (value <= 40) return "#ff6b81";
  if (value <= 60) return "#f0b90b";
  if (value <= 80) return "#7bed9f";
  return "#00d4aa";
}

export default function FearGreedGauge({ data }: { data: FearGreedIndex }) {
  const color = getColor(data.value);
  const rotation = (data.value / 100) * 180 - 90; // -90 to 90 degrees

  return (
    <div className="bg-card-bg border border-card-border rounded-xl p-5 flex flex-col items-center">
      <h3 className="text-sm text-text-muted mb-3">恐慌贪婪指数</h3>

      {/* Gauge */}
      <div className="relative w-40 h-20 mb-2">
        <svg viewBox="0 0 200 100" className="w-full h-full">
          {/* Background arc */}
          <path
            d="M 10 95 A 85 85 0 0 1 190 95"
            fill="none"
            stroke="#21262d"
            strokeWidth="12"
            strokeLinecap="round"
          />
          {/* Colored arc */}
          <path
            d="M 10 95 A 85 85 0 0 1 190 95"
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${(data.value / 100) * 267} 267`}
          />
          {/* Needle */}
          <line
            x1="100"
            y1="95"
            x2="100"
            y2="25"
            stroke={color}
            strokeWidth="2"
            transform={`rotate(${rotation}, 100, 95)`}
          />
          <circle cx="100" cy="95" r="4" fill={color} />
        </svg>
      </div>

      <div className="text-3xl font-bold" style={{ color }}>
        {data.value}
      </div>
      <div className="text-sm text-text-muted mt-1">{data.label}</div>
    </div>
  );
}

