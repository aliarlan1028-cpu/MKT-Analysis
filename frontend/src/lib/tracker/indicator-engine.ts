/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Candle, Signal } from '@/lib/tracker/types';
import * as TI from 'technicalindicators';
import { formatPrice } from '@/lib/tracker/utils';

export class IndicatorEngine {
  static analyze(candles: Candle[], config: any = {}): Signal[] {
    if (candles.length < 50) return [];

    const signals: Signal[] = [];
    
    // 1. Candlestick Patterns
    if (config.showCandlestick !== false) {
      this.detectCandlestickPatterns(candles, signals);
    }

    // 2. Trend Indicators
    if (config.showTrend !== false) {
      this.detectTrendSignals(candles, signals);
    }

    // 3. Momentum Signals
    this.detectMomentumSignals(candles, signals);

    // 4. Volatility Signals
    this.detectVolatilitySignals(candles, signals);

    // 5. Volume Signals
    this.detectVolumeSignals(candles, signals);

    // 6. MACD Signals
    if (config.showMacd !== false) {
      this.detectMACDSignals(candles, signals);
    }

    // 7. Combination Signals (Advanced)
    if (config.showAdvanced !== false) {
      this.detectCombinationSignals(candles, signals);
    }

    // 8. Support & Resistance Signals
    this.detectSupportResistanceSignals(candles, signals);

    // Filter by confidence if requested
    if (config.strongOnly) {
      return signals.filter(s => s.confidence === 'high');
    }

    return signals;
  }

  private static detectCandlestickPatterns(candles: Candle[], signals: Signal[]) {
    const last = candles[candles.length - 1];
    const data = {
      open: candles.map(c => c.open),
      high: candles.map(c => c.high),
      low: candles.map(c => c.low),
      close: candles.map(c => c.close),
    };

    // Bullish Engulfing
    if (TI.bullishengulfingpattern(data)) {
      const entry = last.close;
      signals.push({
        id: `bull-eng-${last.time}`,
        time: last.time,
        type: 'bullish',
        title: '看涨吞没 (Bullish Engulfing)',
        description: '当前K线实体完全覆盖前一根阴线实体，显示买盘强劲反转。',
        suggestion: `建议入场价: ${formatPrice(entry)}。止损参考: ${formatPrice(last.low)}。`,
        confidence: 'high',
        category: 'candlestick',
        entryPrice: entry,
        stopLoss: last.low * 0.995,
        takeProfit: entry + (entry - last.low) * 2
      });
    }

    // Bearish Engulfing
    if (TI.bearishengulfingpattern(data)) {
      const entry = last.close;
      signals.push({
        id: `bear-eng-${last.time}`,
        time: last.time,
        type: 'bearish',
        title: '看跌吞没 (Bearish Engulfing)',
        description: '当前K线实体完全覆盖前一根阳线实体，显示卖压沉重。',
        suggestion: `建议入场价: ${formatPrice(entry)}。止损参考: ${formatPrice(last.high)}。`,
        confidence: 'high',
        category: 'candlestick',
        entryPrice: entry,
        stopLoss: last.high * 1.005,
        takeProfit: entry - (last.high - entry) * 2
      });
    }

    // Hammer
    if (TI.hammerpattern(data)) {
      signals.push({
        id: `hammer-${last.time}`,
        time: last.time,
        type: 'bullish',
        title: '锤头线 (Hammer)',
        description: '下影线较长，实体较小，出现在下跌趋势末端提示反转。',
        suggestion: '潜在底部信号，结合成交量放大可提高确认度。',
        confidence: 'medium',
        category: 'candlestick'
      });
    }

    // Morning Star
    if (TI.morningstar(data)) {
      signals.push({
        id: `morning-star-${last.time}`,
        time: last.time,
        type: 'bullish',
        title: '晨星 (Morning Star)',
        description: '三根K线组成的底部反转形态，预示着下跌趋势的终结。',
        suggestion: '强力看涨信号，建议关注反转机会。',
        confidence: 'high',
        category: 'candlestick'
      });
    }

    // Evening Star
    if (TI.eveningstar(data)) {
      signals.push({
        id: `evening-star-${last.time}`,
        time: last.time,
        type: 'bearish',
        title: '暮星 (Evening Star)',
        description: '三根K线组成的顶部反转形态，预示着上涨趋势的终结。',
        suggestion: '强力看跌信号，建议及时止盈或反手做空。',
        confidence: 'high',
        category: 'candlestick'
      });
    }

    // Three White Soldiers
    if (TI.threewhitesoldiers(data)) {
      signals.push({
        id: `three-white-soldiers-${last.time}`,
        time: last.time,
        type: 'bullish',
        title: '三白兵 (Three White Soldiers)',
        description: '连续三根阳线，且每根都在前一根实体内开盘，显示极强上涨动能。',
        suggestion: '趋势延续信号，适合顺势加仓。',
        confidence: 'high',
        category: 'candlestick'
      });
    }
  }

  private static detectTrendSignals(candles: Candle[], signals: Signal[]) {
    const closes = candles.map(c => c.close);
    const ema20 = TI.EMA.calculate({ period: 20, values: closes });
    const ema50 = TI.EMA.calculate({ period: 50, values: closes });

    const lastEma20 = ema20[ema20.length - 1];
    const lastEma50 = ema50[ema50.length - 1];
    const prevEma20 = ema20[ema20.length - 2];
    const prevEma50 = ema50[ema50.length - 2];

    if (prevEma20 <= prevEma50 && lastEma20 > lastEma50) {
      signals.push({
        id: `ema-cross-bull-${candles[candles.length - 1].time}`,
        time: candles[candles.length - 1].time,
        type: 'bullish',
        title: 'EMA 金叉 (Golden Cross)',
        description: '20日EMA上穿50日EMA，趋势转强。',
        suggestion: '中长线看涨信号确立，适合趋势跟踪。',
        confidence: 'high',
        category: 'trend'
      });
    } else if (prevEma20 >= prevEma50 && lastEma20 < lastEma50) {
      signals.push({
        id: `ema-cross-bear-${candles[candles.length - 1].time}`,
        time: candles[candles.length - 1].time,
        type: 'bearish',
        title: 'EMA 死叉 (Death Cross)',
        description: '20日EMA下穿50日EMA，趋势转弱。',
        suggestion: '中长线看跌信号，建议离场观望。',
        confidence: 'high',
        category: 'trend'
      });
    }
  }

  private static detectMomentumSignals(candles: Candle[], signals: Signal[]) {
    const closes = candles.map(c => c.close);
    const rsi = TI.RSI.calculate({ period: 14, values: closes });
    const lastRsi = rsi[rsi.length - 1];

    if (lastRsi > 70) {
      signals.push({
        id: `rsi-overbought-${candles[candles.length - 1].time}`,
        time: candles[candles.length - 1].time,
        type: 'neutral',
        title: 'RSI 超买',
        description: `RSI当前值为 ${lastRsi.toFixed(2)}，进入超买区域。`,
        suggestion: '行情可能面临回调压力，不建议追高。',
        confidence: 'medium',
        category: 'momentum'
      });
    } else if (lastRsi < 30) {
      signals.push({
        id: `rsi-oversold-${candles[candles.length - 1].time}`,
        time: candles[candles.length - 1].time,
        type: 'neutral',
        title: 'RSI 超卖',
        description: `RSI当前值为 ${lastRsi.toFixed(2)}，进入超卖区域。`,
        suggestion: '行情可能出现超跌反弹，关注筑底机会。',
        confidence: 'medium',
        category: 'momentum'
      });
    }
  }

  private static detectVolatilitySignals(candles: Candle[], signals: Signal[]) {
    const closes = candles.map(c => c.close);
    const bb = TI.BollingerBands.calculate({ period: 20, stdDev: 2, values: closes });
    const lastBB = bb[bb.length - 1];
    const lastClose = closes[closes.length - 1];

    if (lastClose > lastBB.upper) {
      signals.push({
        id: `bb-upper-${candles[candles.length - 1].time}`,
        time: candles[candles.length - 1].time,
        type: 'bearish',
        title: '触及布林带上轨',
        description: '价格突破布林带上轨，通常意味着短期超涨。',
        suggestion: '警惕冲高回落，可考虑分批止盈。',
        confidence: 'medium',
        category: 'volatility'
      });
    } else if (lastClose < lastBB.lower) {
      signals.push({
        id: `bb-lower-${candles[candles.length - 1].time}`,
        time: candles[candles.length - 1].time,
        type: 'bullish',
        title: '触及布林带下轨',
        description: '价格跌破布林带下轨，通常意味着短期超跌。',
        suggestion: '关注反弹机会，不建议在此位杀跌。',
        confidence: 'medium',
        category: 'volatility'
      });
    }
  }

  private static detectVolumeSignals(candles: Candle[], signals: Signal[]) {
    const last = candles[candles.length - 1];
    const volumes = candles.map(c => c.volume);
    const avgVolume = volumes.slice(-20).reduce((a, b) => a + b, 0) / 20;

    if (last.volume > avgVolume * 2) {
      signals.push({
        id: `high-volume-${last.time}`,
        time: last.time,
        type: 'neutral',
        title: '成交量异常放大',
        description: `当前成交量是过去20根均值的 ${(last.volume / avgVolume).toFixed(1)} 倍。`,
        suggestion: '巨量通常预示着趋势的延续或反转，请结合K线形态判断。',
        confidence: 'medium',
        category: 'volume'
      });
    }
  }

  private static detectMACDSignals(candles: Candle[], signals: Signal[]) {
    const closes = candles.map(c => c.close);
    const macd = TI.MACD.calculate({
      values: closes,
      fastPeriod: 12,
      slowPeriod: 26,
      signalPeriod: 9,
      SimpleMAOscillator: false,
      SimpleMASignal: false
    });

    if (macd.length < 2) return;

    const last = macd[macd.length - 1];
    const prev = macd[macd.length - 2];

    if (prev.MACD! <= prev.signal! && last.MACD! > last.signal!) {
      signals.push({
        id: `macd-cross-bull-${candles[candles.length - 1].time}`,
        time: candles[candles.length - 1].time,
        type: 'bullish',
        title: 'MACD 金叉',
        description: 'MACD快线上穿慢线，动能由负转正。',
        suggestion: '趋势转强信号，建议关注后续上涨空间。',
        confidence: 'medium',
        category: 'momentum'
      });
    } else if (prev.MACD! >= prev.signal! && last.MACD! < last.signal!) {
      signals.push({
        id: `macd-cross-bear-${candles[candles.length - 1].time}`,
        time: candles[candles.length - 1].time,
        type: 'bearish',
        title: 'MACD 死叉',
        description: 'MACD快线下穿慢线，动能由正转负。',
        suggestion: '趋势转弱信号，建议警惕回调风险。',
        confidence: 'medium',
        category: 'momentum'
      });
    }
  }

  private static detectCombinationSignals(candles: Candle[], signals: Signal[]) {
    const last = candles[candles.length - 1];
    const closes = candles.map(c => c.close);
    const data = {
      open: candles.map(c => c.open),
      high: candles.map(c => c.high),
      low: candles.map(c => c.low),
      close: closes,
    };

    // 1. RSI Oversold + Bullish Pattern (Trend Reversal)
    const rsi = TI.RSI.calculate({ period: 14, values: closes });
    const lastRsi = rsi[rsi.length - 1];
    const isBullishPattern = TI.bullishengulfingpattern(data) || TI.hammerpattern(data);

    if (lastRsi < 35 && isBullishPattern) {
      signals.push({
        id: `combo-reversal-bull-${last.time}`,
        time: last.time,
        type: 'bullish',
        title: '超卖反转组合 (RSI + K线)',
        description: 'RSI处于超卖区且出现看涨K线形态，反转信号极强。',
        suggestion: `建议入场价: ${formatPrice(last.close)}。止损参考: ${formatPrice(last.low * 0.99)}。`,
        confidence: 'high',
        category: 'advanced',
        entryPrice: last.close,
        stopLoss: last.low * 0.99,
        takeProfit: last.close + (last.close - last.low) * 3
      });
    }

    // 2. Trend Pullback (EMA + Pattern)
    const ema20 = TI.EMA.calculate({ period: 20, values: closes });
    const ema50 = TI.EMA.calculate({ period: 50, values: closes });
    const lastEma20 = ema20[ema20.length - 1];
    const lastEma50 = ema50[ema50.length - 1];

    // Uptrend pullback
    if (lastEma20 > lastEma50 && last.low <= lastEma20 && last.close > lastEma20 && isBullishPattern) {
      signals.push({
        id: `combo-pullback-bull-${last.time}`,
        time: last.time,
        type: 'bullish',
        title: '趋势回踩买入 (EMA + K线)',
        description: '处于上升趋势中，价格回踩20日均线并出现看涨形态。',
        suggestion: '顺势交易机会，建议在均线支撑位附近布局。',
        confidence: 'high',
        category: 'advanced',
        entryPrice: last.close,
        stopLoss: Math.min(last.low, lastEma50) * 0.995,
        takeProfit: last.close + (last.close - lastEma50) * 2
      });
    }

    // 3. Volatility Breakout (BB + Volume)
    const bb = TI.BollingerBands.calculate({ period: 20, stdDev: 2, values: closes });
    const lastBB = bb[bb.length - 1];
    const volumes = candles.map(c => c.volume);
    const avgVolume = volumes.slice(-20).reduce((a, b) => a + b, 0) / 20;

    if (last.close > lastBB.upper && last.volume > avgVolume * 1.5) {
      signals.push({
        id: `combo-breakout-bull-${last.time}`,
        time: last.time,
        type: 'bullish',
        title: '放量突破 (BB + Volume)',
        description: '价格放量突破布林带上轨，显示极强的向上突破动能。',
        suggestion: '动量突破信号，适合短线追涨，注意止损。',
        confidence: 'high',
        category: 'advanced',
        entryPrice: last.close,
        stopLoss: lastBB.middle,
        takeProfit: last.close + (last.close - lastBB.middle) * 1.5
      });
    }

    // 4. RSI Overbought + Bearish Pattern (Trend Reversal)
    const isBearishPattern = TI.bearishengulfingpattern(data) || TI.eveningstar(data);
    if (lastRsi > 65 && isBearishPattern) {
      signals.push({
        id: `combo-reversal-bear-${last.time}`,
        time: last.time,
        type: 'bearish',
        title: '超买见顶组合 (RSI + K线)',
        description: 'RSI处于超买区且出现看跌K线形态，见顶信号明显。',
        suggestion: `建议入场价: ${formatPrice(last.close)}。止损参考: ${formatPrice(last.high * 1.01)}。`,
        confidence: 'high',
        category: 'advanced',
        entryPrice: last.close,
        stopLoss: last.high * 1.01,
        takeProfit: last.close - (last.high - last.close) * 3
      });
    }

    // 5. Trend Pullback (EMA + Pattern) - Downtrend
    if (lastEma20 < lastEma50 && last.high >= lastEma20 && last.close < lastEma20 && isBearishPattern) {
      signals.push({
        id: `combo-pullback-bear-${last.time}`,
        time: last.time,
        type: 'bearish',
        title: '趋势回抽做空 (EMA + K线)',
        description: '处于下降趋势中，价格回抽20日均线并出现看跌形态。',
        suggestion: '顺势做空机会，建议在均线压力位附近布局。',
        confidence: 'high',
        category: 'advanced',
        entryPrice: last.close,
        stopLoss: Math.max(last.high, lastEma50) * 1.005,
        takeProfit: last.close - (lastEma50 - last.close) * 2
      });
    }
  }

  private static detectSupportResistanceSignals(candles: Candle[], signals: Signal[]) {
    const last = candles[candles.length - 1];
    const prev = candles[candles.length - 2];
    const { supports, resistances } = this.findSupportResistanceLevels(candles);

    const threshold = last.close * 0.005; // 0.5% proximity threshold

    // Check Resistances
    resistances.forEach(res => {
      // 1. Breakout
      if (prev.close <= res && last.close > res) {
        signals.push({
          id: `sr-breakout-${last.time}`,
          time: last.time,
          type: 'bullish',
          title: '阻力位突破 (Breakout)',
          description: `价格成功突破关键阻力位 ${formatPrice(res)}，上方空间打开。`,
          suggestion: '强力看涨信号，建议顺势做多，止损设在阻力位下方。',
          confidence: 'high',
          category: 'advanced',
          entryPrice: last.close,
          stopLoss: res * 0.99,
          takeProfit: last.close * 1.05
        });
      }
      // 2. Rejection (Touch and drop)
      else if (last.high >= res - threshold && last.close < res - threshold && last.open < last.close) {
        // Simple check for rejection: touched zone but closed lower
        const isBearish = last.close < last.open || (candles.length > 2 && last.close < candles[candles.length - 2].close);
        if (isBearish) {
          signals.push({
            id: `sr-rejection-${last.time}`,
            time: last.time,
            type: 'bearish',
            title: '阻力位受阻 (Rejection)',
            description: `价格在阻力位 ${formatPrice(res)} 附近遇阻回落。`,
            suggestion: '短期见顶信号，建议逢高减仓或尝试做空。',
            confidence: 'medium',
            category: 'advanced'
          });
        }
      }
    });

    // Check Supports
    supports.forEach(sup => {
      // 1. Breakdown
      if (prev.close >= sup && last.close < sup) {
        signals.push({
          id: `sr-breakdown-${last.time}`,
          time: last.time,
          type: 'bearish',
          title: '支撑位跌破 (Breakdown)',
          description: `价格跌破关键支撑位 ${formatPrice(sup)}，恐慌盘可能涌出。`,
          suggestion: '强力看跌信号，建议及时止损或顺势做空。',
          confidence: 'high',
          category: 'advanced',
          entryPrice: last.close,
          stopLoss: sup * 1.01,
          takeProfit: last.close * 0.95
        });
      }
      // 2. Bounce (Touch and up)
      else if (last.low <= sup + threshold && last.close > sup + threshold) {
        const isBullish = last.close > last.open;
        if (isBullish) {
          signals.push({
            id: `sr-bounce-${last.time}`,
            time: last.time,
            type: 'bullish',
            title: '支撑位反弹 (Bounce)',
            description: `价格在支撑位 ${formatPrice(sup)} 获得支撑并企稳反弹。`,
            suggestion: '筑底回升信号，建议关注做多机会。',
            confidence: 'medium',
            category: 'advanced'
          });
        }
      }
    });
  }

  private static findSupportResistanceLevels(candles: Candle[]) {
    const window = 20;
    const highs: number[] = [];
    const lows: number[] = [];

    // Find local peaks and troughs
    for (let i = window; i < candles.length - window; i++) {
      const current = candles[i];
      const slice = candles.slice(i - window, i + window + 1);
      
      const isHigh = slice.every(c => c.high <= current.high);
      const isLow = slice.every(c => c.low >= current.low);

      if (isHigh) highs.push(current.high);
      if (isLow) lows.push(current.low);
    }

    // Cluster levels that are close to each other
    const cluster = (levels: number[]) => {
      if (levels.length === 0) return [];
      const sorted = [...levels].sort((a, b) => a - b);
      const clusters: number[][] = [[sorted[0]]];
      const threshold = sorted[sorted.length - 1] * 0.01; // 1% clustering threshold

      for (let i = 1; i < sorted.length; i++) {
        const lastCluster = clusters[clusters.length - 1];
        const avg = lastCluster.reduce((a, b) => a + b, 0) / lastCluster.length;
        if (Math.abs(sorted[i] - avg) < threshold) {
          lastCluster.push(sorted[i]);
        } else {
          clusters.push([sorted[i]]);
        }
      }

      return clusters.map(c => c.reduce((a, b) => a + b, 0) / c.length);
    };

    return {
      supports: cluster(lows),
      resistances: cluster(highs)
    };
  }
}
