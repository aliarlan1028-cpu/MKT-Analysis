/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { tradingEngine } from '@/lib/trading-engine';
import { Settings2, Eye, Bell, Zap, Cpu, AlertTriangle } from 'lucide-react';

interface SettingsSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: any;
  onConfigChange: (config: any) => void;
  onResetAccount: () => void;
}

export const SettingsSheet: React.FC<SettingsSheetProps> = ({ open, onOpenChange, config, onConfigChange, onResetAccount }) => {
  const [showConfirmReset, setShowConfirmReset] = React.useState(false);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="bg-zinc-950 border-zinc-800 text-zinc-100 w-[400px] p-0 flex flex-col h-screen max-h-screen overflow-hidden">
        <div className="px-8 pt-6 pb-4 shrink-0 border-b border-zinc-900">
          <SheetHeader className="text-left">
            <SheetTitle className="flex items-center gap-2 text-zinc-100">
              <Settings2 className="w-5 h-5" />
              系统设置
            </SheetTitle>
            <SheetDescription className="text-zinc-500">
              配置您的指标扫描器与交易偏好
            </SheetDescription>
          </SheetHeader>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-8 py-6 space-y-8">
          {/* Signal Filters */}
          <section className="space-y-4">
            <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
              <Eye className="w-3 h-3" /> 信号显示
            </h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <Label htmlFor="strong-only" className="text-sm">仅显示强信号</Label>
                <Switch 
                  id="strong-only" 
                  checked={config.strongOnly} 
                  onCheckedChange={(v) => onConfigChange({ ...config, strongOnly: v })}
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="show-candlestick" className="text-sm">K线形态识别</Label>
                <Switch 
                  id="show-candlestick" 
                  checked={config.showCandlestick} 
                  onCheckedChange={(v) => onConfigChange({ ...config, showCandlestick: v })}
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="show-trend" className="text-sm">趋势指标信号</Label>
                <Switch 
                  id="show-trend" 
                  checked={config.showTrend} 
                  onCheckedChange={(v) => onConfigChange({ ...config, showTrend: v })}
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="show-macd" className="text-sm">MACD 指标信号</Label>
                <Switch 
                  id="show-macd" 
                  checked={config.showMacd !== false} 
                  onCheckedChange={(v) => onConfigChange({ ...config, showMacd: v })}
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="show-advanced" className="text-sm">高级组合信号</Label>
                <Switch 
                  id="show-advanced" 
                  checked={config.showAdvanced !== false} 
                  onCheckedChange={(v) => onConfigChange({ ...config, showAdvanced: v })}
                />
              </div>
            </div>
          </section>

          {/* Sensitivity */}
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
                <Zap className="w-3 h-3" /> 扫描灵敏度
              </h3>
              <span className="text-xs font-mono text-zinc-100 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
                {config.sensitivity}%
              </span>
            </div>
            <div className="space-y-6">
              <div className="space-y-4">
                <div onPointerDown={(e) => e.stopPropagation()} className="px-1 py-2">
                  <Slider 
                    value={[config.sensitivity]} 
                    onValueChange={(v) => onConfigChange({ ...config, sensitivity: v[0] })}
                    max={100} 
                    min={0} 
                    step={1} 
                    className="cursor-pointer"
                  />
                </div>
                
                <div className="grid grid-cols-3 gap-2">
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className={`text-[10px] h-7 ${config.sensitivity <= 30 ? 'bg-zinc-100 text-zinc-950 border-zinc-100' : 'bg-zinc-900 border-zinc-800 text-zinc-400'}`}
                    onClick={() => onConfigChange({ ...config, sensitivity: 20 })}
                  >
                    保守
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className={`text-[10px] h-7 ${config.sensitivity > 30 && config.sensitivity <= 70 ? 'bg-zinc-100 text-zinc-950 border-zinc-100' : 'bg-zinc-900 border-zinc-800 text-zinc-400'}`}
                    onClick={() => onConfigChange({ ...config, sensitivity: 50 })}
                  >
                    均衡
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className={`text-[10px] h-7 ${config.sensitivity > 70 ? 'bg-zinc-100 text-zinc-950 border-zinc-100' : 'bg-zinc-900 border-zinc-800 text-zinc-400'}`}
                    onClick={() => onConfigChange({ ...config, sensitivity: 80 })}
                  >
                    激进
                  </Button>
                </div>

                <p className="text-[10px] text-zinc-500 leading-relaxed">
                  {config.sensitivity > 70 
                    ? "当前处于激进模式：将捕捉更多微小波动，但误报风险较高。" 
                    : config.sensitivity < 30 
                    ? "当前处于保守模式：仅识别极高置信度的信号，过滤大部分噪音。"
                    : "当前处于均衡模式：在信号频率与准确度之间取得平衡。"}
                </p>
              </div>
            </div>
          </section>

          {/* Notifications */}
          <section className="space-y-4">
            <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
              <Bell className="w-3 h-3" /> 通知提醒
            </h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <Label htmlFor="sound" className="text-sm">开启提示音</Label>
                <Switch 
                  id="sound" 
                  checked={config.sound} 
                  onCheckedChange={(v) => onConfigChange({ ...config, sound: v })}
                />
              </div>
            </div>
          </section>

          {/* Auto Trading */}
          <section className="space-y-4 pt-4 border-t border-zinc-900">
            <h3 className="text-xs font-bold text-emerald-500 uppercase tracking-wider flex items-center gap-2">
              <Cpu className="w-3 h-3" /> 自动交易 (Beta)
            </h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="auto-trade" className="text-sm">开启自动跟单</Label>
                  <p className="text-[10px] text-zinc-500">仅针对高置信度信号自动开仓</p>
                </div>
                <Switch 
                  id="auto-trade" 
                  checked={config.autoTrade} 
                  onCheckedChange={(v) => onConfigChange({ ...config, autoTrade: v })}
                />
              </div>
              
              {config.autoTrade && (
                <div className="space-y-6 animate-in fade-in slide-in-from-top-2 duration-200">
                  {/* Amount Selection */}
                  <div className="space-y-3">
                    <div className="flex justify-between items-center">
                      <Label className="text-xs text-zinc-400">单笔金额 (USDT)</Label>
                      <div className="flex items-center gap-2">
                        <Input 
                          type="number"
                          value={config.autoTradeAmount}
                          onChange={(e) => onConfigChange({ ...config, autoTradeAmount: Number(e.target.value) })}
                          className="w-20 h-7 text-[10px] bg-zinc-900 border-zinc-800 text-right font-mono"
                        />
                        <span className="text-[10px] text-zinc-600">USDT</span>
                      </div>
                    </div>
                    <div className="grid grid-cols-4 gap-1.5">
                      {[50, 100, 200, 500].map(val => (
                        <Button
                          key={val}
                          variant="outline"
                          size="sm"
                          className={`h-6 text-[9px] ${config.autoTradeAmount === val ? 'bg-emerald-600 border-emerald-500 text-white' : 'bg-zinc-900 border-zinc-800 text-zinc-400'}`}
                          onClick={() => onConfigChange({ ...config, autoTradeAmount: val })}
                        >
                          {val}
                        </Button>
                      ))}
                    </div>
                  </div>

                  {/* Leverage Selection */}
                  <div className="space-y-3">
                    <div className="flex justify-between items-center">
                      <Label className="text-xs text-zinc-400">默认杠杆</Label>
                      <div className="flex items-center gap-2">
                        <Input 
                          type="number"
                          value={config.autoTradeLeverage}
                          onChange={(e) => onConfigChange({ ...config, autoTradeLeverage: Number(e.target.value) })}
                          className="w-20 h-7 text-[10px] bg-zinc-900 border-zinc-800 text-right font-mono"
                        />
                        <span className="text-[10px] text-zinc-600">x</span>
                      </div>
                    </div>
                    <div className="grid grid-cols-4 gap-1.5">
                      {[3, 5, 10, 20].map(val => (
                        <Button
                          key={val}
                          variant="outline"
                          size="sm"
                          className={`h-6 text-[9px] ${config.autoTradeLeverage === val ? 'bg-emerald-600 border-emerald-500 text-white' : 'bg-zinc-900 border-zinc-800 text-zinc-400'}`}
                          onClick={() => onConfigChange({ ...config, autoTradeLeverage: val })}
                        >
                          {val}x
                        </Button>
                      ))}
                    </div>
                  </div>

                  <p className="text-[10px] text-zinc-500 leading-relaxed bg-zinc-900/50 p-2 rounded border border-zinc-800/50">
                    <span className="text-emerald-500 font-bold">提示：</span> 
                    系统将以 {config.autoTradeLeverage}x 杠杆，每笔投入 {config.autoTradeAmount} USDT 进行自动跟单。请确保账户余额充足。
                  </p>
                </div>
              )}
            </div>
          </section>

          {/* Danger Zone */}
          <section className="space-y-4 pt-4 border-t border-zinc-900 pb-12">
            <h3 className="text-xs font-bold text-rose-500 uppercase tracking-wider flex items-center gap-2">
              <AlertTriangle className="w-3 h-3" /> 危险区域
            </h3>
            <div className="bg-rose-950/10 border border-rose-900/20 rounded-lg p-3 space-y-3">
              <p className="text-[10px] text-rose-500/80 leading-relaxed">
                重置账户将永久清除所有持仓、历史记录并将余额恢复至初始状态 (10,000 USDT)。此操作不可撤销。
              </p>
              {!showConfirmReset ? (
                <Button 
                  variant="destructive" 
                  className="w-full h-8 text-[10px] font-bold uppercase tracking-wider"
                  onClick={() => setShowConfirmReset(true)}
                >
                  立即重置账户
                </Button>
              ) : (
                <div className="flex gap-2 animate-in fade-in zoom-in-95 duration-200">
                  <Button 
                    variant="outline" 
                    className="flex-1 h-8 text-[10px] border-zinc-800 text-zinc-400"
                    onClick={() => setShowConfirmReset(false)}
                  >
                    取消
                  </Button>
                  <Button 
                    variant="destructive" 
                    className="flex-1 h-8 text-[10px] font-bold"
                    onClick={() => {
                      console.log('[SettingsSheet] Reset confirmed via custom UI');
                      onResetAccount();
                      setShowConfirmReset(false);
                    }}
                  >
                    确认重置
                  </Button>
                </div>
              )}
            </div>
          </section>
        </div>
      </SheetContent>
    </Sheet>
  );
};
