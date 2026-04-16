/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useMemo } from 'react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Activity, Cpu, Coins, Search } from 'lucide-react';
import { formatPrice, formatPercent } from '@/lib/utils';

interface HeaderProps {
  symbol: string;
  interval: string;
  instruments: { id: string, name: string }[];
  onSymbolChange: (symbol: string) => void;
  onIntervalChange: (interval: string) => void;
  price: number;
  change24h: number;
}

export const Header: React.FC<HeaderProps> = ({ 
  symbol, 
  interval,
  instruments, 
  onSymbolChange, 
  onIntervalChange,
  price, 
  change24h 
}) => {
  const [search, setSearch] = useState('');

  const timeframes = [
    { value: '1m', label: '1分钟' },
    { value: '5m', label: '5分钟' },
    { value: '15m', label: '15分钟' },
    { value: '1H', label: '1小时' },
    { value: '4H', label: '4小时' },
    { value: '1D', label: '1日线' },
  ];

  const filteredInstruments = useMemo(() => {
    if (!search) return instruments;
    return instruments.filter(inst => 
      inst.id.toLowerCase().includes(search.toLowerCase()) || 
      inst.name.toLowerCase().includes(search.toLowerCase())
    ).slice(0, 50); // Limit to 50 for performance in the dropdown
  }, [instruments, search]);

  return (
    <header className="h-14 border-bottom border-zinc-800 bg-zinc-950 flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-emerald-600 rounded-lg flex items-center justify-center">
            <Activity className="text-white w-5 h-5" />
          </div>
          <span className="font-bold text-lg tracking-tight">OKX Tracker Pro</span>
        </div>

        <div className="h-6 w-[1px] bg-zinc-800" />

        <Select value={symbol} onValueChange={onSymbolChange}>
          <SelectTrigger className="w-[220px] bg-zinc-900 border-zinc-800 h-9 text-xs font-bold">
            <SelectValue placeholder="选择交易对" />
          </SelectTrigger>
          <SelectContent className="bg-zinc-900 border-zinc-800 text-zinc-100 max-h-[400px]">
            <div className="p-2 sticky top-0 bg-zinc-900 z-10 border-b border-zinc-800">
              <div className="relative">
                <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-zinc-500" />
                <Input 
                  placeholder="搜索币种..." 
                  className="h-8 pl-8 text-xs bg-zinc-950 border-zinc-800 focus-visible:ring-emerald-500"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => e.stopPropagation()} // Prevent select from closing
                />
              </div>
            </div>
            {filteredInstruments.length === 0 ? (
              <div className="p-4 text-center text-xs text-zinc-500">未找到相关币对</div>
            ) : (
              filteredInstruments.map(inst => (
                <SelectItem key={inst.id} value={inst.id} className="text-xs">
                  {inst.name}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>

        <Select value={interval} onValueChange={onIntervalChange}>
          <SelectTrigger className="w-[100px] bg-zinc-900 border-zinc-800 h-9 text-xs font-bold">
            <SelectValue placeholder="周期" />
          </SelectTrigger>
          <SelectContent className="bg-zinc-900 border-zinc-800 text-zinc-100">
            {timeframes.map(tf => (
              <SelectItem key={tf.value} value={tf.value} className="text-xs">
                {tf.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-4">
          <div className="flex flex-col">
            <span className="text-[10px] text-zinc-500 uppercase font-bold">最新价格</span>
            <span className="text-sm font-mono font-bold text-zinc-100">
              {formatPrice(price)}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] text-zinc-500 uppercase font-bold">24H 涨跌</span>
            <span className={`text-sm font-mono font-bold ${change24h >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
              {formatPercent(change24h)}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <Badge variant="outline" className="bg-emerald-500/5 text-emerald-500 border-emerald-500/20 gap-1.5 h-7">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          WebSocket 实时连接
        </Badge>
        <div className="flex items-center gap-2 text-zinc-400">
          <Coins className="w-4 h-4" />
          <span className="text-xs">模拟交易模式</span>
        </div>
      </div>
    </header>
  );
};
