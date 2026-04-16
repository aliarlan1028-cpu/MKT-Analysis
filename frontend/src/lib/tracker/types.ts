/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Position {
  id: string;
  symbol: string;
  side: 'long' | 'short';
  leverage: number;
  entryPrice: number;
  amount: number; // in USDT
  margin: number;
  pnl: number;
  pnlPercent: number;
  timestamp: number;
  tp?: number;
  sl?: number;
  reason?: string; // 交易理由
}

export interface TradeHistory {
  id: string;
  symbol: string;
  side: 'long' | 'short';
  leverage: number;
  entryPrice: number;
  exitPrice: number;
  amount: number;
  pnl: number;
  timestamp: number;
  reason?: string; // 交易理由
  review?: string;
}

export interface Signal {
  id: string;
  time: number;
  type: 'bullish' | 'bearish' | 'neutral';
  title: string;
  description: string;
  suggestion: string;
  confidence: 'low' | 'medium' | 'high';
  category: 'candlestick' | 'trend' | 'momentum' | 'volatility' | 'volume' | 'advanced';
  indicators?: string[];
  entryPrice?: number;
  stopLoss?: number;
  takeProfit?: number;
  aiAnalysis?: string;
}

export interface PendingOrder {
  id: string;
  symbol: string;
  side: 'long' | 'short';
  leverage: number;
  amount: number;
  price: number;
  tp?: number;
  sl?: number;
  timestamp: number;
}

export interface TradingState {
  balance: number;
  positions: Position[];
  history: TradeHistory[];
  pendingOrders: PendingOrder[];
}
