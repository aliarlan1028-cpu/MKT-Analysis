/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { GoogleGenAI } from "@google/genai";
import { Candle, Signal } from "@/lib/tracker/types";

let genAI: any = null;
let model: any = null;

function getModel() {
  const apiKey = (import.meta as any).env.VITE_GEMINI_API_KEY;
  if (!apiKey) return null;
  
  if (!genAI) {
    genAI = new GoogleGenAI(apiKey);
    model = genAI.getGenerativeModel({ model: "gemini-2.0-flash" });
  }
  return model;
}

export class AIService {
  static async analyzeSignalFailure(signal: Signal, currentCandles: Candle[]): Promise<string> {
    const aiModel = getModel();
    if (!aiModel) return "";

    const prompt = `
      交易信号分析：
      信号：${signal.title} (${signal.type})
      建议入场价：${signal.entryPrice}
      
      当前市场走势出现反向波动。请分析可能的原因：
      1. 是否存在趋势反转？
      2. 是否受大盘（如BTC）拖累？
      3. 是否是典型的“诱多/诱空”陷阱？
      
      最近K线数据：
      ${JSON.stringify(currentCandles.slice(-10))}
      
      请用中文给出简短分析（100字以内）。
    `;

    try {
      const result = await aiModel.generateContent(prompt);
      const response = await result.response;
      return response.text();
    } catch (error) {
      return "分析失败。";
    }
  }

  static async getTradeReview(trade: any): Promise<string> {
    const aiModel = getModel();
    if (!aiModel) return "AI 复盘功能不可用。";

    const prompt = `
      请对以下已完成的交易进行复盘总结：
      
      交易品种: ${trade.symbol}
      方向: ${trade.side === 'long' ? '做多' : '做空'}
      杠杆: ${trade.leverage}x
      入场价: ${trade.entryPrice}
      出场价: ${trade.exitPrice}
      盈亏: ${trade.pnl.toFixed(2)} USDT
      盈亏比例: ${((trade.pnl / (trade.amount / trade.leverage)) * 100).toFixed(2)}%
      
      请提供以下内容的中文复盘 (150字以内):
      1. 盈亏原因分析 (技术面/情绪面)。
      2. 交易执行评价 (入场点位、持仓耐心等)。
      3. 未来改进建议。
      4. 总结一句话经验。
    `;

    try {
      const result = await aiModel.generateContent(prompt);
      const response = await result.response;
      return response.text();
    } catch (error) {
      console.error("Trade review failed:", error);
      return "复盘生成失败。";
    }
  }
}
