// Replicates the app's heuristic tip model to compare old vs new tips.
//
// MANUAL DEV TOOL ONLY — not in the workflow, not in any test. It does NOT
// reflect tipSide(): there is no comp policy, no split selection and no finals
// solver here, so it answers "what does the raw model like this week", never
// "what will the app tip". Use freeze_tips.mjs (which drives the real page) for
// that. The Roosters block was removed on 2026-09-12 with the lock itself.
import fs from 'fs';
function load(path){
  const src = fs.readFileSync(path,'utf8');
  const m = src.replace(/window\.\w+\s*=\s*/,'return ');
  return new Function(m.replace(/^[\s\S]*?return /,'return '))();
}
function loadData(path){ const s=fs.readFileSync(path,'utf8'); return eval('('+s.slice(s.indexOf('{'), s.lastIndexOf('}')+1)+')'); }
const LEARNED = loadData(process.argv[3]);
const learnedActive = !!(LEARNED && LEARNED.lowConfidence!==true);
function tipsFor(dataPath){
  const D = loadData(dataPath);
  const teams=D.teams, T=s=>teams.find(t=>t.short===s);
  const overallMargin=t=>(t.PF-t.PA)/Math.max(1,t.P);
  const avg=o=>o&&o.P>0?(o.PF-o.PA)/o.P:null;
  const formNudge=t=>Math.max(-2,Math.min(2,((t.last5||0)-2.5)*0.4));
  const splitWeight=n=>Math.min(0.5,(n||0)/((n||0)+6));
  function effRating(t,where){const base=overallMargin(t);const so=t[where];const sp=avg(so);let b;if(sp===null)b=base;else{const w=splitWeight(so.P);b=w*sp+(1-w)*base;}return b+formNudge(t);}
  const logistic=m=>1/(1+Math.exp(-m/(learnedActive?LEARNED.params.logisticScale:7)));
  const hga = learnedActive?LEARNED.params.homeAdv:2;
  function injPen(news){if(!news)return 0;const t=String(news).toLowerCase();if(!/(ruled out|late change|suspended|injured|\bout\b)/.test(t))return 0;return 3;}
  return D.fixtures.map(fx=>{
    const h=T(fx.home),a=T(fx.away);
    const margin=(effRating(h,'home')-injPen(h.news))-(effRating(a,'away')-injPen(a.news))+hga;
    const pHome=logistic(margin);
    const tip=pHome>=0.5?h:a;const conf=Math.max(pHome,1-pHome);
    return {g:`${h.name} v ${a.name}`, tip:tip.name, tipShort:tip.short, conf:+(conf*100).toFixed(0), pHome:+(pHome*100).toFixed(1), home:h.short, away:a.short};
  });
}
const oldT=tipsFor(process.argv[2]);
const newT=tipsFor(process.argv[4]);
console.log('GAME | OLD tip (win%) | NEW tip (win%) | CHANGED');
newT.forEach((n,i)=>{
  const o=oldT[i];
  const changed=(!o||o.tipShort!==n.tipShort||Math.abs(o.conf-n.conf)>=3)?'*** YES':'no';
  console.log(`${n.g} | ${o?o.tip+' '+o.conf+'%':'-'} | ${n.tip} ${n.conf}% | ${changed}`);
});
