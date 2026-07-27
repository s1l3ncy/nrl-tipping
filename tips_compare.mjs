// Replicates the app's heuristic tip model to compare old vs new tips.
import fs from 'fs';
function load(path){
  const src = fs.readFileSync(path,'utf8');
  const m = src.replace(/window\.\w+\s*=\s*/,'return ');
  return new Function(m.replace(/^[\s\S]*?return /,'return '))();
}
function loadData(path){ const s=fs.readFileSync(path,'utf8'); return eval('('+s.slice(s.indexOf('{'), s.lastIndexOf('}')+1)+')'); }
const LEARNED = loadData(process.argv[3]);
const learnedActive = !!(LEARNED && LEARNED.lowConfidence!==true);
const LOCK='SYD';
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
// Roosters lock
const rk=newT.find(t=>t.home===LOCK||t.away===LOCK);
if(rk){const rkProb=rk.home===LOCK?rk.pHome:100-rk.pHome;const opp=rk.home===LOCK?rk.away:rk.home;
  console.log(`\nROOSTERS lock: vs ${opp} (${rk.home===LOCK?'home':'away'}) — win chance ${rkProb.toFixed(0)}% -> ${rkProb>=50?'SAFE':'RISKY'} (model tips ${rk.tipShort===LOCK?'Roosters':rk.tip})`);
} else console.log('\nROOSTERS: bye this round');
