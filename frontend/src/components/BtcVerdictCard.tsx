"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import type { BtcVerdict } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

function fmt(n: number | null | undefined, d = 0): string {
  if (n == null) return "N/A";
  return n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

interface SymbolOption {
  instId: string;
  ccy: string;
  label: string;
}

const DIR_STYLES: Record<string, { bg: string; border: string; glow: string }> = {
  bullish:  { bg: "bg-accent-green/5",  border: "border-accent-green/40", glow: "shadow-accent-green/10" },
  bearish:  { bg: "bg-accent-red/5",    border: "border-accent-red/40",   glow: "shadow-accent-red/10" },
  neutral:  { bg: "bg-card-bg",         border: "border-card-border",     glow: "" },
};

interface Props {
  selectedSymbol: string;
  onSymbolChange: (ccy: string) => void;
}

export default function BtcVerdictCard({ selectedSymbol, onSymbolChange }: Props) {
  const [verdict, setVerdict] = useState<BtcVerdict | null>(null);
  const [ts, setTs] = useState<string>("");
  const [symbols, setSymbols] = useState<SymbolOption[]>([]);
  const [searchText, setSearchText] = useState<string>("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Fetch available symbols
  useEffect(() => {
    const loadSymbols = async () => {
      try {
        const res = await fetch(`${API}/derivatives/symbols`);
        if (res.ok) {
          const data = await res.json();
          setSymbols(data);
        }
      } catch { /* ignore */ }
    };
    loadSymbols();
  }, []);

  // Fetch verdict for selected symbol
  const loadVerdict = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/derivatives/${selectedSymbol}`);
      if (res.ok) {
        const data = await res.json();
        setVerdict(data.verdict);
        setTs(data.timestamp);
      }
    } catch { /* ignore */ }
    setLoading(false);
  }, [selectedSymbol]);

  useEffect(() => {
    loadVerdict();
    const iv = setInterval(loadVerdict, 60000);
    return () => clearInterval(iv);
  }, [loadVerdict]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const filteredSymbols = symbols.filter(s =>
    s.ccy.toLowerCase().includes(searchText.toLowerCase()) ||
    s.label.toLowerCase().includes(searchText.toLowerCase())
  );

  const handleSelect = (ccy: string) => {
    onSymbolChange(ccy);
    setShowDropdown(false);
    setSearchText("");
    setVerdict(null);
  };

  if (!verdict && !loading) {
    return (
      <div className="bg-card-bg border border-card-border rounded-xl p-4">
        <p className="text-text-muted text-sm">🤖 AI 研判加载中...</p>
      </div>
    );
  }

  const style = verdict ? (DIR_STYLES[verdict.direction] || DIR_STYLES.neutral) : DIR_STYLES.neutral;
  const strengthLabel = verdict?.strength === "strong" ? "强" : verdict?.strength === "moderate" ? "中" : "弱";

  return (
    <div className={`${style.bg} border ${style.border} rounded-xl p-4 shadow-lg ${style.glow}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">🤖 AI 综合研判</h3>
          {/* Symbol Selector */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              className="px-2 py-0.5 text-xs font-bold bg-accent-blue/20 text-accent-blue border border-accent-blue/30 rounded-md hover:bg-accent-blue/30 transition-colors"
            >
              {selectedSymbol}/USDT ▾
            </button>
            {showDropdown && (
              <div className="absolute top-full left-0 mt-1 w-56 bg-card-bg border border-card-border rounded-lg shadow-xl z-50 overflow-hidden">
                <div className="p-2 border-b border-card-border">
                  <input
                    type="text"
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    placeholder="搜索币对..."
                    className="w-full px-2 py-1 text-xs bg-bg-primary border border-card-border rounded text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                    autoFocus
                  />
                </div>
                <div className="max-h-64 overflow-y-auto">
                  {filteredSymbols.map((s) => (
                    <button
                      key={s.instId}
                      onClick={() => handleSelect(s.ccy)}
                      className={`w-full text-left px-3 py-1.5 text-xs hover:bg-accent-blue/10 transition-colors ${
                        s.ccy === selectedSymbol ? "bg-accent-blue/20 text-accent-blue font-bold" : "text-text-primary"
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                  {filteredSymbols.length === 0 && (
                    <p className="px-3 py-2 text-xs text-text-muted">未找到匹配的币对</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {loading && <span className="text-xs text-accent-blue animate-pulse">加载中...</span>}
          {ts && (
            <span className="text-xs text-text-muted">
              {new Date(ts).toLocaleTimeString("zh-CN", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>
      </div>

      {verdict && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* Direction + Score */}
          <div>
            <div className="text-2xl font-bold mb-1">{verdict.direction_cn}</div>
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <span>综合评分: <span className="font-mono font-bold">{verdict.score > 0 ? "+" : ""}{verdict.score}</span></span>
              <span>| 信号强度: {strengthLabel}</span>
            </div>
            <p className="text-sm mt-2 leading-relaxed">{verdict.summary}</p>
          </div>

          {/* Signals */}
          <div>
            <p className="text-xs text-text-muted font-semibold mb-1">📡 信号明细</p>
            <div className="flex flex-wrap gap-1">
              {verdict.signals.map((s, i) => (
                <span key={i} className={`text-xs px-2 py-0.5 rounded-full ${
                  s.includes("多") || s.includes("涨") || s.includes("吸筹") || s.includes("超卖") || s.includes("利多")
                    ? "bg-accent-green/15 text-accent-green"
                    : s.includes("空") || s.includes("跌") || s.includes("派发") || s.includes("超买") || s.includes("利空")
                    ? "bg-accent-red/15 text-accent-red"
                    : "bg-gray-700 text-text-muted"
                }`}>
                  {s}
                </span>
              ))}
            </div>
          </div>

          {/* Key Levels */}
          <div>
            <p className="text-xs text-text-muted font-semibold mb-1">📍 关键价位 (当前 ${fmt(verdict.price)})</p>
            <div className="space-y-0.5">
              {verdict.key_levels.map((l, i) => (
                <div key={i} className="flex justify-between text-xs">
                  <span className={`${
                    l.label.includes("止盈") || l.label.includes("支撑") ? "text-accent-green" :
                    l.label.includes("止损") || l.label.includes("阻力") ? "text-accent-red" :
                    "text-accent-blue"
                  }`}>{l.label}</span>
                  <span className="font-mono">${fmt(l.price)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

