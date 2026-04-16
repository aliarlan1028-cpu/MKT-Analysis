/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Position, TradeHistory, TradingState, PendingOrder } from '../types';

export class TradingEngine {
  private state: TradingState = {
    balance: 10000, // Initial 10k USDT
    positions: [],
    history: [],
    pendingOrders: []
  };

  constructor() {
    const saved = localStorage.getItem('trading_state');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        this.state = {
          ...this.state,
          ...parsed,
          // Ensure arrays exist even if missing from old saved state
          positions: parsed.positions || [],
          history: parsed.history || [],
          pendingOrders: parsed.pendingOrders || []
        };
      } catch (e) {
        console.error('Failed to parse trading state', e);
      }
    }
  }

  public save() {
    localStorage.setItem('trading_state', JSON.stringify(this.state));
  }

  public reset() {
    console.log('[TradingEngine] Resetting state...');
    this.state = {
      balance: 10000,
      positions: [],
      history: [],
      pendingOrders: []
    };
    localStorage.clear(); // Clear everything to be sure
    this.save();
    console.log('[TradingEngine] State reset complete.');
  }

  getState() {
    return this.state;
  }

  openPosition(symbol: string, side: 'long' | 'short', leverage: number, amount: number, price: number, tp?: number, sl?: number, isLimit: boolean = false) {
    let finalAmount = amount;
    let margin = amount / leverage;

    // If balance is insufficient, try to use maximum available balance
    if (margin > this.state.balance) {
      if (this.state.balance <= 0) {
        throw new Error('余额不足 (当前余额为 0)');
      }
      // Use 99% of balance to leave a small buffer
      margin = this.state.balance * 0.99;
      finalAmount = margin * leverage;
      console.log(`[TradingEngine] Insufficient balance. Adjusting amount from ${amount} to ${finalAmount.toFixed(2)}`);
    }

    if (isLimit) {
      const order: PendingOrder = {
        id: Math.random().toString(36).substr(2, 9),
        symbol,
        side,
        leverage,
        amount: finalAmount,
        price,
        tp,
        sl,
        timestamp: Date.now()
      };
      this.state.pendingOrders.push(order);
      this.save();
      return order;
    }

    const position: Position = {
      id: Math.random().toString(36).substr(2, 9),
      symbol,
      side,
      leverage,
      entryPrice: price,
      amount: finalAmount,
      margin,
      pnl: 0,
      pnlPercent: 0,
      timestamp: Date.now(),
      tp,
      sl
    };

    this.state.balance -= margin;
    this.state.positions.push(position);
    this.save();
    return position;
  }

  cancelOrder(id: string) {
    const index = this.state.pendingOrders.findIndex(o => o.id === id);
    if (index !== -1) {
      this.state.pendingOrders.splice(index, 1);
      this.save();
    }
  }

  closePosition(id: string, currentPrice: number, review?: string) {
    const index = this.state.positions.findIndex(p => p.id === id);
    if (index === -1) return;

    const pos = this.state.positions[index];
    const pnl = pos.side === 'long' 
      ? (currentPrice - pos.entryPrice) / pos.entryPrice * pos.amount
      : (pos.entryPrice - currentPrice) / pos.entryPrice * pos.amount;

    const history: TradeHistory = {
      id: pos.id,
      symbol: pos.symbol,
      side: pos.side,
      leverage: pos.leverage,
      entryPrice: pos.entryPrice,
      exitPrice: currentPrice,
      amount: pos.amount,
      pnl,
      timestamp: Date.now(),
      review
    };

    // Ensure balance doesn't go below zero
    const totalReturn = pos.margin + pnl;
    this.state.balance = Math.max(0, this.state.balance + totalReturn);
    
    this.state.history.unshift(history);
    this.state.positions.splice(index, 1);
    this.save();
  }

  updatePnL(currentPrices: Record<string, number>) {
    let changed = false;
    
    // 1. Check Pending Orders
    const remainingOrders: PendingOrder[] = [];
    this.state.pendingOrders.forEach(order => {
      const currentPrice = currentPrices[order.symbol];
      if (currentPrice) {
        const hit = order.side === 'long' 
          ? currentPrice <= order.price 
          : currentPrice >= order.price;
        
        if (hit) {
          const margin = order.amount / order.leverage;
          if (margin <= this.state.balance) {
            this.state.balance -= margin;
            this.state.positions.push({
              id: order.id,
              symbol: order.symbol,
              side: order.side,
              leverage: order.leverage,
              entryPrice: order.price,
              amount: order.amount,
              margin,
              pnl: 0,
              pnlPercent: 0,
              timestamp: Date.now(),
              tp: order.tp,
              sl: order.sl
            });
            changed = true;
          } else {
            // Insufficient balance to trigger, keep it pending or cancel?
            // For now, keep it pending.
            remainingOrders.push(order);
          }
        } else {
          remainingOrders.push(order);
        }
      } else {
        remainingOrders.push(order);
      }
    });
    this.state.pendingOrders = remainingOrders;

    // 2. Update Positions and check TP/SL
    const activePositions: Position[] = [];
    this.state.positions.forEach(pos => {
      const currentPrice = currentPrices[pos.symbol];
      if (currentPrice) {
        // Check TP/SL
        let shouldClose = false;
        if (pos.tp) {
          if (pos.side === 'long' ? currentPrice >= pos.tp : currentPrice <= pos.tp) {
            shouldClose = true;
          }
        }
        if (pos.sl) {
          if (pos.side === 'long' ? currentPrice <= pos.sl : currentPrice >= pos.sl) {
            shouldClose = true;
          }
        }

        if (shouldClose) {
          this.closePosition(pos.id, currentPrice, '止盈止损触发');
          changed = true;
        } else {
          const pnl = pos.side === 'long'
            ? (currentPrice - pos.entryPrice) / pos.entryPrice * pos.amount
            : (pos.entryPrice - currentPrice) / pos.entryPrice * pos.amount;
          
          // Liquidation check: if loss exceeds 90% of margin
          if (pnl <= -pos.margin * 0.9) {
            this.closePosition(pos.id, currentPrice, '强制平仓 (保证金不足)');
            changed = true;
            return;
          }

          pos.pnl = pnl;
          pos.pnlPercent = (pnl / pos.margin) * 100;
          activePositions.push(pos);
          changed = true;
        }
      } else {
        activePositions.push(pos);
      }
    });
    this.state.positions = activePositions;

    if (changed) this.save();
    return this.state.positions;
  }
}

export const tradingEngine = new TradingEngine();
