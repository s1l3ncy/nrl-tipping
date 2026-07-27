// Standalone reproduction of nrl-tipping-guide.html's SIMPLE model (used while
// learned model is lowConfidence). Prints Round 22 tips + win% exactly as the app.
import fs from 'fs';
const raw = fs.readFileSync(new URL('./nrl_data.js', import.meta.url),'utf8');
const body = raw.split('\n').filter(l=>!l.trimStart().startsWith('//')).join('\n');
const json = body.slice(body.indexOf('=')+1, body.lastIndexOf(';'));
const D = JSON.parse(json);
const teams = D.teams, fixtures = D.fixtures;
const T = s => teams.find(t=>t.short===s);
const HGA = 2, FORMW = 0.4;
const overallMargin = t => (t.PF-t.PA)/Math.max(1,t.P);
const avg = o => (o && o.P>0) ? (o.PF-o.PA)/o.P : null;
const splitWeight = n => Math.min(0.5, (n||0)/((n||0)+6));
const formNudge = t => Math.max(-2, Math.min(2, (((t.last5||0)-2.5)*FORMW)));
function effRating(t,where){
  const base=overallMargin(t); const so=t[where]; const s=avg(so);
  let blended = (s===null)? base : (splitWeight(so.P)*s + (1-splitWeight(so.P))*base);
  return blended + formNudge(t);
}
const logistic = m => 1/(1+Math.exp(-m/7));
console.log(`Round ${D.round} — bye: ${D.byeTeams.join(', ')}`);
for(const fx of fixtures){
  const h=T(fx.home), a=T(fx.away);
  const margin = effRating(h,'home') - effRating(a,'away') + HGA;
  const pHome = logistic(margin);
  const tip = pHome>=0.5? h : a;
  const win = Math.max(pHome,1-pHome);
  console.log(`${fx.home} v ${fx.away}: TIP ${tip.short} (${(win*100).toFixed(0)}%)  [pHome=${(pHome*100).toFixed(0)}% margin=${margin.toFixed(1)}]`);
}
