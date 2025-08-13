window.ui = (function(){
  let el, titolo, testo, btnOk, btnAnnulla, sfondo;

  function prepara(){
    if(el) return;
    el = document.getElementById('app-modal');
    titolo = document.getElementById('modale-titolo');
    testo = document.getElementById('modale-testo');
    btnOk = document.getElementById('modale-ok');
    btnAnnulla = document.getElementById('modale-annulla');
    sfondo = el.querySelector('.modale__sfondo');
  }

  function apri({messaggio, intestazione='Messaggio', testoOk='OK', testoAnnulla=null}={}){
    prepara();
    titolo.textContent = intestazione;
    testo.innerHTML = messaggio || '';
    btnOk.textContent = testoOk || 'OK';
    btnAnnulla.style.display = testoAnnulla ? '' : 'none';
    if(testoAnnulla) btnAnnulla.textContent = testoAnnulla;

    el.classList.remove('nascosta');
    requestAnimationFrame(()=>{
      el.classList.add('mostra');
      document.body.classList.add('modale-aperta');
      btnOk.focus();
    });
  }

  function chiudi(){
    if(!el) return;
    el.classList.remove('mostra');
    document.body.classList.remove('modale-aperta');
    setTimeout(()=> el.classList.add('nascosta'), 200);
  }

  async function avviso(messaggio, intestazione='Avviso', testoOk='OK'){
    prepara();
    return new Promise(resolve=>{
      apri({messaggio, intestazione, testoOk});
      const chiudiOk = ()=>{ pulisci(); resolve(); };
      const pulisci = ()=>{
        btnOk.removeEventListener('click', chiudiOk);
        sfondo.removeEventListener('click', clickSfondo);
        document.removeEventListener('keydown', tasto);
        chiudi();
      };
      const clickSfondo = (e)=>{ if(e.target.dataset.chiudi) chiudiOk(); };
      const tasto = (e)=>{ if(e.key==='Enter' || e.key==='Escape') chiudiOk(); };

      btnOk.addEventListener('click', chiudiOk);
      sfondo.addEventListener('click', clickSfondo);
      document.addEventListener('keydown', tasto);
    });
  }

  async function conferma(messaggio, {intestazione='Confermi?', testoOk='Conferma', testoAnnulla='Annulla'}={}){
    prepara();
    return new Promise(resolve=>{
      apri({messaggio, intestazione, testoOk, testoAnnulla});
      const chiudiOk = ()=>{ pulisci(); resolve(true); };
      const chiudiAnnulla = ()=>{ pulisci(); resolve(false); };
      const pulisci = ()=>{
        btnOk.removeEventListener('click', chiudiOk);
        btnAnnulla.removeEventListener('click', chiudiAnnulla);
        sfondo.removeEventListener('click', clickSfondo);
        document.removeEventListener('keydown', tasto);
        chiudi();
      };
      const clickSfondo = (e)=>{ if(e.target.dataset.chiudi) chiudiAnnulla(); };
      const tasto = (e)=>{ if(e.key==='Escape') chiudiAnnulla(); if(e.key==='Enter') chiudiOk(); };

      btnOk.addEventListener('click', chiudiOk);
      btnAnnulla.addEventListener('click', chiudiAnnulla);
      sfondo.addEventListener('click', clickSfondo);
      document.addEventListener('keydown', tasto);
    });
  }

  return { avviso, conferma };
})();