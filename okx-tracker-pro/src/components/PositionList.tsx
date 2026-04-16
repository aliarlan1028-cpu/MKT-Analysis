/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Position, TradeHistory, PendingOrder } from '../types';
import { XCircle, History, LayoutList, Clock, Cpu } from 'lucide-react';
import { formatPrice, formatPercent } from '@/lib/utils';

interface PositionListProps {
  positions: Position[];
  history: TradeHistory[];
  pendingOrders: PendingOrder[];
  onClose: (id: string) => void;
  onCancelOrder: (id: string) => void;
}

export const PositionList: React.FC<PositionListProps> = ({ 
  positions = [], 
  history = [], 
  pendingOrders = [], 
  onClose, 
  onCancelOrder 
}) => {
  return (
    <Card className="bg-zinc-950 border-zinc-800 text-zinc-100 h-full flex flex-col">
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <LayoutList className="w-4 h-4 text-zinc-400" />
          持仓与历史
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 p-0 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="p-4 space-y-6">
            {/* Active Positions */}
            <section>
              <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-3 flex items-center gap-2">
                当前持仓 ({positions.length})
              </h3>
              <div className="space-y-2">
                {positions.map((pos) => (
                  <div key={pos.id} className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold">{pos.symbol}</span>
                          <Badge className={pos.side === 'long' ? 'bg-emerald-900/30 text-emerald-500' : 'bg-rose-900/30 text-rose-500'}>
                            {pos.side === 'long' ? '多' : '空'} {pos.leverage}x
                          </Badge>
                        </div>
                        <div className="text-[10px] text-zinc-500 mt-1">
                          开仓价: {formatPrice(pos.entryPrice)}
                        </div>
                        {(pos.tp || pos.sl) && (
                          <div className="flex gap-2 mt-1">
                            {pos.tp && <span className="text-[9px] text-emerald-500/80">止盈: {formatPrice(pos.tp)}</span>}
                            {pos.sl && <span className="text-[9px] text-rose-500/80">止损: {formatPrice(pos.sl)}</span>}
                          </div>
                        )}
                      </div>
                      <div className="text-right">
                        <div className={`text-xs font-bold ${pos.pnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {pos.pnl >= 0 ? '+' : ''}{pos.pnl.toFixed(2)} USDT
                        </div>
                        <div className={`text-[10px] ${pos.pnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                          {formatPercent(pos.pnlPercent)}
                        </div>
                      </div>
                    </div>
                    <Button
                      variant="destructive"
                      size="sm"
                      className="w-full h-7 text-[10px] bg-rose-900/20 hover:bg-rose-900/40 text-rose-500 border border-rose-900/50"
                      onClick={() => onClose(pos.id)}
                    >
                      市价平仓
                    </Button>
                  </div>
                ))}
                {positions.length === 0 && (
                  <div className="text-center py-4 text-zinc-600 text-[10px]">暂无持仓</div>
                )}
              </div>
            </section>

            {/* Pending Orders */}
            <section>
              <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-3 flex items-center gap-2">
                <Clock className="w-3 h-3" /> 挂单中 ({pendingOrders.length})
              </h3>
              <div className="space-y-2">
                {pendingOrders.map((order) => (
                  <div key={order.id} className="p-3 rounded-lg bg-zinc-900/40 border border-zinc-800/50 border-dashed">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-zinc-300">{order.symbol}</span>
                          <Badge variant="outline" className={`text-[9px] h-4 ${order.side === 'long' ? 'border-emerald-500/50 text-emerald-500' : 'border-rose-500/50 text-rose-500'}`}>
                            限价{order.side === 'long' ? '多' : '空'} {order.leverage}x
                          </Badge>
                        </div>
                        <div className="text-[10px] text-zinc-500 mt-1">
                          委托价: <span className="text-zinc-300 font-mono">{formatPrice(order.price)}</span>
                        </div>
                        {(order.tp || order.sl) && (
                          <div className="flex gap-2 mt-1">
                            {order.tp && <span className="text-[9px] text-emerald-500/60">止盈: {formatPrice(order.tp)}</span>}
                            {order.sl && <span className="text-[9px] text-rose-500/60">止损: {formatPrice(order.sl)}</span>}
                          </div>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-zinc-500 hover:text-rose-500 hover:bg-rose-500/10"
                        onClick={() => onCancelOrder(order.id)}
                      >
                        <XCircle className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                ))}
                {pendingOrders.length === 0 && (
                  <div className="text-center py-4 text-zinc-700 text-[10px]">暂无挂单</div>
                )}
              </div>
            </section>

            {/* History */}
            <section>
              <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-3 flex items-center gap-2">
                <History className="w-3 h-3" /> 最近成交
              </h3>
              <div className="space-y-2">
                {history.map((h) => (
                  <div key={h.id} className="p-2 rounded bg-zinc-900/30 border border-zinc-800/50">
                    <div className="flex justify-between items-center mb-1">
                      <div>
                        <div className="text-[10px] font-bold">{h.symbol}</div>
                        <div className="text-[9px] text-zinc-600">
                          {new Date(h.timestamp).toLocaleTimeString()}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`text-[10px] font-bold ${h.pnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {h.pnl >= 0 ? '+' : ''}{h.pnl.toFixed(2)}
                        </div>
                        <div className="text-[9px] text-zinc-600">
                          {h.side === 'long' ? '多' : '空'} {h.leverage}x
                        </div>
                      </div>
                    </div>
                    
                    {/* AI Review Section */}
                    <div className="mt-2 pt-2 border-t border-zinc-800/50">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Cpu className="w-2.5 h-2.5 text-emerald-500" />
                        <span className="text-[9px] font-bold text-zinc-500 uppercase">AI 复盘总结</span>
                      </div>
                      {h.review ? (
                        <p className="text-[10px] text-zinc-400 leading-relaxed italic">
                          "{h.review}"
                        </p>
                      ) : (
                        <div className="flex items-center gap-2 py-1">
                          <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                          <span className="text-[9px] text-zinc-600">正在生成复盘分析...</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {history.length === 0 && (
                  <div className="text-center py-4 text-zinc-600 text-[10px]">暂无历史记录</div>
                )}
              </div>
            </section>
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
};
