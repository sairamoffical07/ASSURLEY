const API_URL = (window.ASSURLEY_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const INSTAGRAM_URL = window.ASSURLEY_INSTAGRAM_URL || '';
const app = document.querySelector('#app');
const esc = (v='') => String(v).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const money = n => n == null || n === '' ? '—' : new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(Number(n));
const date = v => new Intl.DateTimeFormat('en-IN',{day:'2-digit',month:'short',year:'numeric'}).format(new Date(v));
const icon = (name, size=18) => {
  const p = {arrow:'<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',check:'<path d="m5 12 4 4L19 6"/>',upload:'<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>',search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-3-3"/>',instagram:'<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/>',menu:'<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/>',close:'<path d="M6 6l12 12"/><path d="M18 6 6 18"/>',file:'<path d="M6 2h8l4 4v16H6z"/><path d="M14 2v5h5"/>',shield:'<path d="M12 3 5 6v5c0 4.7 2.7 8.2 7 10 4.3-1.8 7-5.3 7-10V6z"/><path d="m9 12 2 2 4-5"/>',alert:'<path d="M12 4 3 20h18z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',eye:'<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',eyeoff:'<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>',externallink:'<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>'};
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p[name]||p.arrow}</svg>`;
};
const logo = compact => `<img class="logo${compact?' compact':''}" src="/assets/${compact?'assurley-mark.png':'assurley-wordmark.png'}" alt="Assurley — Smarter Claims. Stronger Trust."/>`;
const pill = status => {
  const raw = String(status || '');
  const s = raw.toLowerCase().replace(/_/g, '-');
  const label = raw.replace(/[-_]/g, ' ').replace(/\b\w/g, x => x.toUpperCase());
  return `<span class="pill pill-${esc(s)}">${esc(label)}</span>`;
};

async function api(path, options={}) {
  const headers = {...(!(options.body instanceof FormData)?{'Content-Type':'application/json'}:{}), ...(options.headers||{})};
  const res = await fetch(`${API_URL}${path}`, {...options, headers});
  if(!res.ok){ const data = await res.json().catch(()=>null); throw new Error(data?.detail || 'Something went wrong. Please try again.'); }
  return res.json();
}

function shell(content){
  return `<header class="topbar"><a href="#/" class="brand-link" aria-label="Assurley home">${logo(false)}</a><nav class="nav-desktop" aria-label="Primary navigation"><a href="#how-it-works">How it works</a><a href="#trust">Why Assurley</a><a href="#/track">Track claim</a><a href="#/operations">Claims team</a></nav><div class="nav-actions"><a class="btn btn-secondary desktop-only" href="#/track">Track claim</a><a class="btn btn-primary desktop-only" href="#/submit">Start a claim ${icon('arrow',16)}</a><button id="open-menu" class="icon-button mobile-only" aria-label="Open navigation">${icon('menu')}</button></div></header><main id="main">${content}</main>${footer()}`;
}
function footer(){return `<footer class="footer"><div class="footer-main"><div class="footer-brand">${logo(false)}<p>Smarter Claims. Stronger Trust.</p></div><div class="footer-links"><div><strong>Product</strong><a href="#how-it-works">How it works</a><a href="#/submit">Start a claim</a><a href="#/track">Track claim</a></div><div><strong>Operations</strong><a href="#/operations">Claims team</a><a href="#trust">Trust &amp; accountability</a></div><div><strong>Social</strong>${INSTAGRAM_URL?`<a href="${esc(INSTAGRAM_URL)}" target="_blank" rel="noopener noreferrer">${icon('instagram')} Instagram</a>`:`<span class="footer-pending">${icon('instagram')} Official link pending</span>`}</div></div></div><div class="footer-bottom"><span>© ${new Date().getFullYear()} Assurley. All rights reserved.</span><span>Insurance claim decisions remain human-controlled.</span></div></footer>`}
function bindShell(){ document.querySelector('#open-menu')?.addEventListener('click',()=>{const d=document.createElement('div');d.className='mobile-drawer';d.setAttribute('role','dialog');d.setAttribute('aria-modal','true');d.innerHTML=`<button class="icon-button drawer-close" aria-label="Close navigation">${icon('close')}</button>${logo(false)}<nav><a href="#how-it-works">How it works</a><a href="#trust">Why Assurley</a><a href="#/track">Track claim</a><a href="#/operations">Claims team</a></nav><a class="btn btn-primary" href="#/submit">Start a claim</a>`; document.body.appendChild(d); const close=()=>d.remove();d.querySelector('.drawer-close').onclick=close;d.querySelectorAll('a').forEach(a=>a.addEventListener('click',close));d.querySelector('.drawer-close').focus();}); }

function landing(){return `<section class="hero section-pad"><div class="hero-copy"><span class="eyebrow">Insurance claims, clearly handled</span><h1>Claims move faster when the paperwork does.</h1><p>Assurley brings claim submission, document checks, review, and settlement tracking into one clear workflow — with automation where it genuinely helps and human control where it matters.</p><div class="hero-actions"><a class="btn btn-primary" href="#/submit">Start a claim ${icon('arrow',16)}</a><a class="text-link" href="#how-it-works">See how it works ${icon('arrow',15)}</a></div><div class="trust-strip"><span>${icon('shield',17)} Human-controlled decisions</span><span>${icon('file',17)} Document-first workflow</span></div></div><div class="hero-demo"><div class="demo-shell"><div class="demo-topline"><span class="mini-logo">${logo(true)}</span><span class="demo-badge">Claim workflow</span></div><div class="demo-claim-head"><div><span class="small-label">New claim</span><strong>Vehicle damage</strong></div>${pill('review')}</div><div class="workflow-line">${['Submitted','Documents','Checks','Review'].map((s,i)=>`<div class="workflow-step s${i}"><span>${i<3?icon('check',13):i+1}</span><em>${s}</em></div>`).join('')}</div><div class="document-card animate-doc"><div class="doc-icon">${icon('file')}</div><div><strong>Supporting document</strong><small>Document uploaded</small></div><span class="doc-state">Reading…</span></div><div class="verification-grid"><div class="verify-row"><span>Policy details</span><strong class="ok">${icon('check',14)} Checked</strong></div><div class="verify-row delay"><span>Claim details</span><strong class="warn">${icon('alert',14)} Review</strong></div></div><div class="demo-footer"><span>Ready for a claims officer</span><span class="pulse-dot"></span></div></div></div></section>
<section id="how-it-works" class="workflow-section section-pad"><div class="section-heading narrow"><span class="eyebrow">One connected workflow</span><h2>From first report to settlement, without losing the thread.</h2><p>The interface is organized around the actual claim lifecycle — not around internal technology modules.</p></div><div class="process-rail">${[['01','Submit','Customers report the incident, insured vehicle, damage, and supporting documents through a guided flow.'],['02','Verify','Documents are stored, read, and compared with claim and policy data. Low-confidence results are surfaced for review.'],['03','Assess','Rules and configured analysis can surface inconsistencies or risk indicators without pretending uncertainty is certainty.'],['04','Review','A claims officer sees the evidence, reasoning, and history before making the final human-controlled decision.'],['05','Track','Customers see clear status updates through approval and settlement without internal insurer-only risk details.']].map(([n,t,d])=>`<article class="process-item"><span class="process-num">${n}</span><div><h3>${t}</h3><p>${d}</p></div></article>`).join('')}</div></section>
<section id="trust" class="trust-section section-pad"><div class="trust-panel"><div class="section-heading"><span class="eyebrow light">Designed for trust</span><h2>Automation that stays accountable.</h2><p>Assurley separates document extraction, rule checks, model outputs, and human decisions so users can understand what happened and why.</p></div><div class="trust-points"><div><span>01</span><strong>Human decision control</strong><p>Approval and rejection remain explicit officer actions.</p></div><div><span>02</span><strong>Visible uncertainty</strong><p>Low OCR confidence and incomplete checks are not hidden.</p></div><div><span>03</span><strong>Auditable progression</strong><p>Status changes and key actions are recorded as a claim timeline.</p></div></div></div></section>
<section class="cta-section section-pad"><div><span class="eyebrow">Ready when you are</span><h2>Start with the claim. Let the workflow do the organizing.</h2></div><div class="cta-actions"><a class="btn btn-primary" href="#/submit">Start a claim ${icon('arrow',16)}</a><a class="btn btn-secondary" href="#/track">Track an existing claim</a></div></section>`}

function inputField(label,name,type='text',required=false,extra=''){return `<label class="field"><span>${label}${required?' <b>*</b>':''}</span><input id="${name}" name="${name}" type="${type}" ${required?'required':''} ${extra}/></label>`}
function submitPage(){ return `<section class="form-page section-pad"><div class="form-intro"><a class="back-link" href="#/">← Back home</a><span class="eyebrow">Start a claim</span><h1>Tell us what happened.</h1><p>Complete the steps below. We only ask for information needed to create and review the claim.</p></div><div class="stepper" id="stepper"></div><div class="form-card"><div id="form-error"></div><form id="claim-form" novalidate><div id="step-content"></div><div class="form-actions"><button id="back-step" class="btn btn-secondary" type="button">Back</button><div class="spacer"></div><button id="next-step" class="btn btn-primary" type="button">Continue ${icon('arrow',16)}</button></div></form></div></section>`}
let submitState={step:1,files:[],data:{}};
function renderStep(){ const stepper=document.querySelector('#stepper'),content=document.querySelector('#step-content'),back=document.querySelector('#back-step'),next=document.querySelector('#next-step'); if(!stepper||!content)return;stepper.innerHTML=['Policyholder','Vehicle','Incident','Documents'].map((s,i)=>`<div class="step ${submitState.step>=i+1?'active':''} ${submitState.step>i+1?'done':''}"><span>${submitState.step>i+1?icon('check',13):i+1}</span><em>${s}</em></div>`).join(''); back.style.visibility=submitState.step===1?'hidden':'visible'; next.textContent='';next.insertAdjacentHTML('beforeend',submitState.step===4?'Submit claim':`Continue ${icon('arrow',16)}`); const d=submitState.data;
if(submitState.step===1)content.innerHTML=`<fieldset><legend>Policyholder details</legend><div class="field-grid two">${inputField('Full name','claimantName','text',true,'autocomplete="name"')}${inputField('Email address','email','email',true,'autocomplete="email"')}${inputField('Phone number','phone','tel',false,'autocomplete="tel"')}${inputField('Policy number','policyNumber','text',true)}</div></fieldset>`;
if(submitState.step===2)content.innerHTML=`<fieldset><legend>Insured vehicle</legend><div class="field-grid two">${inputField('Vehicle registration number','vehicleNumber','text',true)}${inputField('Make &amp; model','vehicleModel','text',true)}</div></fieldset>`;
if(submitState.step===3)content.innerHTML=`<fieldset><legend>Incident details</legend><div class="field-grid two">${inputField('Incident date','incidentDate','date',true,`max="${new Date().toISOString().slice(0,10)}"`)
}${inputField('Incident location','incidentLocation','text',true)}<label class="field"><span>Incident type <b>*</b></span><select id="incidentType" name="incidentType"><option>Collision</option><option>Own damage</option><option>Theft</option><option>Natural event</option><option>Other</option></select></label>${inputField('Estimated repair amount (₹)','estimatedAmount','number',false,'min="0" step="0.01"')}<label class="field span-two"><span>What happened? <b>*</b></span><textarea id="description" name="description" rows="6" required minlength="20" placeholder="Describe the incident and visible damage in your own words."></textarea><small>20 minimum characters</small></label></div></fieldset>`;
if(submitState.step===4)content.innerHTML=`<fieldset><legend>Supporting documents</legend><p class="field-help">Upload relevant repair invoices, registration documents, or damage images. Files are stored with the claim and processed asynchronously when supported by the server.</p><label class="upload-zone"><input id="docs" type="file" multiple accept="image/png,image/jpeg,image/webp,image/tiff,.pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff"/>${icon('upload',24)}<strong>Choose files</strong><span>PDF, PNG, JPG, WEBP, or TIFF</span></label><div class="file-list" id="file-list"></div><div class="review-summary"><h3>Before you submit</h3><dl><div><dt>Policyholder</dt><dd>${esc(d.claimantName||'—')}</dd></div><div><dt>Policy</dt><dd>${esc(d.policyNumber||'—')}</dd></div><div><dt>Vehicle</dt><dd>${esc(d.vehicleNumber||'—')}</dd></div><div><dt>Incident</dt><dd>${d.incidentDate?date(d.incidentDate):'—'}</dd></div></dl></div></fieldset>`;
Object.entries(d).forEach(([k,v])=>{const el=document.querySelector(`[name="${k}"]`);if(el)el.value=v}); if(submitState.step===4){document.querySelector('#docs').onchange=e=>{submitState.files=[...e.target.files];renderFiles()};renderFiles();}}
function renderFiles(){const list=document.querySelector('#file-list');if(!list)return;list.innerHTML=submitState.files.map((f,i)=>`<div class="file-row">${icon('file')}<div><strong>${esc(f.name)}</strong><small>${(f.size/1024/1024).toFixed(2)} MB</small></div><button type="button" data-remove="${i}" aria-label="Remove ${esc(f.name)}">Remove</button></div>`).join('');list.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{submitState.files.splice(Number(b.dataset.remove),1);renderFiles()})}
function collectStep(){document.querySelectorAll('#step-content [name]').forEach(el=>submitState.data[el.name]=el.value.trim?el.value.trim():el.value)}
function validateStep(){const fields=[...document.querySelectorAll('#step-content input,#step-content select,#step-content textarea')].filter(el=>el.type!=='file');for(const el of fields){if(!el.checkValidity()){el.reportValidity();return false}}return true}
async function bindSubmit(){submitState={step:1,files:[],data:{}};renderStep();document.querySelector('#back-step').onclick=()=>{collectStep();submitState.step--;renderStep()};document.querySelector('#next-step').onclick=async()=>{if(!validateStep())return;collectStep();if(submitState.step<4){submitState.step++;renderStep();return;} const err=document.querySelector('#form-error');err.innerHTML='';const btn=document.querySelector('#next-step');btn.disabled=true;btn.textContent='Submitting…';try{const payload={...submitState.data,estimatedAmount:submitState.data.estimatedAmount?Number(submitState.data.estimatedAmount):null};const claim=await api('/api/claims',{method:'POST',body:JSON.stringify(payload)});for(const file of submitState.files){const fd=new FormData();fd.append('file',file);await api(`/api/claims/${encodeURIComponent(claim.id)}/documents?email=${encodeURIComponent(submitState.data.email)}`,{method:'POST',body:fd})}document.querySelector('main').innerHTML=`<section class="form-page section-pad"><div class="success-state"><div class="success-icon">${icon('check',28)}</div><span class="eyebrow">Claim submitted</span><h1>Your claim is in the workflow.</h1><p>Keep this claim ID. You can use it with your email address to check progress.</p><div class="claim-code">${esc(claim.id)}</div><div class="success-actions"><a class="btn btn-primary" href="#/track/${encodeURIComponent(claim.id)}">Track claim ${icon('arrow',16)}</a><a class="btn btn-secondary" href="#/">Back home</a></div></div></section>`;}catch(e){err.innerHTML=`<div class="alert-error" role="alert">${esc(e.message)}</div>`;btn.disabled=false;btn.innerHTML=`Submit claim ${icon('arrow',16)}`}}}

function trackPage(initial=''){return `<section class="track-page section-pad"><div class="section-heading narrow"><span class="eyebrow">Claim tracking</span><h1>Know exactly where your claim stands.</h1><p>Enter your claim ID and the email address used during submission.</p></div><div class="track-search">${inputField('Claim ID','track-id')}${inputField('Email address','track-email','email')}<button id="track-btn" class="btn btn-primary">Track claim</button></div><div id="track-result"><div class="empty-state"><div class="empty-icon">${icon('search',25)}</div><h2>No claim loaded yet</h2><p>Your status, documents, and timeline will appear here after a successful lookup.</p></div></div></section>`}
function customerClaim(c){const stages=['submitted','documents','review','approved','settled'];const cur=Math.max(0,stages.indexOf(c.status));return `<div class="customer-claim"><div class="claim-header"><div><span class="small-label">Claim ${esc(c.id)}</span><h2>${esc(c.incidentType)}</h2><p>${esc(c.vehicleModel)} · ${esc(c.vehicleNumber)}</p></div>${pill(c.status)}</div><div class="customer-progress">${stages.map((s,i)=>`<div class="progress-node ${i<=cur?'active':''}"><span>${i<cur?icon('check',13):i+1}</span><em>${s[0].toUpperCase()+s.slice(1)}</em></div>`).join('')}</div><div class="customer-panels"><div class="info-panel"><span class="eyebrow">Current status</span><h3>${c.status==='review'?'Your claim is being reviewed.':c.status==='approved'?'Your claim has been approved.':c.status==='rejected'?'A decision has been recorded.':c.status==='settled'?'Settlement is complete.':'Your claim is moving through the workflow.'}</h3><p>${c.status==='review'?'No action is required unless the claims team contacts you for more information.':'Check the timeline below for the latest recorded activity.'}</p></div><div class="summary-panel"><dl><div><dt>Submitted</dt><dd>${date(c.createdAt)}</dd></div><div><dt>Policy</dt><dd>${esc(c.policyNumber)}</dd></div><div><dt>Estimated amount</dt><dd>${money(c.estimatedAmount)}</dd></div>${c.approvedAmount!=null?`<div><dt>Approved amount</dt><dd>${money(c.approvedAmount)}</dd></div>`:''}</dl></div></div><div class="timeline-panel"><h3>Claim timeline</h3><div class="timeline">${c.timeline.map(t=>`<div class="timeline-item"><span class="timeline-dot"></span><div><strong>${esc(t.title)}</strong><p>${esc(t.detail||'')}</p><small>${new Date(t.at).toLocaleString('en-IN')}</small></div></div>`).join('')}</div></div></div>`}
function bindTrack(initial=''){document.querySelector('#track-id').value=decodeURIComponent(initial||'');document.querySelector('#track-btn').onclick=async()=>{const id=document.querySelector('#track-id').value.trim(),email=document.querySelector('#track-email').value.trim(),result=document.querySelector('#track-result');if(!id||!email){result.innerHTML='<div class="alert-error track-alert" role="alert">Enter both the claim ID and email address.</div>';return}result.innerHTML='<div class="loading-state">Checking claim…</div>';try{const c=await api(`/api/claims/${encodeURIComponent(id)}?email=${encodeURIComponent(email)}`);result.innerHTML=customerClaim(c)}catch(e){result.innerHTML=`<div class="alert-error track-alert" role="alert">${esc(e.message)}</div>`}}}

function opsLogin(message=''){return `<div class="ops-login"><a class="ops-home" href="#/">${logo(false)}</a><div class="ops-login-card"><span class="eyebrow">Claims operations</span><h1>Authorized team access</h1><p>Enter the operations access key configured on the server. No default key is embedded in the website.</p>${message?`<div class="alert-error">${esc(message)}</div>`:''}<label class="field"><span>Operations key</span><input id="ops-key" type="password"/></label><button id="ops-login-btn" class="btn btn-primary full">Open operations</button><a href="#/" class="text-link centered">Return to website</a></div></div>`}
async function operations(){const key=sessionStorage.getItem('assurley-admin-key');if(!key){app.innerHTML=opsLogin();bindOpsLogin();return}try{const claims=await api('/api/claims',{headers:{'X-Admin-Key':key}});renderOperations(claims,key)}catch(e){sessionStorage.removeItem('assurley-admin-key');app.innerHTML=opsLogin(e.message);bindOpsLogin()}}
function bindOpsLogin(){document.querySelector('#ops-login-btn').onclick=async()=>{const key=document.querySelector('#ops-key').value.trim();if(!key)return;sessionStorage.setItem('assurley-admin-key',key);operations()}}
function renderOperations(claims,key){app.innerHTML=`<div class="ops-shell"><aside class="ops-sidebar"><a href="#/">${logo(true)}</a><nav><button id="nav-overview" class="active" aria-label="Overview">Overview</button><button id="nav-claims" aria-label="All claims">Claims</button><button id="nav-review" aria-label="Review queue">Review</button></nav><div class="ops-bottom"><a href="#/">Public website</a><button id="ops-signout">Sign out</button></div></aside><main class="ops-main"><header class="ops-header"><div><span class="eyebrow">Claims operations</span><h1>Overview</h1></div><div class="ops-search">${icon('search')}<input id="ops-search" placeholder="Search claim, policy, vehicle…" aria-label="Search claims"/></div></header><div class="metrics"><div class="metric"><span>Open claims</span><strong>${claims.filter(c=>!['settled','rejected'].includes(c.status)).length}</strong></div><div class="metric"><span>Pending review</span><strong>${claims.filter(c=>c.status==='review').length}</strong></div><div class="metric"><span>High risk</span><strong>${claims.filter(c=>c.riskLevel==='high').length}</strong></div><div class="metric"><span>Settlement complete</span><strong>${claims.filter(c=>c.status==='settled').length}</strong></div></div><section class="ops-section"><div class="ops-section-head"><div><h2>Claims requiring attention</h2><p>Submitted claims appear here as they move through the workflow.</p></div><span id="claim-count">${claims.length} claims</span></div><div id="claims-table"></div></section></main></div>`;document.querySelector('#ops-signout').onclick=()=>{sessionStorage.removeItem('assurley-admin-key');operations()};const table=document.querySelector('#claims-table');const navOverview=document.querySelector('#nav-overview'),navClaims=document.querySelector('#nav-claims'),navReview=document.querySelector('#nav-review');const setNav=(el)=>{[navOverview,navClaims,navReview].forEach(x=>x?.classList.remove('active'));el?.classList.add('active')};navOverview.onclick=()=>{setNav(navOverview);draw(claims);window.scrollTo({top:0,behavior:'smooth'})};navClaims.onclick=()=>{setNav(navClaims);draw(claims);document.querySelector('.ops-section')?.scrollIntoView({behavior:'smooth'})};navReview.onclick=()=>{setNav(navReview);draw(claims.filter(c=>c.status==='review'));document.querySelector('.ops-section')?.scrollIntoView({behavior:'smooth'})};function draw(list){document.querySelector('#claim-count').textContent=`${list.length} claims`;if(!list.length){table.innerHTML=`<div class="empty-table">${icon('shield',26)}<h3>No matching claims</h3><p>Newly submitted claims will appear here.</p></div>`;return}table.innerHTML=`<div class="table-wrap"><table><thead><tr><th>Claim</th><th>Policyholder</th><th>Vehicle</th><th>Status</th><th>Risk</th><th>Submitted</th></tr></thead><tbody>${list.map(c=>`<tr tabindex="0" data-claim="${esc(c.id)}"><td><strong>${esc(c.id)}</strong><small>${esc(c.policyNumber)}</small></td><td>${esc(c.claimantName)}</td><td>${esc(c.vehicleNumber)}<small>${esc(c.vehicleModel)}</small></td><td>${pill(c.status)}</td><td>${pill(c.riskLevel)}</td><td>${date(c.createdAt)}</td></tr>`).join('')}</tbody></table></div>`;table.querySelectorAll('[data-claim]').forEach(r=>{const open=()=>openDrawer(claims.find(c=>c.id===r.dataset.claim),key,claims);r.onclick=open;r.onkeydown=e=>{if(e.key==='Enter')open()}})}draw(claims);document.querySelector('#ops-search').oninput=e=>{const q=e.target.value.toLowerCase();draw(claims.filter(c=>`${c.id} ${c.claimantName} ${c.policyNumber} ${c.vehicleNumber}`.toLowerCase().includes(q)))}}

// ---------------------------------------------------------------------------
// Admin drawer — helper renderers
// ---------------------------------------------------------------------------

function renderVerifyStatus(status) {
  const map = {
    'MATCH': 'verify-match',
    'MISMATCH': 'verify-mismatch',
    'REVIEW': 'verify-review',
    'NOT_AVAILABLE': 'verify-na',
  };
  const cls = map[status] || 'verify-na';
  return `<span class="verify-badge ${cls}">${esc(status ? status.replace('_',' ') : 'N/A')}</span>`;
}

function renderDocumentsSection(c, key) {
  if (!c.documents || !c.documents.length) {
    return `<p class="muted">No supporting documents were uploaded.</p>`;
  }
  return `<div class="drawer-docs">${c.documents.map(d => {
    const conf = d.ocrConfidence != null ? `${Math.round(d.ocrConfidence * 100)}%` : null;
    const hasText = !!d.extractedText;
    const canView = !!d.storedName;
    const docId = d.id;
    const statusUpper = (d.ocrStatus || d.status || 'UPLOADED').toUpperCase();
    const isProcessing = statusUpper === 'PROCESSING';
    const isFailed = statusUpper === 'FAILED';
    const isLowConf = statusUpper === 'LOW_CONFIDENCE' || statusUpper === 'REVIEW_REQUIRED';

    let fileType = '';
    if (d.type) {
      const parts = d.type.split('/');
      fileType = (parts[1] || parts[0]).toUpperCase().replace('JPEG', 'JPG');
    }
    const pageText = (d.pageCount && d.pageCount > 1) ? ` · ${d.pageCount} pages` : '';

    let docTypePill = d.docType ? pill(d.docType) : '';
    return `<div class="drawer-doc" id="doc-${esc(docId)}">
      <div class="drawer-doc-top">
        <div class="drawer-doc-meta">
          ${icon('file')}
          <div>
            <strong>${esc(d.name)}</strong>
            <small>${fileType ? esc(fileType) + ' · ' : ''}${pill(d.ocrStatus || d.status)}${docTypePill ? ' · ' + docTypePill : ''}${conf ? ` · OCR ${conf}` : ''}${pageText}</small>
          </div>
        </div>
        <div class="drawer-doc-actions">
          ${canView
            ? `<button class="btn btn-secondary btn-xs doc-view-btn" data-docid="${esc(docId)}" data-claimid="${esc(c.id)}">${icon('externallink',14)} View</button>`
            : `<button class="btn btn-secondary btn-xs" disabled title="File reference unavailable">${icon('externallink',14)} View</button>`
          }
          ${hasText
            ? `<button class="btn btn-secondary btn-xs doc-ocr-btn" data-docid="${esc(docId)}">${icon('eye',14)} OCR Text</button>`
            : `<button class="btn btn-secondary btn-xs" disabled title="No OCR text available">${icon('eyeoff',14)} No OCR</button>`
          }
          <button class="btn btn-secondary btn-xs doc-reprocess-btn" data-docid="${esc(docId)}" data-claimid="${esc(c.id)}" ${isProcessing ? 'disabled' : ''}>Reprocess</button>
        </div>
      </div>
      ${isProcessing ? `<div class="doc-status-banner banner-processing"><span class="pulse-dot"></span> Processing document with Tesseract OCR…</div>` : ''}
      ${isLowConf ? `<div class="doc-status-banner banner-warning">${icon('alert',13)} Low OCR confidence — manual verification recommended.</div>` : ''}
      ${isFailed ? `<div class="doc-status-banner banner-danger">${icon('alert',13)} Assurley could not reliably read this document.</div>` : ''}
      ${hasText ? `<div class="ocr-panel" id="ocr-${esc(docId)}" hidden><pre class="ocr-text">${esc(d.extractedText)}</pre></div>` : ''}
    </div>`;
  }).join('')}</div>`;
}

function renderExtractedSection(c) {
  const docs = (c.documents || []).filter(d => d.extractedFields && Object.keys(d.extractedFields).length > 0);
  if (!docs.length) return '';
  
  return docs.map(d => {
    const docType = d.docType || 'UNKNOWN';
    let title = 'Extracted Information';
    if (docType === 'REPAIR_INVOICE') title = 'Invoice Details';
    else if (docType === 'VEHICLE_RC') title = 'Registration Certificate';
    else if (docType === 'DRIVING_LICENCE') title = 'Driving Licence';
    else if (docType === 'INSURANCE_POLICY') title = 'Policy Document';
    else if (docType === 'POLICE_FIR') title = 'Police FIR';

    const fields = Object.entries(d.extractedFields);
    if (!fields.length) return '';

    const formatLabel = k => k.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase());
    
    const rows = fields.map(([k, f]) => {
      const val = f && f.value ? esc(f.value) : '<span class="muted">—</span>';
      return `<div class="extracted-row"><dt>${esc(formatLabel(k))}</dt><dd>${val}</dd></div>`;
    }).join('');

    return `<div class="drawer-section">
      <h3>${esc(title)} <span class="section-badge">${esc(d.name)}</span></h3>
      <dl class="extracted-list">${rows}</dl>
    </div>`;
  }).join('');
}

function renderVerificationSection(c) {
  const docs = (c.documents || []).filter(d => d.verification);
  if (!docs.length) return '';
  // Use verification from first doc that has it; merge per-check for best status
  const allChecks = docs.map(d => d.verification);
  // For each check key, pick the most notable status (MISMATCH > REVIEW > MATCH > NOT_AVAILABLE)
  const rank = s => ({MISMATCH:3,REVIEW:2,MATCH:1,NOT_AVAILABLE:0}[s]||0);
  const merged = {};
  for (const checks of allChecks) {
    for (const [key, check] of Object.entries(checks)) {
      if (!merged[key] || rank(check.status) > rank(merged[key].status)) {
        merged[key] = check;
      }
    }
  }
  if (!Object.keys(merged).length) return '';
  const rows = Object.values(merged).map(check => `
    <div class="verify-row-admin">
      <div class="verify-label">${esc(check.label)}</div>
      <div class="verify-values">
        <div><span class="verify-source-tag">Policy/Claim</span> ${check.claimValue ? esc(check.claimValue) : '<span class="muted">—</span>'}</div>
        <div><span class="verify-source-tag">Invoice</span> ${check.invoiceValue ? esc(check.invoiceValue) : '<span class="muted">—</span>'}</div>
      </div>
      ${renderVerifyStatus(check.status)}
    </div>`).join('');
  return `<div class="drawer-section">
    <h3>Verification Checks</h3>
    <div class="verify-grid-admin">${rows}</div>
  </div>`;
}

function renderRiskSection(c) {
  const risk = c.riskAnalysis;
  if (!risk) {
    // Existing "not evaluated" state
    return `<div class="drawer-section">
      <h3>Risk Analysis</h3>
      <div class="analysis-note">${icon('shield')}<div><strong>Not yet evaluated</strong><p>Risk analysis runs after documents are processed.</p></div></div>
    </div>`;
  }
  if (risk.method !== 'RULE_BASED') {
    return `<div class="drawer-section"><h3>Risk Analysis</h3><div class="analysis-note">${icon('shield')}<div><strong>Unknown method</strong></div></div></div>`;
  }
  const levelClass = { low: 'pill-low', medium: 'pill-medium', high: 'pill-high' }[risk.level] || 'pill-not-evaluated';
  const reasons = (risk.reasons || []).map(r =>
    `<li class="risk-reason"><span>${esc(r.description)}</span><span class="risk-source-tag source-${(r.source||'').toLowerCase()}">${esc(r.source||'RULE')}</span><span class="risk-points">+${r.points}</span></li>`
  ).join('');
  return `<div class="drawer-section">
    <h3>Risk Analysis</h3>
    <div class="risk-panel">
      <div class="risk-header">
        <div class="risk-level-block">
          <span class="pill ${levelClass}">${esc(risk.level ? risk.level.toUpperCase() : '—')}</span>
          <span class="risk-score">${risk.score}<span class="risk-denom">/100</span></span>
        </div>
        <span class="badge-rule-based">Rule-based analysis</span>
      </div>
      ${reasons ? `<div class="risk-reasons-block"><p class="risk-reasons-label">Why this claim was flagged</p><ul class="risk-reasons">${reasons}</ul></div>` : '<p class="muted" style="margin:10px 0 0">No specific rules were triggered.</p>'}
      <div class="risk-recommendation"><strong>Recommendation</strong><p>${esc(risk.recommendation)}</p></div>
    </div>
  </div>`;
}

function openDrawer(c, key, claims) {
  const bg = document.createElement('div');
  bg.className = 'drawer-backdrop';
  bg.innerHTML = `<aside class="claim-drawer" aria-label="Claim ${esc(c.id)}">
    <button class="icon-button drawer-close" aria-label="Close claim">${icon('close')}</button>
    <div class="drawer-head">
      <span class="small-label">${esc(c.id)}</span>
      <h2>${esc(c.claimantName)}</h2>
      <p>${esc(c.vehicleModel)} · ${esc(c.vehicleNumber)}</p>
      <div class="drawer-pills">${pill(c.status)}${pill(c.riskLevel)}</div>
    </div>
    <div class="drawer-section">
      <h3>Claim summary</h3>
      <dl class="detail-list">
        <div><dt>Policy</dt><dd>${esc(c.policyNumber)}</dd></div>
        <div><dt>Incident date</dt><dd>${date(c.incidentDate)}</dd></div>
        <div><dt>Location</dt><dd>${esc(c.incidentLocation)}</dd></div>
        <div><dt>Estimated amount</dt><dd>${money(c.estimatedAmount)}</dd></div>
      </dl>
      <p class="claim-description">${esc(c.description)}</p>
    </div>
    <div class="drawer-section">
      <div class="section-inline"><h3>Documents</h3><span>${c.documents.length}</span></div>
      ${renderDocumentsSection(c, key)}
    </div>
    ${renderExtractedSection(c)}
    ${renderVerificationSection(c)}
    ${renderRiskSection(c)}
    <div class="drawer-section">
      <h3>Human decision</h3>
      <div id="decision-error"></div>
      <label class="field"><span>Decision note</span><textarea id="decision-note" rows="4" placeholder="Record the reasoning for the decision.">${esc(c.decisionNote||'')}</textarea></label>
      <label class="field"><span>Approved settlement amount (₹)</span><input id="approved-amount" type="number" min="0" step="0.01" value="${esc(c.approvedAmount??'')}"/></label>
      <div class="decision-actions">
        ${c.status==='approved'
          ? '<button id="settle" class="btn btn-primary">Mark settlement complete</button>'
          : '<button id="reject" class="btn btn-danger">Reject claim</button><button id="approve" class="btn btn-primary">Approve claim</button>'
        }
      </div>
    </div>
  </aside>`;

  document.body.appendChild(bg);
  const close = () => bg.remove();
  bg.querySelector('.drawer-close').onclick = close;
  bg.onmousedown = e => { if (e.target === bg) close(); };

  // View Document buttons (fetch with admin key, open blob URL)
  bg.querySelectorAll('.doc-view-btn').forEach(btn => {
    btn.onclick = async () => {
      const claimId = btn.dataset.claimid;
      const docId = btn.dataset.docid;
      btn.disabled = true;
      btn.textContent = 'Opening…';
      try {
        const res = await fetch(`${API_URL}/api/claims/${encodeURIComponent(claimId)}/documents/${encodeURIComponent(docId)}/file`, {
          headers: { 'X-Admin-Key': key }
        });
        if (!res.ok) {
          const err = await res.json().catch(() => null);
          throw new Error(err?.detail || 'Could not load document.');
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        // Revoke after a delay to allow the tab to load
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      } catch (e) {
        alert('Could not open document: ' + e.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = `${icon('externallink',14)} View`;
      }
    };
  });

  // OCR Text toggle buttons
  bg.querySelectorAll('.doc-ocr-btn').forEach(btn => {
    btn.onclick = () => {
      const docId = btn.dataset.docid;
      const panel = bg.querySelector(`#ocr-${docId}`);
      if (!panel) return;
      const showing = !panel.hidden;
      panel.hidden = showing;
      btn.innerHTML = showing ? `${icon('eye',14)} OCR Text` : `${icon('eyeoff',14)} Hide OCR`;
    };
  });

  // Reprocess Document buttons
  bg.querySelectorAll('.doc-reprocess-btn').forEach(btn => {
    btn.onclick = async () => {
      const claimId = btn.dataset.claimid;
      const docId = btn.dataset.docid;
      btn.disabled = true;
      btn.textContent = 'Starting...';
      try {
        const updated = await api(`/api/claims/${encodeURIComponent(claimId)}/documents/${encodeURIComponent(docId)}/reprocess`, {
          method: 'POST',
          headers: { 'X-Admin-Key': key }
        });
        const idx = claims.findIndex(x => x.id === updated.id);
        claims[idx] = updated;
        close();
        renderOperations(claims, key);
        openDrawer(updated, key, claims);
      } catch (e) {
        alert('Could not reprocess document: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Reprocess';
      }
    };
  });

  // Decision handlers (unchanged)
  async function decide(decision) {
    const note = bg.querySelector('#decision-note').value.trim();
    const amount = bg.querySelector('#approved-amount').value;
    if (!note) { bg.querySelector('#decision-error').innerHTML = '<div class="alert-error">Add a decision note before saving.</div>'; return; }
    if (decision === 'approved' && !amount) { bg.querySelector('#decision-error').innerHTML = '<div class="alert-error">Approved claims require a settlement amount.</div>'; return; }
    try {
      const updated = await api(`/api/claims/${encodeURIComponent(c.id)}/decision`, {
        method: 'POST',
        headers: { 'X-Admin-Key': key },
        body: JSON.stringify({ decision, note, approvedAmount: decision === 'approved' ? Number(amount) : null }),
      });
      const idx = claims.findIndex(x => x.id === updated.id);
      claims[idx] = updated;
      close();
      renderOperations(claims, key);
    } catch (e) {
      bg.querySelector('#decision-error').innerHTML = `<div class="alert-error">${esc(e.message)}</div>`;
    }
  }

  if (c.status === 'approved') {
    bg.querySelector('#settle').onclick = async () => {
      try {
        const updated = await api(`/api/claims/${encodeURIComponent(c.id)}/settle`, {
          method: 'POST',
          headers: { 'X-Admin-Key': key },
        });
        const idx = claims.findIndex(x => x.id === updated.id);
        claims[idx] = updated;
        close();
        renderOperations(claims, key);
      } catch (e) {
        bg.querySelector('#decision-error').innerHTML = `<div class="alert-error">${esc(e.message)}</div>`;
      }
    };
  } else {
    bg.querySelector('#reject').onclick = () => decide('rejected');
    bg.querySelector('#approve').onclick = () => decide('approved');
  }
}

async function route() {
  const hash = location.hash || '#/';
  window.scrollTo({ top: 0, behavior: 'instant' });
  if (hash.startsWith('#/operations')) { await operations(); return; }
  if (hash.startsWith('#/submit')) { app.innerHTML = shell(submitPage()); bindShell(); bindSubmit(); return; }
  if (hash.startsWith('#/track')) { const id = hash.startsWith('#/track/') ? hash.slice(8) : ''; app.innerHTML = shell(trackPage(id)); bindShell(); bindTrack(id); return; }
  app.innerHTML = shell(landing()); bindShell();
  if (hash === '#how-it-works' || hash === '#trust') setTimeout(() => document.querySelector(hash)?.scrollIntoView(), 0);
}
window.addEventListener('hashchange', route);
route();
