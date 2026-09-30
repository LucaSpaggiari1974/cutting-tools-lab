/* Cutting Tools LAB — Metal AI core
   Deterministic first: formulas and structured catalog data are calculated locally.
   Web/backend research can be attached through window.METAL_AI_WEB_SEARCH_URL.
*/
(function(){
  const $=id=>document.getElementById(id);
  const norm=s=>String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
  const num=s=>{if(s==null)return null;const n=parseFloat(String(s).replace(',','.'));return Number.isFinite(n)?n:null};
  const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const PI=3.14;

  function rows(){
    return [...document.querySelectorAll('#rows tr.data')].map(tr=>{
      const c=[...tr.cells].map(td=>td.innerText.trim());
      return {category:c[0]||'',code:c[1]||'',geom:c[2]||'',material:c[3]||'',vc:c[4]||'',f:c[5]||'',ap:c[6]||'',maker:c[7]||''};
    });
  }

  function parseQuery(t){
    const q=norm(t);
    const get=(re)=>{const m=q.match(re);return m?m[1]:null};
    return {
      d:get(/(?:diametro|diam|dm|da|\bd)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),
      n:get(/(?:rpm|giri(?:\/min)?|n)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),
      vc:get(/(?:vc|velocita(?: di)? taglio)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),
      f:get(/(?:\bf\b|avanzamento(?:\/giro| per giro)?|fz)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),
      vf:get(/(?:vf|avanzamento(?:\s+minuto|\/min))\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),
      ap:get(/(?:ap|profondita)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),
      ae:get(/(?:ae|larghezza|impegno)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),
      z:get(/(?:z|denti)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),
      l:get(/(?:lunghezza|l)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/),
      h:get(/(?:altezza|h)\s*[=:]?\s*(\d+(?:[.,]\d+)?)/)
    };
  }

  function calc(q){
    const d=num(q.d),n=num(q.n),vc=num(q.vc),f=num(q.f),vf=num(q.vf),ap=num(q.ap),ae=num(q.ae),z=num(q.z);
    const out=[];
    if(d!=null&&n!=null) out.push(['Vc',(PI*d*n/1000),'m/min','Vc = 3,14 × D × n / 1000']);
    if(d!=null&&vc!=null) out.push(['n',(vc*1000)/(PI*d),'rpm','n = Vc × 1000 / (3,14 × D)']);
    if(f!=null&&n!=null) out.push(['Vf',f*n,'mm/min','Vf = f × n']);
    if(vf!=null&&n!=null) out.push(['f',vf/n,'mm/giro','f = Vf / n']);
    if(z!=null&&f!=null&&n!=null) out.push(['Vf',f*z*n,'mm/min','Vf = fz × z × n']);
    if(vc!=null&&ap!=null&&ae!=null) out.push(['Q',vc*ap*ae,'cm³/min*','stima semplificata; la definizione dipende dalla strategia']);
    return out;
  }

  function geometry(text,q){
    const s=norm(text), out=[];
    if(/angolo.*(triangolo|retto)|triangolo.*angolo/.test(s)&&num(q.h)!=null&&num(q.l)!=null){
      const a=Math.atan2(num(q.h),num(q.l))*180/Math.PI;
      out.push(['Angolo',a,'°','atan(h/l)']);
    }
    return out;
  }

  function catalogSearch(text){
    const q=norm(text), all=rows(), keys=q.split(/\s+/).filter(x=>x.length>2);
    return all.map(r=>{
      const hay=norm(Object.values(r).join(' '));
      const score=keys.reduce((s,k)=>s+(hay.includes(k)?1:0),0);
      return {r,score};
    }).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).slice(0,8);
  }

  function needsResearch(text){
    const q=norm(text);
    return /norma|iso\b|en\b|din\b|materiale|acciaio|inox|inconel|titanio|ghisa|superlega|nuovo inserto|ultimo|aggiornato|produttore|catalogo|mola|rettifica|evolvente|vite|problema|vibraz|rottura|usura|finitura|temperatura|forza/.test(q);
  }

  function render(text){
    const q=parseQuery(text), calculations=[...calc(q),...geometry(text,q)], hits=catalogSearch(text);
    let html='';
    if(calculations.length){
      html+='<div class="aiBox"><b>Calcolo verificabile</b>';
      calculations.forEach(([name,val,unit,formula])=>{
        html+='<div class="aiHit"><b>'+esc(name)+' = '+esc(Number(val).toFixed(3))+' '+esc(unit)+'</b><br><span>'+esc(formula)+'</span></div>';
      });
      html+='</div>';
    }
    if(hits.length){
      html+='<div class="aiBox"><b>Catalogo locale</b>';
      hits.forEach(({r})=>html+='<div class="aiHit"><b>'+esc(r.code)+'</b> · '+esc(r.maker)+'<br><span>'+esc(r.category)+' · '+esc(r.material)+'</span><br><span>Vc '+esc(r.vc)+' · f/fz '+esc(r.f)+' · ap '+esc(r.ap)+'</span></div>');
      html+='</div>';
    }
    if(needsResearch(text)){
      html+='<div class="aiBox"><b>Ricerca tecnica</b><br><span>Questa richiesta può dipendere da dati aggiornati di produttori, norme o condizioni reali di lavorazione. Il dato web va verificato e associato a fonte e data; non viene inventato.</span></div>';
    }
    if(!html) html='<div class="aiBox"><b>Analisi metalmeccanica</b><br><span>Posso analizzare il problema, eseguire i calcoli disponibili e interrogare il catalogo. Per dati esterni non presenti localmente serve il collegamento al motore web tecnico.</span></div>';
    $('aiAnswer').innerHTML=html;
    return {calculations,hits,research:needsResearch(text)};
  }

  function spoken(text,result){
    if(result.calculations.length){
      return result.calculations.map(x=>x[0]+' uguale '+Number(x[1]).toFixed(2)+' '+x[2]).join('. ')+'.';
    }
    if(result.hits.length) return 'Ho trovato '+result.hits.length+' corrispondenze nel catalogo locale. Il primo risultato è '+result.hits[0].r.code+'.';
    if(result.research) return 'Per questa domanda serve una verifica tecnica su dati esterni aggiornati. Non invento il parametro.';
    return 'Ho analizzato la richiesta. Servono ulteriori dati tecnici per produrre un calcolo verificabile.';
  }
  function speak(text){
    try{if(!('speechSynthesis' in window))return;window.speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang='it-IT';u.rate=.95;window.speechSynthesis.speak(u)}catch(_){}
  }
  function answerAndSpeak(text){
    const result=render(text);
    if(String(text||'').trim()) speak(spoken(text,result));
  }

  function init(){
    if(!$('aiAsk'))return;
    $('aiAsk').onclick=()=>answerAndSpeak($('aiInput').value);
    $('aiInput').addEventListener('keydown',e=>{if(e.key==='Enter')answerAndSpeak(e.target.value)});
    const mic=$('aiVoice'),SR=window.SpeechRecognition||window.webkitSpeechRecognition;
    if(mic&&SR){
      const rec=new SR();rec.lang='it-IT';rec.interimResults=false;rec.maxAlternatives=1;
      rec.onstart=()=>{mic.textContent='🎙️ Ascolto…';mic.disabled=true};
      rec.onend=()=>{mic.textContent='🎙️ Parla';mic.disabled=false};
      rec.onerror=()=>{mic.textContent='🎙️ Parla';mic.disabled=false};
      rec.onresult=e=>{const t=e.results[0][0].transcript;$('aiInput').value=t;answerAndSpeak(t)};
      mic.onclick=()=>{try{rec.start()}catch(_){}};
    }else if(mic){mic.disabled=true;mic.title='Riconoscimento vocale non supportato da questo browser';}
    const ex=$('aiExamples');if(ex)ex.addEventListener('click',e=>{if(e.target.dataset.q){$('aiInput').value=e.target.dataset.q;render(e.target.dataset.q)}});
  }
  window.MetalAI={answer:render,calculate:q=>[...calc(q),...geometry('',q)],version:'2.0-metal-core'};
  window.addEventListener('load',()=>setTimeout(init,300));
})();