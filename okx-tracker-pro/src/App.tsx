/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { Header } from './components/Header';
import { TradingChart } from './components/TradingChart';
import { TradingPanel } from './components/TradingPanel';
import { PositionList } from './components/PositionList';
import { SignalLog } from './components/SignalLog';
import { SignalDetail } from './components/SignalDetail';
import { SettingsSheet } from './components/SettingsSheet';
import { okxService } from './lib/okx-service';
import { IndicatorEngine } from './lib/indicator-engine';
import { tradingEngine } from './lib/trading-engine';
import { AIService } from './lib/ai-service';
import { Candle, Signal, TradingState } from './types';
import { Toaster, toast } from 'sonner';
import { Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function App() {
  const [symbol, setSymbol] = useState('BTC-USDT-SWAP');
  const [interval, setIntervalTime] = useState('1m');
  const [instruments, setInstruments] = useState<{ id: string, name: string }[]>([]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [tradingState, setTradingState] = useState<TradingState>(tradingEngine.getState());
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);
  const [currentPrice, setCurrentPrice] = useState(0);
  const [showSettings, setShowSettings] = useState(false);
  const [config, setConfig] = useState({
    strongOnly: false,
    showCandlestick: true,
    showTrend: true,
    sensitivity: 50,
    sound: true,
    autoTrade: false,
    autoTradeAmount: 100,
    autoTradeLeverage: 5
  });

  // Use a ref to always have the latest config in the subscription callback
  const latestConfig = useRef(config);
  useEffect(() => {
    latestConfig.current = config;
  }, [config]);

  // Initialize data
  useEffect(() => {
    okxService.connect();
    
    const init = async () => {
      try {
        const insts = await okxService.fetchInstruments();
        setInstruments(insts);
        
        // Ensure the current symbol is in the list, or default to the first one
        let targetSymbol = symbol;
        if (insts.length > 0 && !insts.find(i => i.id === symbol)) {
          targetSymbol = insts[0].id;
          setSymbol(targetSymbol);
        }

        const history = await okxService.fetchHistory(targetSymbol, interval, 100);
        setCandles(history);
        if (history.length > 0) {
          const lastCandle = history[history.length - 1];
          setCurrentPrice(lastCandle.close);
          const initialSignals = IndicatorEngine.analyze(history, latestConfig.current);
          setSignals(initialSignals);

          // If autoTrade is on, check if the latest signal is on the current candle and trade it
          if (latestConfig.current.autoTrade && initialSignals.length > 0) {
            const latestSignal = initialSignals[0];
            if (latestSignal.time === lastCandle.time && latestSignal.confidence === 'high') {
              const side = latestSignal.type === 'bullish' ? 'long' : latestSignal.type === 'bearish' ? 'short' : null;
              if (side) {
                console.log(`[AutoTrade] Triggering initial trade for ${targetSymbol} based on existing signal: ${latestSignal.title}`);
                handleOrder(
                  targetSymbol,
                  side,
                  latestConfig.current.autoTradeLeverage,
                  latestConfig.current.autoTradeAmount,
                  lastCandle.close,
                  latestSignal.takeProfit,
                  latestSignal.stopLoss,
                  false
                );
                toast.success(`[自动交易] 已根据当前信号 "${latestSignal.title}" 开仓`);
              }
            }
          }
        }
      } catch (error: any) {
        console.error('Failed to fetch history:', error);
        toast.error(`获取历史数据失败: ${error.message || '未知错误'}`);
      }
    };

    init();

    const unsubscribe = okxService.subscribe(symbol, interval, (candle, isFinal) => {
      setCandles(prev => {
        const last = prev[prev.length - 1];
        let updated: Candle[];
        
        if (last && last.time === candle.time) {
          updated = [...prev.slice(0, -1), candle];
        } else {
          updated = [...prev, candle].slice(-200);
        }

        // Analyze signals on every tick for real-time feedback
        const newSignals = IndicatorEngine.analyze(updated, latestConfig.current);
        setSignals(prevSignals => {
          const existingIds = new Set(prevSignals.map(s => s.id));
          const uniqueNew = newSignals.filter(s => !existingIds.has(s.id));
          
          if (uniqueNew.length > 0) {
            uniqueNew.forEach(s => {
              if (s.confidence === 'high') {
                toast.info(`新信号: ${s.title}`, {
                  description: s.description,
                });

                if (latestConfig.current.autoTrade) {
                  // 1. Check for reverse signals to close existing positions
                  const existingPos = tradingEngine.getState().positions.find(p => p.symbol === symbol);
                  if (existingPos) {
                    const isOpposite = (existingPos.side === 'long' && s.type === 'bearish') || 
                                       (existingPos.side === 'short' && s.type === 'bullish');
                    if (isOpposite && s.confidence === 'high') {
                      console.log(`[AutoTrade] Closing position for ${symbol} due to reverse signal: ${s.title}`);
                      tradingEngine.closePosition(existingPos.id, candle.close, `反向信号平仓: ${s.title}`);
                      setTradingState({ ...tradingEngine.getState() });
                      toast.info(`[自动交易] 检测到反向强信号，已自动平仓 ${symbol}`);
                    }
                  }

                  // 2. Open new position
                  const side = s.type === 'bullish' ? 'long' : s.type === 'bearish' ? 'short' : null;
                  if (side) {
                    // Only open if we don't already have a position in the same direction
                    const hasSameSidePos = existingPos && existingPos.side === side;
                    
                    if (!hasSameSidePos) {
                      console.log(`[AutoTrade] Triggering trade for ${symbol} based on signal: ${s.title}`);
                      handleOrder(
                        symbol,
                        side, 
                        latestConfig.current.autoTradeLeverage, 
                        latestConfig.current.autoTradeAmount, 
                        candle.close,
                        s.takeProfit,
                        s.stopLoss,
                        false
                      );
                      toast.success(`[自动交易] 已根据信号 "${s.title}" 开仓`);
                    }
                  } else {
                    console.log(`[AutoTrade] Signal ${s.title} is neutral, skipping trade.`);
                  }
                }
              }
            });
            return [...uniqueNew, ...prevSignals].sort((a, b) => b.time - a.time).slice(0, 50);
          }
          return prevSignals;
        });

        return updated;
      });
      setCurrentPrice(candle.close);
    });

    return () => unsubscribe();
  }, [symbol, interval]);

  // Update PnL periodically
  useEffect(() => {
    const timer = setInterval(() => {
      tradingEngine.updatePnL({ [symbol]: currentPrice });
      setTradingState({ ...tradingEngine.getState() });
    }, 1000);
    return () => clearInterval(timer);
  }, [currentPrice, symbol]);

  const handleOrder = useCallback((
    orderSymbol: string,
    side: 'long' | 'short', 
    leverage: number, 
    amount: number, 
    price: number,
    tp?: number,
    sl?: number,
    isLimit: boolean = false
  ) => {
    try {
      tradingEngine.openPosition(orderSymbol, side, leverage, amount, price, tp, sl, isLimit);
      setTradingState({ ...tradingEngine.getState() });
      
      if (isLimit) {
        toast.success(`限价单已挂出: ${side === 'long' ? '做多' : '做空'} ${orderSymbol} @ ${price}`);
      } else {
        toast.success(`开仓成功: ${side === 'long' ? '做多' : '做空'} ${orderSymbol}`);
      }
    } catch (error: any) {
      console.error('Order failed:', error);
      toast.error(error.message || '下单失败');
    }
  }, []);

  const handleClosePosition = useCallback((id: string) => {
    tradingEngine.closePosition(id, currentPrice);
    setTradingState({ ...tradingEngine.getState() });
    toast.success('平仓成功');
  }, [currentPrice]);

  const handleCancelOrder = useCallback((id: string) => {
    tradingEngine.cancelOrder(id);
    setTradingState({ ...tradingEngine.getState() });
    toast.info('挂单已取消');
  }, []);

  const handleResetAccount = useCallback(() => {
    console.log('[App] handleResetAccount triggered');
    tradingEngine.reset();
    const newState = tradingEngine.getState();
    console.log('[App] New state after reset:', newState);
    setTradingState({ ...newState });
    toast.success('账户已重置，正在刷新页面...');
    
    // Force a reload to ensure everything is clean
    setTimeout(() => {
      window.location.reload();
    }, 1000);
  }, []);

  // Watch for new history items to generate AI reviews
  useEffect(() => {
    const lastHistory = tradingState.history[0];
    if (lastHistory && !lastHistory.review) {
      const generateReview = async () => {
        try {
          const review = await AIService.getTradeReview(lastHistory);
          // Update the history item in the engine
          lastHistory.review = review;
          tradingEngine.save(); // Assuming I make save public or handle it
          setTradingState({ ...tradingEngine.getState() });
        } catch (e) {
          console.error('Failed to generate review', e);
        }
      };
      generateReview();
    }
  }, [tradingState.history.length]);

  return (
    <div className="flex flex-col h-screen bg-black text-zinc-100 overflow-hidden font-sans">
      <Header 
        symbol={symbol} 
        interval={interval}
        instruments={instruments}
        onSymbolChange={setSymbol} 
        onIntervalChange={setIntervalTime}
        price={currentPrice} 
        change24h={candles.length > 0 ? ((currentPrice - candles[0].close) / candles[0].close) * 100 : 0}
      />

      <div className="absolute top-16 right-84 z-10">
        <Button 
          variant="outline" 
          size="sm" 
          className="bg-zinc-900/80 border-zinc-800 backdrop-blur-sm"
          onClick={() => setShowSettings(true)}
        >
          <Settings2 className="w-4 h-4 mr-2" />
          扫描设置
        </Button>
      </div>
      
      <main className="flex-1 flex overflow-hidden p-1 gap-1">
        {/* Left: Chart */}
        <div className="flex-1 flex flex-col min-w-0 bg-zinc-950 rounded-lg border border-zinc-900 overflow-hidden">
          <div className="flex-1 relative">
            <TradingChart 
              data={candles} 
              signals={signals} 
              positions={tradingState.positions}
              onSignalClick={setSelectedSignal}
            />
          </div>
          
          {/* Bottom: Positions */}
          <div className="h-64 border-t border-zinc-900">
            <PositionList 
              positions={tradingState.positions} 
              history={tradingState.history}
              pendingOrders={tradingState.pendingOrders}
              onClose={handleClosePosition}
              onCancelOrder={handleCancelOrder}
            />
          </div>
        </div>

        {/* Right: Sidebar */}
        <div className="w-80 flex flex-col gap-1 shrink-0 overflow-y-auto pr-1 custom-scrollbar">
          <div className="shrink-0">
            <TradingPanel 
              balance={tradingState.balance} 
              currentPrice={currentPrice} 
              symbol={symbol}
              onOrder={(side, leverage, amount, price, tp, sl, isLimit) => 
                handleOrder(symbol, side, leverage, amount, price, tp, sl, isLimit)
              }
            />
          </div>
          <div className="shrink-0">
            <SignalLog 
              signals={signals} 
              onSignalClick={setSelectedSignal}
            />
          </div>
        </div>
      </main>

      <SignalDetail 
        signal={selectedSignal} 
        onClose={() => setSelectedSignal(null)} 
      />

      <SettingsSheet 
        open={showSettings} 
        onOpenChange={setShowSettings}
        config={config}
        onConfigChange={setConfig}
        onResetAccount={handleResetAccount}
      />
      
      <Toaster theme="dark" position="top-right" />
    </div>
  );
}
