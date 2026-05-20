/* fm_delete.js — File Manager Library Delete button red paint */
(function(){
const d=window.parent.document;
const paint=(btn)=>{if(!btn)return;
const s=(k,v)=>btn.style.setProperty(k,v,'important');
const base=()=>{
s('color','#b91c1c');s('background-color','rgba(239,68,68,0.12)');
s('border','1px solid rgba(220,38,38,0.55)');
s('font-weight','600');
s('box-shadow','0 1px 2px rgba(239,68,68,0.1)');
btn.querySelectorAll('p,span').forEach((n)=>s('color','inherit'));};
const hover=()=>{
s('color','#fff');s('background-color','#dc2626');
s('border-color','#b91c1c');
s('box-shadow','0 3px 10px rgba(220,38,38,0.32)');};
base();
if(!btn.dataset.bstDelFx){btn.dataset.bstDelFx='1';
btn.addEventListener('mouseenter',hover);
btn.addEventListener('mouseleave',base);}};
const run=()=>{
d.querySelectorAll('[class*="st-key-bst_fm_del_"]').forEach((w)=>{
const btn=w.matches('button')?w:w.querySelector('button');
paint(btn);});};
run();
new MutationObserver(run).observe(d.body,{childList:true,subtree:true});
setTimeout(run,30);setTimeout(run,200);setTimeout(run,700);
})();
