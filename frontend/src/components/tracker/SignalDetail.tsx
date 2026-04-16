/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Signal } from '@/lib/tracker/types';
import { TrendingUp, TrendingDown, Info, Lightbulb, History, CheckCircle2, Target, ShieldAlert, TrendingUp as ProfitIcon, Sparkles } from 'lucide-react';
import { formatPrice } from '@/lib/tracker/utils';

interface SignalDetailProps {
  signal: Signal | null;
  onClose: () => void;
}

export const SignalDetail: React.FC<SignalDetailProps> = ({ signal, onClose }) => {
  if (!signal) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-zinc-950 border border-zinc-800 rounded-xl w-full max-w-md overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className={`h-1.5 w-full ${
          signal.type === 'bullish' ? 'bg-emerald-500' : 
          signal.type === 'bearish' ? 'bg-rose-500' : 
          'bg-yellow-500'
        }`} />
        
        <div className="p-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <Badge variant="outline" className="mb-2 text-[10px] uppercase tracking-wider text-zinc-500">
                {signal.category}
              </Badge>
              <h2 className="text-xl font-bold flex items-center gap-2">
                {signal.type === 'bullish' ? <TrendingUp className="text-emerald-500" /> :
                 signal.type === 'bearish' ? <TrendingDown className="text-rose-500" /> :
                 <Info className="text-yellow-500" />}
                {signal.title}
              </h2>
            </div>
            <Badge className={
              signal.confidence === 'high' ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/50' :
              'bg-blue-500/10 text-blue-500 border-blue-500/50'
            }>
              {signal.confidence === 'high' ? '高置信度' : '中置信度'}
            </Badge>
          </div>

          <div className="space-y-6">
            <section>
              <h3 className="text-xs font-bold text-zinc-400 mb-2 flex items-center gap-2">
                <Info className="w-3 h-3" /> 事件解读
              </h3>
              <p className="text-sm text-zinc-300 leading-relaxed">
                {signal.description}
              </p>
            </section>

            {(signal.entryPrice || signal.stopLoss || signal.takeProfit) && (
              <section className="grid grid-cols-3 gap-2">
                {signal.entryPrice && (
                  <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                    <div className="text-[9px] text-zinc-500 uppercase flex items-center gap-1 mb-1">
                      <Target className="w-2.5 h-2.5" /> 入场价
                    </div>
                    <div className="text-xs font-mono font-bold text-zinc-100">
                      {formatPrice(signal.entryPrice)}
                    </div>
                  </div>
                )}
                {signal.stopLoss && (
                  <div className="p-2 rounded bg-rose-950/20 border border-rose-900/30">
                    <div className="text-[9px] text-rose-500 uppercase flex items-center gap-1 mb-1">
                      <ShieldAlert className="w-2.5 h-2.5" /> 止损
                    </div>
                    <div className="text-xs font-mono font-bold text-rose-400">
                      {formatPrice(signal.stopLoss)}
                    </div>
                  </div>
                )}
                {signal.takeProfit && (
                  <div className="p-2 rounded bg-emerald-950/20 border border-emerald-900/30">
                    <div className="text-[9px] text-emerald-500 uppercase flex items-center gap-1 mb-1">
                      <ProfitIcon className="w-2.5 h-2.5" /> 止盈
                    </div>
                    <div className="text-xs font-mono font-bold text-emerald-400">
                      {formatPrice(signal.takeProfit)}
                    </div>
                  </div>
                )}
              </section>
            )}

            {signal.aiAnalysis && (
              <section>
                <h3 className="text-xs font-bold text-purple-400 mb-2 flex items-center gap-2">
                  <Sparkles className="w-3 h-3" /> AI 深度分析
                </h3>
                <div className="p-3 rounded-lg bg-purple-950/10 border border-purple-900/30 text-xs text-purple-200 leading-relaxed italic">
                  {signal.aiAnalysis}
                </div>
              </section>
            )}

            <section>
              <h3 className="text-xs font-bold text-zinc-400 mb-2 flex items-center gap-2">
                <Lightbulb className="w-3 h-3 text-yellow-500" /> 策略建议
              </h3>
              <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 text-sm text-zinc-200">
                {signal.suggestion}
              </div>
            </section>

            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 rounded-lg bg-zinc-900/50 border border-zinc-800">
                <h4 className="text-[10px] text-zinc-500 uppercase mb-1 flex items-center gap-1">
                  <History className="w-3 h-3" /> 历史胜率
                </h4>
                <div className="text-lg font-mono font-bold text-zinc-100">
                  {signal.confidence === 'high' ? '68.5%' : '54.2%'}
                </div>
              </div>
              <div className="p-3 rounded-lg bg-zinc-900/50 border border-zinc-800">
                <h4 className="text-[10px] text-zinc-500 uppercase mb-1 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> 确认建议
                </h4>
                <div className="text-[11px] text-zinc-300">
                  {signal.type === 'bullish' ? '等待成交量放大确认' : '关注RSI是否背离'}
                </div>
              </div>
            </div>
          </div>

          <Button 
            className="w-full mt-8 bg-zinc-100 text-zinc-950 hover:bg-zinc-200 font-bold"
            onClick={onClose}
          >
            我知道了
          </Button>
        </div>
      </div>
    </div>
  );
};
