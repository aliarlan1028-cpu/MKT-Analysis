/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ISeriesApi, CandlestickData, SeriesMarker, CandlestickSeries } from 'lightweight-charts';
import { Candle, Signal, Position } from '@/lib/tracker/types';
import { formatPrice } from '@/lib/tracker/utils';

interface TradingChartProps {
  data: Candle[];
  signals: Signal[];
  positions: Position[];
  onSignalClick: (signal: Signal) => void;
}

export const TradingChart: React.FC<TradingChartProps> = ({ 
  data = [], 
  signals = [], 
  positions = [], 
  onSignalClick 
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [series, setSeries] = useState<ISeriesApi<'Candlestick'> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#0a0a0a' },
        textColor: '#d1d1d1',
      },
      grid: {
        vertLines: { color: '#1f1f1f' },
        horzLines: { color: '#1f1f1f' },
      },
      crosshair: {
        mode: 0,
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      priceFormat: {
        type: 'price',
        precision: 8,
        minMove: 0.00000001,
      },
    });

    chartRef.current = chart;
    setSeries(candlestickSeries);

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    chart.subscribeClick((param) => {
      if (!param.time || !param.point) return;
      
      const signal = signals.find(s => s.time === param.time);
      if (signal) {
        onSignalClick(signal);
      }
    });

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (series && data.length > 0) {
      series.setData(data as any);
    }
  }, [series, data]);

  useEffect(() => {
    if (series) {
      const markers: SeriesMarker<any>[] = [];

      // Clear existing price lines
      (series as any)._priceLines?.forEach((pl: any) => series.removePriceLine(pl));
      (series as any)._priceLines = [];

      // Add signal markers
      signals.forEach(s => {
        const dataStartTime = data[0]?.time || 0;
        const dataEndTime = data[data.length - 1]?.time || Infinity;
        
        if (s.time >= dataStartTime && s.time <= dataEndTime) {
          markers.push({
            time: s.time,
            position: s.type === 'bullish' ? 'belowBar' : s.type === 'bearish' ? 'aboveBar' : 'inBar',
            color: s.type === 'bullish' ? '#26a69a' : s.type === 'bearish' ? '#ef5350' : '#ff9800',
            shape: s.type === 'bullish' ? 'arrowUp' : s.type === 'bearish' ? 'arrowDown' : 'circle',
            text: s.title.split(' ')[0],
          });
        }
      });

      // Add position markers & price lines
      if (data.length > 0) {
        positions.forEach(p => {
          // Marker for entry
          markers.push({
            time: data[data.length - 1].time,
            position: p.side === 'long' ? 'belowBar' : 'aboveBar',
            color: '#2196f3',
            shape: 'circle',
            text: `${p.side.toUpperCase()} @ ${formatPrice(p.entryPrice)}`,
          });

          // Entry Price Line
          const entryLine = series.createPriceLine({
            price: p.entryPrice,
            color: '#2196f3',
            lineWidth: 2,
            lineStyle: 2, // Dashed
            axisLabelVisible: true,
            title: `开仓 (${p.side === 'long' ? '多' : '空'})`,
          });

          // TP Line
          let tpLine;
          if (p.tp) {
            tpLine = series.createPriceLine({
              price: p.tp,
              color: '#10b981',
              lineWidth: 1,
              lineStyle: 1, // Dotted
              axisLabelVisible: true,
              title: '止盈 (TP)',
            });
          }

          // SL Line
          let slLine;
          if (p.sl) {
            slLine = series.createPriceLine({
              price: p.sl,
              color: '#f43f5e',
              lineWidth: 1,
              lineStyle: 1, // Dotted
              axisLabelVisible: true,
              title: '止损 (SL)',
            });
          }

          // Store for cleanup
          if (!(series as any)._priceLines) (series as any)._priceLines = [];
          (series as any)._priceLines.push(entryLine);
          if (tpLine) (series as any)._priceLines.push(tpLine);
          if (slLine) (series as any)._priceLines.push(slLine);
        });
      }

      if (typeof (series as any).setMarkers === 'function') {
        const sortedMarkers = markers.sort((a, b) => (a.time as number) - (b.time as number));
        (series as any).setMarkers(sortedMarkers);
      }
    }
  }, [series, signals, positions, data]);

  return (
    <div className="relative w-full h-full">
      <div ref={chartContainerRef} className="w-full h-full" />
    </div>
  );
};
