"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
const SimChart = dynamic(() => import("@/components/sim/SimChart"), { ssr: false });
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Account { balance: number; used_margin: number; available_balance: number; total_pnl: number; total_trades: number; wins: number; losses: number; win_rate: number; can_refund: boolean; }
interface Factor { description: string; bias: string }
interface Position {
  id: number; coin: string; direction: string; status: string; leverage: number; margin: number;
  entry_price: number | null; target_entry_price: number; stop_loss: number;
  take_profit_1: number; take_profit_2: number | null; exit_price: number | null;
  pnl: number | null; pnl_pct: number | null; mae: number; mfe: number;
  factors: Factor[]; factor_review: Record<string, unknown> | null;
  trade_reason?: string; trade_summary?: string;
  events?: { timestamp: string; event_type: string; price: number; change_pct?: number }[];
  opened_at: string | null; closed_at: string | null; created_at: string;
}
function Badge({ text, type }: { text: string; type: "green" | "red" | "yellow" | "blue" }) {
  const c = { green: "bg-accent-green/15 text-accent-green", red: "bg-accent-red/15 text-accent-red", yellow: "bg-accent-yellow/15 text-accent-yellow", blue: "bg-accent-blue/15 text-accent-blue" };
  return <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${c[type]}`}>{text}</span>;
}
export default function SimTradingPanel() {
  const [account, setAccount] = useState<Account | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [allSymbols, setAllSymbols] = useState<string[]>([]);
  const [selectedCoin, setSelectedCoin] = useState("");
  const [coinSearch, setCoinSearch] = useState("");
  const [showCoinPicker, setShowCoinPicker] = useState(false);
  const [klinesMap, setKlinesMap] = useState<Record<string, unknown[]>>({});
  const [livePrice, setLivePrice] = useState<Record<string, number>>({});
  const [viewMode, setViewMode] = useState<"trade" | "history">("trade");
  const pickerRef = useRef<HTMLDivElement>(null);
  const [orderDir, setOrderDir] = useState<"LONG"|"SHORT">("LONG");
  const [orderSL, setOrderSL] = useState(""); const [orderTP1, setOrderTP1] = useState(""); const [orderTP2, setOrderTP2] = useState("");
  const [orderReason, setOrderReason] = useState(""); const [submitting, setSubmitting] = useState(false); const [showOrder, setShowOrder] = useState(false);
  const [closingId, setClosingId] = useState<number|null>(null); const [closeSummary, setCloseSummary] = useState(""); const [showClose, setShowClose] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [a, p] = await Promise.all([fetch(`${API}/sim/account`), fetch(`${API}/sim/positions`)]);
      if (a.ok) setAccount(await a.json()); if (p.ok) setPositions(await p.json());
    } catch { /* */ }
  }, []);
  useEffect(() => { fetchData(); fetch(`${API}/derivatives/symbols`).then(r=>r.ok?r.json():[]).then((d: Array<{ccy?:string}|string>)=>{setAllSymbols(d.map(x=>typeof x==="string"?x:(x.ccy||"")).filter(Boolean));}).catch(()=>{}); const iv=setInterval(fetchData,15000); return ()=>clearInterval(iv); }, [fetchData]);
  useEffect(() => { const h=(e:MouseEvent)=>{if(pickerRef.current&&!pickerRef.current.contains(e.target as Node))setShowCoinPicker(false);}; document.addEventListener("mousedown",h); return ()=>document.removeEventListener("mousedown",h); }, []);
  useEffect(() => { const coins=new Set<string>(); positions.filter(p=>p.status==="OPEN"||p.status==="PENDING").forEach(p=>coins.add(p.coin)); if(selectedCoin)coins.add(selectedCoin); if(!coins.size)return; const f=async()=>{const pr:Record<string,number>={}; await Promise.allSettled([...coins].map(async c=>{try{const r=await fetch(`${API}/market/okx/${c}`);if(r.ok){const d=await r.json();pr[c]=d.price;}}catch{}})); setLivePrice(pr);}; f(); const iv=setInterval(f,10000); return ()=>clearInterval(iv); }, [positions,selectedCoin]);
  const chartCoins = Array.from(new Set([...(selectedCoin?[selectedCoin]:[]),...positions.filter(p=>p.status==="OPEN"||p.status==="PENDING").map(p=>p.coin)]));
  useEffect(() => { if(!chartCoins.length)return; const f=async()=>{const m:Record<string,unknown[]>={}; await Promise.allSettled(chartCoins.map(async c=>{try{const r=await fetch(`${API}/sim/klines/${c}?bar=5m&limit=200`);if(r.ok)m[c]=await r.json();}catch{}})); setKlinesMap(prev=>({...prev,...m}));}; f(); const iv=setInterval(f,60000); return ()=>clearInterval(iv); }, [chartCoins.join(",")]);
  const doRefund = async () => { await fetch(`${API}/sim/refund`,{method:"POST"}); fetchData(); };
  const openPositions = positions.filter(p=>p.status==="OPEN"||p.status==="PENDING");
  const closedPositions = positions.filter(p=>p.status==="CLOSED"||p.status==="LIQUIDATED");
  const curPrice = selectedCoin ? livePrice[selectedCoin] : null;

  const submitOrder = async () => {
    if(!selectedCoin||!curPrice||!orderSL||!orderTP1||!orderReason.trim()){alert("请填写所有必填项");return;}
    setSubmitting(true);
    try { await fetch(`${API}/sim/open`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({coin:selectedCoin,direction:orderDir,entry_price:curPrice,stop_loss:parseFloat(orderSL),take_profit_1:parseFloat(orderTP1),take_profit_2:orderTP2?parseFloat(orderTP2):null,factors:[{description:orderReason,bias:orderDir==="LONG"?"看多":"看空"}]})}); setOrderReason("");setOrderSL("");setOrderTP1("");setOrderTP2("");setShowOrder(false);fetchData(); } catch{alert("下单失败");}
    setSubmitting(false);
  };
  const handleClose=(id:number)=>{setClosingId(id);setCloseSummary("");setShowClose(true);};
  const confirmClose=async()=>{if(closingId===null)return; if(closeSummary.trim()){await fetch(`${API}/sim/positions/${closingId}/summary`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({summary:closeSummary})}).catch(()=>{});} await fetch(`${API}/sim/close/${closingId}`,{method:"POST"}); setShowClose(false);setClosingId(null);setCloseSummary("");fetchData();};

  return (
    <div className="space-y-4">
      {/* ═══ ACCOUNT BAR ═══ */}
      {account && (
        <div className="grid grid-cols-3 md:grid-cols-7 gap-2">
          {[{l:"账户余额",v:`$${account.balance.toFixed(2)}`},{l:"已用保证金",v:`$${account.used_margin.toFixed(2)}`},{l:"可用余额",v:`$${account.available_balance.toFixed(2)}`},
            {l:"累计盈亏",v:`${account.total_pnl>=0?"+":""}${account.total_pnl.toFixed(2)}`,c:account.total_pnl>=0?"text-accent-green":"text-accent-red"},
            {l:"胜率",v:`${account.win_rate}%`},{l:"交易",v:`${account.wins}胜 ${account.losses}负`},
          ].map(({l,v,c})=>(
            <div key={l} className="bg-card-bg border border-card-border rounded-lg p-2 text-center">
              <div className="text-[10px] text-text-muted">{l}</div><div className={`text-sm font-bold font-mono ${c||""}`}>{v}</div>
            </div>
          ))}
          <div className="bg-card-bg border border-card-border rounded-lg p-2 flex items-center justify-center">
            {account.can_refund ? <button onClick={doRefund} className="px-2 py-1 bg-accent-yellow/20 text-accent-yellow rounded text-xs font-semibold">💰 补充资金</button> : <span className="text-[10px] text-text-muted">余额充足</span>}
          </div>
        </div>
      )}

      {/* ═══ TABS ═══ */}
      <div className="flex gap-2">
        {(["trade","history"] as const).map(m=>(
          <button key={m} onClick={()=>setViewMode(m)} className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${viewMode===m?"bg-accent-blue/20 text-accent-blue":"bg-card-bg text-text-muted hover:text-white"}`}>
            {m==="trade"?"📊 交易":"📋 历史 & 心得"} {m==="history"&&closedPositions.length>0&&`(${closedPositions.length})`}
          </button>
        ))}
      </div>

      {viewMode === "trade" ? (<>
        {/* ═══ COIN PICKER + ORDER BUTTON ═══ */}
        <div className="flex items-center gap-3 bg-card-bg border border-card-border rounded-xl p-3">
          <div className="relative flex-1" ref={pickerRef}>
            <button onClick={()=>setShowCoinPicker(!showCoinPicker)} className="w-full px-3 py-2 bg-transparent border border-card-border rounded-lg text-left text-sm hover:border-accent-blue/40">
              {selectedCoin ? `${selectedCoin}/USDT 永续` : "点击选择币种..."}
            </button>
            {showCoinPicker && (
              <div className="absolute top-full left-0 mt-1 w-full bg-card-bg border border-card-border rounded-lg shadow-xl z-50">
                <input type="text" placeholder="搜索..." value={coinSearch} onChange={e=>setCoinSearch(e.target.value.toUpperCase())} className="w-full px-3 py-2 bg-transparent border-b border-card-border text-sm outline-none" autoFocus />
                <div className="max-h-48 overflow-y-auto">
                  {allSymbols.filter(s=>s.includes(coinSearch)).slice(0,30).map(s=>(
                    <button key={s} onClick={()=>{setSelectedCoin(s);setShowCoinPicker(false);setCoinSearch("");}} className="w-full text-left px-3 py-1.5 text-sm hover:bg-accent-blue/10">{s}/USDT</button>
                  ))}
                </div>
              </div>
            )}
          </div>
          {selectedCoin && curPrice && (
            <div className="text-right shrink-0">
              <div className="text-lg font-bold font-mono">${curPrice.toLocaleString(undefined,{minimumFractionDigits:2})}</div>
              <div className="text-[10px] text-text-muted">实时价格</div>
            </div>
          )}
          {selectedCoin && <button onClick={()=>setShowOrder(!showOrder)} className="px-4 py-2 bg-accent-blue text-white rounded-lg text-sm font-semibold hover:bg-accent-blue/80 shrink-0">📝 下单</button>}
        </div>

        {/* ═══ ORDER FORM ═══ */}
        {showOrder && selectedCoin && (
          <div className="bg-card-bg border-2 border-accent-blue/40 rounded-xl p-4">
            <h3 className="text-sm font-bold mb-3">📝 手动下单 — {selectedCoin}/USDT</h3>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <button onClick={()=>setOrderDir("LONG")} className={`py-3 rounded-lg font-bold text-sm ${orderDir==="LONG"?"bg-accent-green text-black":"bg-white/5 text-text-muted hover:bg-accent-green/10"}`}>🟢 做多 LONG</button>
              <button onClick={()=>setOrderDir("SHORT")} className={`py-3 rounded-lg font-bold text-sm ${orderDir==="SHORT"?"bg-accent-red text-white":"bg-white/5 text-text-muted hover:bg-accent-red/10"}`}>🔴 做空 SHORT</button>
            </div>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div><label className="text-[10px] text-text-muted block mb-1">🛑 止损价 *</label><input type="number" value={orderSL} onChange={e=>setOrderSL(e.target.value)} placeholder="止损价格" className="w-full px-3 py-2 bg-white/5 border border-card-border rounded-lg text-sm font-mono outline-none focus:border-accent-red/50" /></div>
              <div><label className="text-[10px] text-text-muted block mb-1">🎯 止盈1 *</label><input type="number" value={orderTP1} onChange={e=>setOrderTP1(e.target.value)} placeholder="止盈价格" className="w-full px-3 py-2 bg-white/5 border border-card-border rounded-lg text-sm font-mono outline-none focus:border-accent-green/50" /></div>
              <div><label className="text-[10px] text-text-muted block mb-1">🎯 止盈2 (选填)</label><input type="number" value={orderTP2} onChange={e=>setOrderTP2(e.target.value)} placeholder="可选" className="w-full px-3 py-2 bg-white/5 border border-card-border rounded-lg text-sm font-mono outline-none" /></div>
            </div>
            <div className="mb-3">
              <label className="text-[10px] text-text-muted block mb-1">📝 交易理由 * （为什么{orderDir==="LONG"?"做多":"做空"}？）</label>
              <textarea value={orderReason} onChange={e=>setOrderReason(e.target.value)} rows={3} placeholder="写下你的分析和交易理由...这将帮助你在复盘时回顾决策过程" className="w-full px-3 py-2 bg-white/5 border border-card-border rounded-lg text-sm outline-none resize-none focus:border-accent-blue/50" />
            </div>
            <div className="flex items-center justify-between">
              <p className="text-[10px] text-text-muted">入场价: ${curPrice?.toLocaleString()} | 杠杆: 10x全仓</p>
              <button onClick={submitOrder} disabled={submitting||!orderReason.trim()||!orderSL||!orderTP1} className={`px-6 py-2.5 rounded-lg font-bold text-sm transition-all ${orderDir==="LONG"?"bg-accent-green text-black hover:bg-accent-green/90":"bg-accent-red text-white hover:bg-accent-red/90"} disabled:opacity-50`}>
                {submitting?"⏳ 提交中...":"✅ 确认开仓"}
              </button>
            </div>
          </div>
        )}

        {/* ═══ K-LINE CHARTS ═══ */}
        {chartCoins.length > 0 && (
          <div className={`grid gap-4 ${chartCoins.length>=2?"grid-cols-1 lg:grid-cols-2":"grid-cols-1"}`}>
            {chartCoins.map(coin=>{
              const klines=klinesMap[coin]||[]; const pos=openPositions.find(p=>p.coin===coin);
              if(!klines.length) return null;
              return <SimChart key={coin} coin={coin} klines={klines as never[]} entryPrice={pos?.entry_price||undefined} stopLoss={pos?.stop_loss} takeProfit1={pos?.take_profit_1} takeProfit2={pos?.take_profit_2||undefined} events={pos?.events} direction={pos?.direction} />;
            })}
          </div>
        )}

        {/* ═══ ACTIVE POSITIONS ═══ */}
        {openPositions.length > 0 && (
          <div className="bg-card-bg border border-card-border rounded-xl p-4">
            <h3 className="text-sm font-semibold mb-2">📈 活跃持仓 ({openPositions.length}/2)</h3>
            {openPositions.map(pos=>{
              const price=livePrice[pos.coin]; const entry=pos.entry_price||pos.target_entry_price;
              let pnl=0; if(price&&pos.entry_price){pnl=pos.direction==="LONG"?(price-pos.entry_price)/pos.entry_price*100*pos.leverage:(pos.entry_price-price)/pos.entry_price*100*pos.leverage;}
              return (
                <div key={pos.id} className="border border-card-border rounded-lg p-3 mb-2">
                  <div className="flex justify-between items-center mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-bold">{pos.coin}/USDT</span>
                      <Badge text={`${pos.direction==="LONG"?"做多":"做空"} ${pos.leverage}x`} type={pos.direction==="LONG"?"green":"red"} />
                      <Badge text={pos.status==="OPEN"?"持仓中":"等待成交"} type={pos.status==="OPEN"?"blue":"yellow"} />
                    </div>
                    <button onClick={()=>handleClose(pos.id)} className="px-3 py-1.5 bg-accent-red/20 text-accent-red rounded-lg text-xs font-semibold hover:bg-accent-red/30">
                      {pos.status==="PENDING"?"取消":"平仓"}
                    </button>
                  </div>
                  <div className="grid grid-cols-5 gap-2 text-xs">
                    <div><span className="text-text-muted">入场</span><div className="font-mono">${entry}</div></div>
                    <div><span className="text-text-muted">现价</span><div className="font-mono">${price?.toFixed(6)||"..."}</div></div>
                    <div><span className="text-text-muted">浮动盈亏</span><div className={`font-mono font-bold ${pnl>=0?"text-accent-green":"text-accent-red"}`}>{pos.status==="OPEN"?`${pnl>=0?"+":""}${pnl.toFixed(2)}%`:"—"}</div></div>
                    <div><span className="text-text-muted">止损</span><div className="font-mono text-accent-red">${pos.stop_loss}</div></div>
                    <div><span className="text-text-muted">止盈</span><div className="font-mono text-accent-green">${pos.take_profit_1}</div></div>
                  </div>
                  {/* Show trade reason */}
                  {pos.factors?.[0]?.description && (
                    <div className="mt-2 p-2 bg-white/5 rounded text-xs border-l-2 border-accent-blue">
                      <span className="text-text-muted">交易理由：</span>{pos.factors[0].description}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* ═══ CLOSE DIALOG ═══ */}
        {showClose && (
          <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={()=>setShowClose(false)}>
            <div className="bg-card-bg border border-card-border rounded-xl p-6 w-full max-w-md" onClick={e=>e.stopPropagation()}>
              <h3 className="text-lg font-bold mb-3">📝 平仓总结</h3>
              <p className="text-xs text-text-muted mb-3">在平仓前写下你的交易心得 — 这笔交易学到了什么？哪里做对了/错了？</p>
              <textarea value={closeSummary} onChange={e=>setCloseSummary(e.target.value)} rows={5} placeholder="写下你的交易总结和心得...&#10;&#10;例如：&#10;- 入场时机判断正确，但止盈设太近&#10;- 被情绪影响追高了&#10;- 应该等回调再入场" className="w-full px-3 py-2 bg-white/5 border border-card-border rounded-lg text-sm outline-none resize-none mb-3" />
              <div className="flex gap-2">
                <button onClick={()=>{setShowClose(false);}} className="flex-1 px-4 py-2 bg-white/5 text-text-muted rounded-lg text-sm hover:bg-white/10">取消</button>
                <button onClick={confirmClose} className="flex-1 px-4 py-2 bg-accent-red text-white rounded-lg text-sm font-semibold hover:bg-accent-red/80">
                  {closeSummary.trim()?"✅ 保存心得并平仓":"⚠️ 跳过心得直接平仓"}
                </button>
              </div>
            </div>
          </div>
        )}
      </>) : (
        /* ═══ HISTORY TAB ═══ */
        <div className="space-y-4">
          {closedPositions.length===0 ? (
            <div className="bg-card-bg border border-card-border rounded-xl p-8 text-center text-text-muted">暂无历史交易</div>
          ) : closedPositions.map(pos=>{
            const isProfit=(pos.pnl||0)>=0;
            return (
              <div key={pos.id} className="bg-card-bg border border-card-border rounded-xl overflow-hidden">
                <div className={`flex items-center justify-between p-4 ${isProfit?"bg-accent-green/5":"bg-accent-red/5"}`}>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-lg">{pos.coin}/USDT</span>
                    <Badge text={`${pos.direction==="LONG"?"做多":"做空"} ${pos.leverage}x`} type={pos.direction==="LONG"?"green":"red"} />
                    {pos.status==="LIQUIDATED"&&<Badge text="💥 爆仓" type="red" />}
                  </div>
                  <span className={`text-2xl font-bold font-mono ${isProfit?"text-accent-green":"text-accent-red"}`}>
                    {isProfit?"+":""}{pos.pnl_pct?.toFixed(2)}% <span className="text-sm">(${pos.pnl?.toFixed(2)})</span>
                  </span>
                </div>
                <div className="p-4">
                  <div className="grid grid-cols-6 gap-2 text-xs mb-3">
                    {[["入场价",`$${pos.entry_price}`],["平仓价",`$${pos.exit_price}`],["保证金",`$${pos.margin?.toFixed(2)}`],
                      ["MAE",`${pos.mae?.toFixed(2)}%`,"text-accent-red"],["MFE",`+${pos.mfe?.toFixed(2)}%`,"text-accent-green"],["时间",pos.opened_at?.slice(5,16)||"N/A"],
                    ].map(([l,v,c])=><div key={String(l)} className="bg-white/5 rounded p-2"><span className="text-text-muted text-[10px] block">{l}</span><div className={`font-mono ${c||""}`}>{v}</div></div>)}
                  </div>
                  {/* Trade reason */}
                  {pos.factors?.[0]?.description && (
                    <div className="mb-3 p-3 bg-accent-blue/5 border border-accent-blue/20 rounded-lg">
                      <span className="text-[10px] text-accent-blue font-semibold block mb-1">📝 开仓理由</span>
                      <p className="text-xs">{pos.factors[0].description}</p>
                    </div>
                  )}
                  {/* Trade summary */}
                  {pos.trade_summary ? (
                    <div className={`p-3 rounded-lg border ${isProfit?"bg-accent-green/5 border-accent-green/20":"bg-accent-red/5 border-accent-red/20"}`}>
                      <span className="text-[10px] font-semibold block mb-1">{isProfit?"✅":"❌"} 交易心得</span>
                      <p className="text-xs">{pos.trade_summary}</p>
                    </div>
                  ) : (
                    <div className="p-3 bg-white/5 rounded-lg text-xs text-text-muted italic">未填写交易心得</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
