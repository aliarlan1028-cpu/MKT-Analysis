/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Candle } from '@/lib/tracker/types';

type CandleCallback = (candle: Candle, isFinal: boolean) => void;

export class OKXService {
  private ws: WebSocket | null = null;
  private subscribers: Map<string, CandleCallback[]> = new Map();
  private baseUrl = 'wss://ws.okx.com:8443/ws/v5/public';

  constructor() {}

  connect() {
    if (this.ws) return;

    this.ws = new WebSocket(this.baseUrl);

    this.ws.onopen = () => {
      console.log('OKX WebSocket Connected');
      // Re-subscribe to existing symbols if any
      this.subscribers.forEach((_, key) => {
        const [symbol, interval] = key.split(':');
        this.subscribeToCandles(symbol, interval);
      });
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.arg && data.arg.channel.startsWith('candle')) {
        const candleData = data.data[0];
        const symbol = data.arg.instId;
        const interval = data.arg.channel.replace('candle', '');
        
        const candle: Candle = {
          time: parseInt(candleData[0]) / 1000,
          open: parseFloat(candleData[1]),
          high: parseFloat(candleData[2]),
          low: parseFloat(candleData[3]),
          close: parseFloat(candleData[4]),
          volume: parseFloat(candleData[5]),
        };

        const isFinal = candleData[8] === '1';
        const key = `${symbol}:${interval}`;
        this.subscribers.get(key)?.forEach(cb => cb(candle, isFinal));
      }
    };

    this.ws.onclose = () => {
      console.log('OKX WebSocket Closed. Reconnecting...');
      this.ws = null;
      setTimeout(() => this.connect(), 3000);
    };

    this.ws.onerror = (err) => {
      console.error('OKX WebSocket Error:', err);
    };
  }

  subscribe(symbol: string, interval: string, callback: CandleCallback) {
    const key = `${symbol}:${interval}`;
    if (!this.subscribers.has(key)) {
      this.subscribers.set(key, []);
      this.subscribeToCandles(symbol, interval);
    }
    this.subscribers.get(key)?.push(callback);

    return () => {
      const callbacks = this.subscribers.get(key) || [];
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
      if (callbacks.length === 0) {
        this.unsubscribeFromCandles(symbol, interval);
        this.subscribers.delete(key);
      }
    };
  }

  private subscribeToCandles(symbol: string, interval: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        op: 'subscribe',
        args: [{
          channel: `candle${interval}`,
          instId: symbol
        }]
      }));
    }
  }

  private unsubscribeFromCandles(symbol: string, interval: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        op: 'unsubscribe',
        args: [{
          channel: `candle${interval}`,
          instId: symbol
        }]
      }));
    }
  }

  async fetchHistory(symbol: string, interval: string, limit: number = 100): Promise<Candle[]> {
    const url = `https://www.okx.com/api/v5/market/candles?instId=${symbol}&bar=${interval}&limit=${limit}`;
    console.log(`Fetching history from: ${url}`);
    try {
      const response = await fetch(url);
      const data = await response.json();
      if (data.code !== '0') {
        console.error('OKX API Error:', data);
        throw new Error(data.msg || 'Unknown OKX API error');
      }
      
      return data.data.map((d: any) => ({
        time: parseInt(d[0]) / 1000,
        open: parseFloat(d[1]),
        high: parseFloat(d[2]),
        low: parseFloat(d[3]),
        close: parseFloat(d[4]),
        volume: parseFloat(d[5]),
      })).reverse();
    } catch (error) {
      console.error('Fetch history failed:', error);
      throw error;
    }
  }

  async fetchInstruments(): Promise<{ id: string, name: string }[]> {
    const url = 'https://www.okx.com/api/v5/public/instruments?instType=SWAP';
    try {
      const response = await fetch(url);
      const data = await response.json();
      if (data.code !== '0') throw new Error(data.msg);
      
      // Filter for live instruments and USDT settled ones for better compatibility
      return data.data
        .filter((inst: any) => inst.state === 'live' && inst.settleCcy === 'USDT')
        .map((inst: any) => ({
          id: inst.instId,
          name: `${inst.ctValCcy}/${inst.settleCcy} 永续`
        }))
        .sort((a: any, b: any) => a.id.localeCompare(b.id));
    } catch (error) {
      console.error('Fetch instruments failed:', error);
      return [
        { id: 'BTC-USDT-SWAP', name: 'BTC/USDT 永续' },
        { id: 'ETH-USDT-SWAP', name: 'ETH/USDT 永续' },
        { id: 'SOL-USDT-SWAP', name: 'SOL/USDT 永续' },
        { id: 'DOGE-USDT-SWAP', name: 'DOGE/USDT 永续' },
      ];
    }
  }
}

export const okxService = new OKXService();
