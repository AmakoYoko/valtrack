(function() {
  // 1) Attendre le formulaire
  function $(s, r=document) { return r.querySelector(s); }
  function readyForm(){
    const u = $('input[type="email"], input[name="username"], input#username');
    const p = $('input[type="password"], input#password');
    const submit = $('button[type="submit"], button[data-testid="btn-signin"], button:has([data-testid="btn-signin"])');
    if (u && p && submit) return {u, p, submit};
    return null;
  }
  function waitForForm(cb){
    const f = readyForm(); if (f) return cb(f);
    const mo = new MutationObserver(()=>{ const f2=readyForm(); if(f2){ mo.disconnect(); cb(f2); }});
    mo.observe(document.documentElement, {subtree:true, childList:true});
  }

  // 2) UI clavier
  function buildKeyboard(targets){
    const root = document.createElement('div');
    root.id = 'riot-softkb';
    root.style.cssText = `
      position:fixed; left:0; right:0; bottom:0; z-index:999999;
      backdrop-filter: blur(8px);
      background: rgba(15,15,20,.85); border-top:1px solid rgba(255,255,255,.12);
      padding:8px 6px; font-family: system-ui, sans-serif; color:#fff;
    `;
    const rows = [
      "1 2 3 4 5 6 7 8 9 0",
      "a z e r t y u i o p",
      "q s d f g h j k l",
      "w x c v b n m @ . - _",
    ];
    let current = targets.u;
    const out = document.createElement('div');
    out.style.cssText="display:flex; gap:6px; margin-bottom:6px;";
    const mkBtn = (label, w) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.style.cssText = `flex:${w||'0 0 auto'}; min-width:36px; padding:10px 8px; border-radius:10px; border:1px solid rgba(255,255,255,.12); background:#1f1f27;`;
      return b;
    };

    // Barre d’actions
    const focusUser = mkBtn("USER"); const focusPass = mkBtn("PASS");
    const BK = mkBtn("⌫"); const CLR = mkBtn("CLR"); const GO = mkBtn("Se connecter", "1 0 0");
    [focusUser, focusPass, BK, CLR, GO].forEach(b=>out.appendChild(b));
    root.appendChild(out);

    // Lignes de touches
    rows.forEach(r=>{
      const row = document.createElement('div');
      row.style.cssText="display:flex; gap:6px; margin:4px 0;";
      r.split(' ').forEach(ch=>{
        const b = mkBtn(ch);
        b.addEventListener('click', ()=>{
          if (!current) return;
          current.focus();
          const v = current.value || "";
          current.value = v + ch;
          current.dispatchEvent(new Event('input', {bubbles:true}));
        });
        row.appendChild(b);
      });
      root.appendChild(row);
    });

    // Espace + @ + .com
    const bottom = document.createElement('div');
    bottom.style.cssText="display:flex; gap:6px; margin-top:6px;";
    const SPACE = mkBtn("ESPACE", "1 0 0");
    const AT = mkBtn("@"); const DOTCOM = mkBtn(".com");
    [SPACE, AT, DOTCOM].forEach(b=>bottom.appendChild(b));
    root.appendChild(bottom);

    // Actions
    focusUser.onclick = ()=>{ current = targets.u; current.focus(); };
    focusPass.onclick = ()=>{ current = targets.p; current.focus(); };
    BK.onclick = ()=>{ if(!current) return; current.value = (current.value||'').slice(0,-1); current.dispatchEvent(new Event('input',{bubbles:true}))};
    CLR.onclick = ()=>{ if(!current) return; current.value = ''; current.dispatchEvent(new Event('input',{bubbles:true}))};
    GO.onclick  = ()=> targets.submit.click();
    SPACE.onclick=()=>{ if(!current) return; current.value += ' '; current.dispatchEvent(new Event('input',{bubbles:true}))};
    AT.onclick  = ()=>{ if(!current) return; current.value += '@'; current.dispatchEvent(new Event('input',{bubbles:true}))};
    DOTCOM.onclick=()=>{ if(!current) return; current.value += '.com'; current.dispatchEvent(new Event('input',{bubbles:true}))};

    // Focus init
    targets.u.addEventListener('focus', ()=> current=targets.u);
    targets.p.addEventListener('focus', ()=> current=targets.p);

    document.body.appendChild(root);
  }

  waitForForm(({u,p,submit})=>{
    // Empêche le site d’ouvrir l’OSK (inutile) et force notre focus
    u.setAttribute('inputmode','text'); p.setAttribute('inputmode','text');
    buildKeyboard({u,p,submit});
  });
})();
