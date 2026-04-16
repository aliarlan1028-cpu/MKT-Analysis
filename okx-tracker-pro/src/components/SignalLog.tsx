/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Signal } from '../types';
import { AlertCircle, TrendingUp, TrendingDown, Info, Zap, Target } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { formatPrice } from '@/lib/utils';

interface SignalLogProps {
  signals: Signal[];
  onSignalClick: (signal: Signal) => void;
}

export const SignalLog: React.FC<SignalLogProps> = ({ signals = [], onSignalClick }) => {
  return (
    <Card className="bg-zinc-950 border-zinc-800 text-zinc-100 flex flex-col">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Zap className="w-4 h-4 text-yellow-500" />
          智能信号日志
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 p-0 overflow-hidden">
        <ScrollArea className="max-h-[400px] px-4 pb-4">
          <div className="space-y-3">
            <AnimatePresence initial={false}>
              {signals.map((signal) => (
                <motion.div
                  key={signal.id}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className="cursor-pointer"
                  onClick={() => onSignalClick(signal)}
                >
                  <div className={`p-3 rounded-lg border bg-zinc-900/50 hover:bg-zinc-900 transition-colors ${
                    signal.type === 'bullish' ? 'border-emerald-900/50' : 
                    signal.type === 'bearish' ? 'border-rose-900/50' : 
                    'border-zinc-800'
                  }`}>
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <div className="flex items-center gap-2">
                        {signal.type === 'bullish' ? <TrendingUp className="w-3 h-3 text-emerald-500" /> :
                         signal.type === 'bearish' ? <TrendingDown className="w-3 h-3 text-rose-500" /> :
                         <Info className="w-3 h-3 text-zinc-400" />}
                        <span className="text-xs font-bold">{signal.title}</span>
                      </div>
                      <Badge variant="outline" className={`text-[10px] h-4 px-1 ${
                        signal.confidence === 'high' ? 'border-yellow-500 text-yellow-500' :
                        signal.confidence === 'medium' ? 'border-blue-500 text-blue-500' :
                        'border-zinc-600 text-zinc-500'
                      }`}>
                        {signal.confidence === 'high' ? '强信号' : '中信号'}
                      </Badge>
                      {signal.category === 'advanced' && (
                        <Badge className="text-[9px] h-4 px-1 bg-purple-900/30 text-purple-400 border-purple-800/50">
                          组合
                        </Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-zinc-400 line-clamp-2 leading-relaxed">
                      {signal.description}
                    </p>
                    {signal.entryPrice && (
                      <div className="mt-2 flex items-center gap-1.5">
                        <Target className="w-2.5 h-2.5 text-zinc-500" />
                        <span className="text-[10px] text-zinc-500">建议入场:</span>
                        <span className="text-[10px] font-mono font-bold text-zinc-300">{formatPrice(signal.entryPrice)}</span>
                      </div>
                    )}
                    <div className="mt-2 flex items-center justify-between text-[10px]">
                      <span className="text-zinc-600">
                        {new Date(signal.time * 1000).toLocaleTimeString()}
                      </span>
                      <span className={`font-medium ${
                        signal.type === 'bullish' ? 'text-emerald-500' :
                        signal.type === 'bearish' ? 'text-rose-500' :
                        'text-zinc-400'
                      }`}>
                        查看详情 →
                      </span>
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            {signals.length === 0 && (
              <div className="flex flex-col items-center justify-center py-12 text-zinc-600">
                <AlertCircle className="w-8 h-8 mb-2 opacity-20" />
                <p className="text-xs">暂无新信号，等待行情波动...</p>
              </div>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
};
