/* Cutting Tools LAB — Metal AI assistant
   Local, deterministic assistant: reads the catalog already loaded by index.html,
   performs structured search and machining calculations without exposing secrets.
*/
(function(){
  const $=id=>document.getElementById(id);
  const norm=s=>String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
  const num=s=>{const n=parseFloat(String(s).replace(',','.'));return Number.isFinite(n)?n:null};
  function rows(){
    return [...document.querySelectorAll('#rows tr.data')].map(tr=>{
      const c=[...tr.cells].map(td=>td.innerText.trim());
      return {category:c[0]||'',code:c[1]||'',geom:c[2]||'',material:c[3]||'',vc:c[4]||'',f:c[5]||'',ap:c[6]||'',maker:c[7]||''};
    });
  }
  function calc(q){
    const d=num(q.d), n=num(q.n), vc=num(q.vc), f=num(q.f), vf=num(q.vf), ap=num(q.ap), ae=num(q.ae), z=num(q.z);
    const out=[];
    if(d!=null&&n!=null) out.push('Vc = '+((3.14*d*n)/1000).toFixed(2)+' m/min');
    if(d!=null&&vc!=null) out.push('n = '+((vc*1000)/(3.14*d)).toFixed(0)+' rpm');
    if(f!=null&&n!=null) out.push('Vf = '+(f*n).toFixed(2)+' mm/min');
    if(vf!=null&&n!=null) out.push('f = '+(vf/n).toFixed(4)+' mm/giro');
    if(z!=null&&f!=null&&n!=null) out.push('Vf = '+(f*z*n).toFixed(2)+' mm/min (f per dente)');
    if(vc!=null&&ap!=null&&f!=null) out.push('Q = '+(vc*ap*f).toFixed(2)+' (stima semplificata)');
    return out;
  }
  function answer(text){
    const q=norm(text), all=rows(), hits=[];
    const keywords=q.split(/\s+/).filter(x=>x.length>2);
    for(const r of all){
      const hay=norm(Object.values(r).join(' '));
      const score=keywords.reduce((s,k)=>s+(hay.includes(k)?1:0),0);
      if(score) hits.push({r,score});
    }
    hits.sort((a,b)=>b.score-a.score);
    const calcs=calc(parseQuery(text));
    let html='';
    if(calcs.length) html+='<div class="aiBox"><b>Calcolo</b><br>'+calcs.map(esc).join('<br>')+'</div>';
    if(hits.length){
      html+='<div class="aiBox"><b>Risultati dal catalogo</b>';
      hits.slice(0,8).forEach(({r})=>{html+='<div class="aiHit"><b>'+esc(r.code)+'</b> · '+esc(r.maker)+'<br><span>'+esc(r.category)+' · '+esc(r.material)+'</span><br><span>Vc '+esc(r.vc)+' · f/fz '+esc(r.f)+' · ap '+esc(r.ap)+'</span></div>';});
      html+='</div>';
    }
    if(!html) html='<div class="aiBox"><b>Non ho trovato una corrispondenza diretta.</b><br>Prova con codice inserto, produttore, materiale, operazione oppure scrivi una richiesta come: “diametro 50, 1200 rpm, calcola Vc”.</div>';
    $('aiAnswer').innerHTML=html;
  }
  function parseQuery(t){
    const q=norm(t);
    const get=(re)=>{const m=q.match(re);return m?m[1]:null};
    return {d:get(/(?:diametro|dm|da|d)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),n:get(/(?:rpm|giri|n)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),vc:get(/vc\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),f:get(/(?:f|avanzamento)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),vf:get(/vf\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),ap:get(/ap\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),ae:get(/ae\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),z:get(/(?:z|denti)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/)};
  }
  function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
  function init(){
    if(!$('aiAsk'))return;
    $('aiAsk').onclick=()=>answer($('aiInput').value);
    $('aiInput').addEventListener('keydown',e=>{if(e.key==='Enter')answer(e.target.value)});
    $('aiExamples').addEventListener('click',e=>{if(e.target.dataset.q){$('aiInput').value=e.target.dataset.q;answer(e.target.dataset.q)}});
  }
  window.addEventListener('load',()=>setTimeout(init,300));
})();