"use client";
import { useEffect, useState, useCallback, useRef } from 'react';
import { Header } from './Header';
import { TradingChart } from './TradingChart';
import { TradingPanel } from './TradingPanel';
import { PositionList } from './PositionList';
import { SignalLog } from './SignalLog';
import { SignalDetail } from './SignalDetail';
import { SettingsSheet } from './SettingsSheet';
import { okxService } from '@/lib/tracker/okx-service';
import { IndicatorEngine } from '@/lib/tracker/indicator-engine';
import { tradingEngine } from '@/lib/tracker/trading-engine';
import { AIService } from '@/lib/tracker/ai-service';
import { Candle, Signal, TradingState } from '@/lib/tracker/types';
import { Toaster, toast } from 'sonner';
import { Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function TrackerApp() {
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
    strongOnly: false, showCandlestick: true, showTrend: true,
    sensitivity: 50, sound: true, autoTrade: false,
    autoTradeAmount: 100, autoTradeLeverage: 5
  });

  const latestConfig = useRef(config);
  useEffect(() => { latestConfig.current = config; }, [config]);

  const handleOrder = useCallback((
    orderSymbol: string, side: 'long' | 'short', leverage: number, amount: number,
    price: number, tp?: number, sl?: number, isLimit: boolean = false, reason?: string
  ) => {
    try {
      tradingEngine.openPosition(orderSymbol, side, leverage, amount, price, tp, sl, isLimit, reason);
      setTradingState({ ...tradingEngine.getState() });
      if (isLimit) toast.success(`限价单已挂出: ${side === 'long' ? '做多' : '做空'} ${orderSymbol} @ ${price}`);
      else toast.success(`开仓成功: ${side === 'long' ? '做多' : '做空'} ${orderSymbol}`);
    } catch (error: any) {
      console.error('Order failed:', error);
      toast.error(error.message || '下单失败');
    }
  }, []);

  useEffect(() => {
    okxService.connect();
    const init = async () => {
      try {
        const insts = await okxService.fetchInstruments();
        setInstruments(insts);
        let targetSymbol = symbol;
        if (insts.length > 0 && !insts.find(i => i.id === symbol)) {
          targetSymbol = insts[0].id; setSymbol(targetSymbol);
        }
        const history = await okxService.fetchHistory(targetSymbol, interval, 100);
        setCandles(history);
        if (history.length > 0) {
          const lastCandle = history[history.length - 1];
          setCurrentPrice(lastCandle.close);
          const initialSignals = IndicatorEngine.analyze(history, latestConfig.current);
          setSignals(initialSignals);
          if (latestConfig.current.autoTrade && initialSignals.length > 0) {
            const s = initialSignals[0];
            if (s.time === lastCandle.time && s.confidence === 'high') {
              const side = s.type === 'bullish' ? 'long' : s.type === 'bearish' ? 'short' : null;
              if (side) {
                handleOrder(targetSymbol, side, latestConfig.current.autoTradeLeverage, latestConfig.current.autoTradeAmount, lastCandle.close, s.takeProfit, s.stopLoss, false, `[自动跟单] ${s.title}: ${s.description}`);
                toast.success(`[自动交易] 已根据信号 "${s.title}" 开仓`);
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
        if (last && last.time === candle.time) updated = [...prev.slice(0, -1), candle];
        else updated = [...prev, candle].slice(-200);
        const newSignals = IndicatorEngine.analyze(updated, latestConfig.current);
        setSignals(prevSignals => {
          const existingIds = new Set(prevSignals.map(s => s.id));
          const uniqueNew = newSignals.filter(s => !existingIds.has(s.id));
          if (uniqueNew.length > 0) {
            uniqueNew.forEach(s => {
              if (s.confidence === 'high') {
                toast.info(`新信号: ${s.title}`, { description: s.description });
                if (latestConfig.current.autoTrade) {
                  const existingPos = tradingEngine.getState().positions.find(p => p.symbol === symbol);
                  if (existingPos) {
                    const isOpp = (existingPos.side === 'long' && s.type === 'bearish') || (existingPos.side === 'short' && s.type === 'bullish');
                    if (isOpp) { tradingEngine.closePosition(existingPos.id, candle.close, `反向信号平仓: ${s.title}`); setTradingState({ ...tradingEngine.getState() }); toast.info(`[自动交易] 反向信号平仓 ${symbol}`); }
                  }
                  const side = s.type === 'bullish' ? 'long' : s.type === 'bearish' ? 'short' : null;
                  if (side) {
                    const hasSame = existingPos && existingPos.side === side;
                    if (!hasSame) {
                      handleOrder(symbol, side, latestConfig.current.autoTradeLeverage, latestConfig.current.autoTradeAmount, candle.close, s.takeProfit, s.stopLoss, false, `[自动跟单] ${s.title}: ${s.description}`);
                      toast.success(`[自动交易] 已根据信号 "${s.title}" 开仓`);
                    }
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
  }, [symbol, interval, handleOrder]);

  useEffect(() => {
    const timer = setInterval(() => { tradingEngine.updatePnL({ [symbol]: currentPrice }); setTradingState({ ...tradingEngine.getState() }); }, 1000);
    return () => clearInterval(timer);
  }, [currentPrice, symbol]);

  const handleClosePosition = useCallback((id: string) => { tradingEngine.closePosition(id, currentPrice); setTradingState({ ...tradingEngine.getState() }); toast.success('平仓成功'); }, [currentPrice]);
  const handleCancelOrder = useCallback((id: string) => { tradingEngine.cancelOrder(id); setTradingState({ ...tradingEngine.getState() }); toast.info('挂单已取消'); }, []);
  const handleResetAccount = useCallback(() => { tradingEngine.reset(); setTradingState({ ...tradingEngine.getState() }); toast.success('账户已重置'); setTimeout(() => window.location.reload(), 1000); }, []);

  useEffect(() => {
    const last = tradingState.history[0];
    if (last && !last.review) { AIService.getTradeReview(last).then(r => { last.review = r; tradingEngine.save(); setTradingState({ ...tradingEngine.getState() }); }).catch(() => {}); }
  }, [tradingState.history.length]);

  return (
    <div className="flex flex-col h-[calc(100vh-120px)] bg-black text-zinc-100 overflow-hidden font-sans rounded-lg border border-zinc-800">
      <Header symbol={symbol} interval={interval} instruments={instruments}
        onSymbolChange={setSymbol} onIntervalChange={setIntervalTime}
        price={currentPrice} change24h={candles.length > 0 ? ((currentPrice - candles[0].close) / candles[0].close) * 100 : 0} />
      <div className="absolute top-16 right-84 z-10">
        <Button variant="outline" size="sm" className="bg-zinc-900/80 border-zinc-800 backdrop-blur-sm" onClick={() => setShowSettings(true)}>
          <Settings2 className="w-4 h-4 mr-2" />扫描设置
        </Button>
      </div>
      <main className="flex-1 flex overflow-hidden p-1 gap-1">
        <div className="flex-1 flex flex-col min-w-0 bg-zinc-950 rounded-lg border border-zinc-900 overflow-hidden">
          <div className="flex-1 relative">
            <TradingChart data={candles} signals={signals} positions={tradingState.positions} onSignalClick={setSelectedSignal} />
          </div>
          <div className="h-64 border-t border-zinc-900">
            <PositionList positions={tradingState.positions} history={tradingState.history} pendingOrders={tradingState.pendingOrders} onClose={handleClosePosition} onCancelOrder={handleCancelOrder} />
          </div>
        </div>
        <div className="w-80 flex flex-col gap-1 shrink-0 overflow-y-auto pr-1">
          <div className="shrink-0">
            <TradingPanel balance={tradingState.balance} currentPrice={currentPrice} symbol={symbol}
              onOrder={(side, leverage, amount, price, tp, sl, isLimit, reason) => handleOrder(symbol, side, leverage, amount, price, tp, sl, isLimit, reason)} />
          </div>
          <div className="shrink-0">
            <SignalLog signals={signals} onSignalClick={setSelectedSignal} />
          </div>
        </div>
      </main>
      <SignalDetail signal={selectedSignal} onClose={() => setSelectedSignal(null)} />
      <SettingsSheet open={showSettings} onOpenChange={setShowSettings} config={config} onConfigChange={setConfig} onResetAccount={handleResetAccount} />
      <Toaster theme="dark" position="top-right" />
    </div>
  );
}
