/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, Wallet } from 'lucide-react';
import { formatPrice } from '@/lib/utils';

interface TradingPanelProps {
  balance: number;
  currentPrice: number;
  symbol: string;
  onOrder: (side: 'long' | 'short', leverage: number, amount: number, price: number, tp?: number, sl?: number, isLimit?: boolean) => void;
}

export const TradingPanel: React.FC<TradingPanelProps> = ({ balance, currentPrice, symbol, onOrder }) => {
  const [leverage, setLeverage] = useState(10);
  const [amount, setAmount] = useState(100);
  const [orderType, setOrderType] = useState<'market' | 'limit'>('market');
  const [limitPrice, setLimitPrice] = useState(currentPrice);
  const [tp, setTp] = useState<string>('');
  const [sl, setSl] = useState<string>('');

  const margin = amount / leverage;

  return (
    <Card className="bg-zinc-950 border-zinc-800 text-zinc-100">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Wallet className="w-4 h-4 text-zinc-400" />
          交易面板 - {symbol}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex justify-between text-xs text-zinc-400">
          <span>可用余额</span>
          <span className="text-zinc-100 font-mono">{balance.toFixed(2)} USDT</span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Button 
            variant={orderType === 'market' ? 'default' : 'outline'}
            size="sm"
            className={`text-xs h-8 ${orderType === 'market' ? 'bg-zinc-100 text-zinc-950' : 'border-zinc-800 text-zinc-400'}`}
            onClick={() => setOrderType('market')}
          >
            市价单
          </Button>
          <Button 
            variant={orderType === 'limit' ? 'default' : 'outline'}
            size="sm"
            className={`text-xs h-8 ${orderType === 'limit' ? 'bg-zinc-100 text-zinc-950' : 'border-zinc-800 text-zinc-400'}`}
            onClick={() => {
              setOrderType('limit');
              setLimitPrice(currentPrice);
            }}
          >
            限价单
          </Button>
        </div>

        {orderType === 'limit' && (
          <div className="space-y-2">
            <label className="text-[10px] text-zinc-500 uppercase font-bold">委托价格</label>
            <Input
              type="number"
              value={limitPrice}
              onChange={(e) => setLimitPrice(Number(e.target.value))}
              className="bg-zinc-900 border-zinc-800 text-zinc-100 h-9 text-xs"
            />
          </div>
        )}

        <div className="space-y-2">
          <label className="text-[10px] text-zinc-500 uppercase font-bold">杠杆倍数: {leverage}x</label>
          <Slider
            value={[leverage]}
            onValueChange={(v) => setLeverage(v[0])}
            max={100}
            min={1}
            step={1}
            className="py-2"
          />
        </div>

        <div className="space-y-2">
          <label className="text-[10px] text-zinc-500 uppercase font-bold">下单金额 (USDT)</label>
          <div className="relative">
            <Input
              type="number"
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
              className="bg-zinc-900 border-zinc-800 text-zinc-100 pr-12 h-9 text-xs"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-zinc-500">USDT</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <label className="text-[10px] text-zinc-500 uppercase font-bold text-emerald-500">止盈价格 (TP)</label>
            <Input
              type="number"
              placeholder="可选"
              value={tp}
              onChange={(e) => setTp(e.target.value)}
              className="bg-zinc-900 border-zinc-800 text-zinc-100 h-8 text-xs focus-visible:ring-emerald-500"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[10px] text-zinc-500 uppercase font-bold text-rose-500">止损价格 (SL)</label>
            <Input
              type="number"
              placeholder="可选"
              value={sl}
              onChange={(e) => setSl(e.target.value)}
              className="bg-zinc-900 border-zinc-800 text-zinc-100 h-8 text-xs focus-visible:ring-rose-500"
            />
          </div>
        </div>

        <div className="flex justify-between text-[10px] text-zinc-500">
          <span>预估保证金: {margin.toFixed(2)} USDT</span>
          <span>当前价格: {formatPrice(currentPrice)}</span>
        </div>

        <div className="grid grid-cols-2 gap-3 pt-2">
          <Button
            onClick={() => onOrder(
              'long', 
              leverage, 
              amount, 
              orderType === 'market' ? currentPrice : limitPrice,
              tp ? Number(tp) : undefined,
              sl ? Number(sl) : undefined,
              orderType === 'limit'
            )}
            className="bg-emerald-600 hover:bg-emerald-700 text-white flex items-center gap-2 h-10 font-bold"
          >
            <TrendingUp className="w-4 h-4" />
            做多
          </Button>
          <Button
            onClick={() => onOrder(
              'short', 
              leverage, 
              amount, 
              orderType === 'market' ? currentPrice : limitPrice,
              tp ? Number(tp) : undefined,
              sl ? Number(sl) : undefined,
              orderType === 'limit'
            )}
            className="bg-rose-600 hover:bg-rose-700 text-white flex items-center gap-2 h-10 font-bold"
          >
            <TrendingDown className="w-4 h-4" />
            做空
          </Button>
        </div>

        <div className="pt-4 border-t border-zinc-800">
          <div className="flex flex-wrap gap-2">
            {[10, 25, 50, 75, 100].map((pct) => (
              <Button
                key={pct}
                variant="outline"
                size="sm"
                className="flex-1 text-[10px] h-7 border-zinc-800 hover:bg-zinc-800"
                onClick={() => setAmount(Math.floor(balance * leverage * (pct / 100)))}
              >
                {pct}%
              </Button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
