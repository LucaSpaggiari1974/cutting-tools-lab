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
    return /norma|iso\b|en\b|din\b|materiale|acciaio|inox|inconel|titanio|ghisa|superlega|nuovo inserto|ultimo|aggiornato|produttore|catalogo|mola|rettifica|rettifica interna|rettifica esterna|rettifica piana|rettifica evolvente|mola a vite|vite|cbn|corindone|abrasivo|ravvivatura|dressing|truing|bruciatura|problema|vibraz|rottura|usura|finitura|temperatura|forza|parametri/.test(q);
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
  async function answerAndSpeak(text){
    const result=render(text);
    if(result.research){
      $('aiAnswer').innerHTML='<div class="aiBox"><b>Attendi e ricerca soluzione</b><br><span>Sto ricercando il problema su fonti tecniche affidabili e confronto le possibili cause. Ti mostrerò la soluzione adatta appena la ricerca è completata.</span></div>';
      try{
        const systemInstruction="Sei l'IA Metalmeccanica di Cutting Tools LAB. Quando l'utente descrive un problema come \"rugosità alta in rettifica\", devi attivare la ricerca tecnica web e non limitarti al catalogo locale. Il tuo compito principale è RISOLVERE PROBLEMI, non soltanto calcolare parametri. Quando l'utente descrive un problema tecnico, diagnosticalo, individua le cause possibili e cerca la soluzione più adatta. Quando la domanda richiede dati aggiornati o documentazione, usa la ricerca web disponibile nel backend e consulta fonti affidabili: manuali e schede dei costruttori, norme e fonti tecniche riconosciute. Confronta le fonti e cita i riferimenti usati. Puoi affrontare problemi di tornitura, fresatura, foratura, alesatura, rettifica, rettifica evolvente, mole a vite, ingranaggi, utensili, CNC, refrigerazione, vibrazioni, chatter, bruciature, usura, rotture, errori dimensionali e finitura, oltre ad altri problemi tecnici legati alle lavorazioni meccaniche. Struttura la risposta in: diagnosi, cause da verificare, soluzione operativa passo-passo, parametri/calcoli se necessari, controlli finali e fonti. Non inventare dati: se mancano informazioni indispensabili, dichiaralo e chiedi i dati necessari.";
      const catalogContext=result.hits.map(x=>x.r.code+' | '+x.r.maker+' | '+x.r.material+' | Vc '+x.r.vc+' | f/fz '+x.r.f+' | ap '+x.r.ap).join('\\n');
        const r=await fetch('https://cutting-tools-lab.vercel.app/api/metal-ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,catalogContext,systemInstruction,mode:"problem-solving-research"})});
        const j=await r.json();
        if(!r.ok) throw new Error(j.error||'Ricerca tecnica non disponibile');
        let html='<div class="aiBox"><b>Analisi tecnica aggiornata</b><div class="aiHit" style="white-space:pre-wrap">'+esc(j.answer)+'</div>';
        if(Array.isArray(j.sources)&&j.sources.length) html+='<div class="aiSources"><b>Fonti consultate</b>'+j.sources.map(s=>'<div class="aiSource"><a href="'+esc(s.url)+'" target="_blank" rel="noopener">'+esc(s.title||s.url)+'</a></div>').join('')+'</div>';
        html+='</div>';
        $('aiAnswer').innerHTML=html;
        
      }catch(e){
        $('aiAnswer').innerHTML='<div class="aiBox"><b>Ricerca tecnica non disponibile</b><br>'+esc(e.message||'Errore')+'<br><span>Il catalogo locale e i calcoli verificabili restano disponibili.</span></div>';
      }
    }else{
      
    }
    return result;
  }

  async function compressImage(file){
    return new Promise((resolve,reject)=>{
      const img=new Image(), url=URL.createObjectURL(file);
      img.onload=()=>{
        const max=1600, scale=Math.min(1,max/Math.max(img.naturalWidth,img.naturalHeight));
        const canvas=document.createElement('canvas');canvas.width=Math.round(img.naturalWidth*scale);canvas.height=Math.round(img.naturalHeight*scale);
        canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height);
        URL.revokeObjectURL(url);resolve(canvas.toDataURL('image/jpeg',.82));
      };
      img.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('Immagine non leggibile'))};img.src=url;
    });
  }
  async function analyzeImage(){
    const input=$('aiImage'), box=$('aiAnswer'), preview=$('aiImagePreview');
    if(!input||!input.files||!input.files[0]){box.innerHTML='<div class="aiBox"><b>Carica prima una foto.</b></div>';return}
    const file=input.files[0];
    try{
      const data=await compressImage(file);
      preview.style.display='block';preview.innerHTML='<img src="'+esc(data)+'" alt="Foto problema" style="max-width:100%;max-height:320px;border-radius:10px;border:1px solid #cbd7e1">';
      box.innerHTML='<div class="aiBox"><b>Analisi visiva in corso…</b><br>Sto confrontando gli indizi visibili con le cause tipiche di lavorazione.</div>';
      const r=await fetch('https://cutting-tools-lab.vercel.app/api/metal-ai-vision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:data,question:$('aiInput')?.value||''})});
      const j=await r.json(); if(!r.ok) throw new Error(j.error||'Errore server');
      box.innerHTML='<div class="aiBox"><b>Diagnosi da immagine</b><div class="aiHit" style="white-space:pre-wrap">'+esc(j.answer)+'</div><small>La diagnosi visiva è un supporto tecnico: prima di modificare parametri o utensili, verificare misure, macchina e condizioni reali.</small></div>';
      
    }catch(e){
      box.innerHTML='<div class="aiBox"><b>Analisi foto non disponibile.</b><br>'+esc(e.message||'Errore')+'</div>';
    }
  }
  function init(){
    if(!$('aiAsk'))return;
    $('aiAsk').onclick=()=>answerAndSpeak($('aiInput').value);
    $('aiInput').addEventListener('keydown',e=>{if(e.key==='Enter')answerAndSpeak(e.target.value)});
    const ex=$('aiExamples');if(ex)ex.addEventListener('click',e=>{if(e.target.dataset.q){$('aiInput').value=e.target.dataset.q;render(e.target.dataset.q)}});
    const img=$('aiImage'), imgBtn=$('aiImageAnalyze'), imgName=$('aiImageName');
    if(img) img.addEventListener('change',()=>{if(img.files[0]&&imgName)imgName.textContent=img.files[0].name});
    if(imgBtn) imgBtn.addEventListener('click',analyzeImage);
  }
  window.MetalAI={answer:render,calculate:q=>[...calc(q),...geometry('',q)],version:'2.0-metal-core'};
  window.addEventListener('load',()=>setTimeout(init,300));
})();