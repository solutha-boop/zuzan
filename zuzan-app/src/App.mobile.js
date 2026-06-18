// ZuZan Mobile — simplified view: Invoices, Expenses, Quotes
import { useState, useEffect } from "react";

// ── THEME ─────────────────────────────────────────────────────────────────────
const C = {
  bg:"#FAF7F2", surface:"#FFFFFF", border:"#E8E0D5",
  ink:"#1A1209", inkMid:"#6B5E4E", inkDim:"#B5A898",
  accent:"#C8401A", accentLt:"#C8401A12",
  green:"#2A6B3C", greenLt:"#2A6B3C12",
  gold:"#C4920A", goldLt:"#C4920A12",
  red:"#C82A2A", redLt:"#C82A2A12",
};

const BASE_URL = "https://zuzan-backend.onrender.com";
const fmt  = n => `R${Number(n||0).toLocaleString("en-ZA",{minimumFractionDigits:2})}`;
const fmtD = d => d ? new Date(d).toLocaleDateString("en-ZA",{day:"2-digit",month:"short",year:"numeric"}) : "—";

// ── API ───────────────────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  const token = localStorage.getItem("zuzan_token");
  const res = await fetch(`${BASE_URL}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token && !token.startsWith("demo_") ? {"Authorization":`Bearer ${token}`} : {}),
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || res.status); }
  return res.json();
}

// ── SHARED UI ─────────────────────────────────────────────────────────────────
const Pill = ({label, color, bg}) => (
  <span style={{background:bg,color,borderRadius:20,padding:"3px 10px",fontSize:11,fontWeight:700,textTransform:"capitalize",whiteSpace:"nowrap"}}>{label}</span>
);

const Field = ({label, children}) => (
  <div style={{marginBottom:14}}>
    <div style={{fontSize:11,fontWeight:600,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:5}}>{label}</div>
    {children}
  </div>
);

const inp = {width:"100%",padding:"12px",border:`1px solid ${C.border}`,borderRadius:10,fontSize:15,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"};

const Btn = ({label,onClick,variant="primary",disabled=false}) => {
  const styles = {
    primary: {background:C.accent,color:"#fff",border:"none"},
    secondary: {background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`},
    success: {background:C.green,color:"#fff",border:"none"},
  };
  return (
    <button onClick={onClick} disabled={disabled} style={{...styles[variant],borderRadius:12,padding:"13px 20px",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:disabled?0.5:1,flex:1}}>
      {label}
    </button>
  );
};

const Card = ({onClick,children,style={}}) => (
  <div onClick={onClick} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:"16px",marginBottom:10,cursor:onClick?"pointer":"default",...style}}>
    {children}
  </div>
);

const KPIRow = ({items}) => (
  <div style={{display:"flex",gap:8,marginBottom:16}}>
    {items.map(({label,value,color}) => (
      <div key={label} style={{flex:1,background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:"12px 10px",textAlign:"center"}}>
        <div style={{fontSize:11,color:C.inkMid,fontWeight:600,marginBottom:4,textTransform:"uppercase",letterSpacing:0.3}}>{label}</div>
        <div style={{fontSize:15,fontWeight:800,color:color||C.ink}}>{value}</div>
      </div>
    ))}
  </div>
);

const statusColor = s => ({paid:C.green,sent:C.gold,overdue:C.red,draft:C.inkMid,accepted:C.green,rejected:C.red,pending:C.gold}[s]||C.inkMid);
const statusBg    = s => ({paid:C.greenLt,sent:C.goldLt,overdue:C.redLt,draft:`${C.inkDim}20`,accepted:C.greenLt,rejected:C.redLt,pending:C.goldLt}[s]||`${C.inkDim}20`);

// ── FAB ───────────────────────────────────────────────────────────────────────
const FAB = ({onClick}) => (
  <button onClick={onClick} style={{position:"fixed",bottom:84,right:20,width:56,height:56,borderRadius:"50%",background:C.accent,color:"#fff",border:"none",fontSize:26,cursor:"pointer",boxShadow:"0 4px 16px #C8401A40",display:"flex",alignItems:"center",justifyContent:"center",zIndex:100}}>+</button>
);

// ── BOTTOM NAV ────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  {id:"invoices", label:"Invoices", icon:"🧾"},
  {id:"expenses", label:"Expenses", icon:"💳"},
  {id:"quotes",   label:"Quotes",   icon:"📋"},
];
const BottomNav = ({tab, setTab}) => (
  <div style={{position:"fixed",bottom:0,left:0,right:0,background:C.surface,borderTop:`1px solid ${C.border}`,display:"flex",zIndex:200,paddingBottom:"env(safe-area-inset-bottom,0)"}}>
    {NAV_ITEMS.map(n => (
      <button key={n.id} onClick={()=>setTab(n.id)} style={{flex:1,background:"none",border:"none",padding:"10px 0 12px",cursor:"pointer",display:"flex",flexDirection:"column",alignItems:"center",gap:3}}>
        <span style={{fontSize:22}}>{n.icon}</span>
        <span style={{fontSize:10,fontWeight:tab===n.id?700:400,color:tab===n.id?C.accent:C.inkMid}}>{n.label}</span>
        {tab===n.id && <span style={{width:20,height:2,background:C.accent,borderRadius:2}}/>}
      </button>
    ))}
  </div>
);

// ── INVOICES ──────────────────────────────────────────────────────────────────
const CATS_INCOME = ["Revenue","Interest Income","Other Income"];
const CURRENCIES  = {ZAR:{symbol:"R"},USD:{symbol:"$"},EUR:{symbol:"€"},GBP:{symbol:"£"}};

function Invoices() {
  const [invoices,   setInvoices]   = useState([]);
  const [customers,  setCustomers]  = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [showForm,   setShowForm]   = useState(false);
  const [selected,   setSelected]   = useState(null);   // view detail
  const [payModal,   setPayModal]   = useState(null);
  const [saving,     setSaving]     = useState(false);
  const [form, setForm] = useState({client:"",amount:"",desc:"",due:"",vatApplicable:true,currency:"ZAR",exchangeRate:"18.5"});

  const load = async () => {
    setLoading(true);
    try {
      const [inv, cust] = await Promise.all([api("/invoices/"), api("/customers/").catch(()=>[])]);
      setInvoices(inv.map(i=>({...i,_dbId:i.id,id:i.invoice_number||`INV-${String(i.id).padStart(3,"0")}`,client:i.client_name||i.client,amount:i.total_amount||i.amount,date:i.issue_date||i.date,due:i.due_date||i.due})));
      setCustomers(cust);
    } catch(e) { console.warn(e); }
    setLoading(false);
  };
  useEffect(()=>{ load(); },[]);

  const toZar = i => (i.currency && i.currency !== "ZAR") ? (i.amount||0)*(i.exchange_rate||i.exchangeRate||18.5) : (i.amount||0);
  const totalPaid    = invoices.filter(i=>i.status==="paid").reduce((s,i)=>s+toZar(i),0);
  const totalPending = invoices.filter(i=>["sent","pending"].includes(i.status)).reduce((s,i)=>s+toZar(i),0);
  const totalOverdue = invoices.filter(i=>i.status==="overdue").reduce((s,i)=>s+toZar(i),0);

  const handleCreate = async () => {
    if (!form.client || !form.amount || !form.desc) { alert("Client, description and amount are required."); return; }
    setSaving(true);
    try {
      const vatAmt = form.vatApplicable ? +form.amount * 0.15 : 0;
      const total  = +form.amount + vatAmt;
      await api("/invoices/", {method:"POST", body:JSON.stringify({
        client_name:  form.client, description: form.desc,
        amount:       total, vat_amount: vatAmt,
        issue_date:   new Date().toISOString().slice(0,10),
        due_date:     form.due || null,
        currency:     form.currency,
        exchange_rate: form.currency!=="ZAR" ? +form.exchangeRate : 1,
        status:       "sent",
      })});
      setForm({client:"",amount:"",desc:"",due:"",vatApplicable:true,currency:"ZAR",exchangeRate:"18.5"});
      setShowForm(false);
      load();
    } catch(e) { alert("Failed: "+e.message); }
    setSaving(false);
  };

  const recordPayment = async () => {
    try {
      await api(`/invoices/${payModal.inv._dbId||payModal.inv.id}`,{method:"PUT",body:JSON.stringify({status:"paid",paid_date:payModal.date,paid_amount_zar:+toZar(payModal.inv)||null})});
      setPayModal(null); setSelected(null); load();
    } catch(e) { alert("Failed: "+e.message); }
  };

  if (showForm) return (
    <div style={{padding:"20px 16px 100px"}}>
      <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:20}}>
        <button onClick={()=>setShowForm(false)} style={{background:"none",border:"none",fontSize:22,cursor:"pointer",color:C.ink}}>←</button>
        <h2 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:0}}>New Invoice</h2>
      </div>
      <Field label="Client">
        {customers.length > 0 ? (
          <select value={form.client} onChange={e=>setForm(v=>({...v,client:e.target.value}))} style={inp}>
            <option value="">— Select customer —</option>
            {customers.map(c=><option key={c.id} value={c.name}>{c.name}</option>)}
          </select>
        ) : (
          <input placeholder="Client name" value={form.client} onChange={e=>setForm(v=>({...v,client:e.target.value}))} style={inp}/>
        )}
      </Field>
      <Field label="Description">
        <input placeholder="e.g. Professional services — May 2026" value={form.desc} onChange={e=>setForm(v=>({...v,desc:e.target.value}))} style={inp}/>
      </Field>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
        <Field label="Amount (excl. VAT)">
          <input type="number" placeholder="0.00" value={form.amount} onChange={e=>setForm(v=>({...v,amount:e.target.value}))} style={inp}/>
        </Field>
        <Field label="Currency">
          <select value={form.currency} onChange={e=>setForm(v=>({...v,currency:e.target.value}))} style={inp}>
            {Object.keys(CURRENCIES).map(c=><option key={c}>{c}</option>)}
          </select>
        </Field>
      </div>
      {form.currency !== "ZAR" && (
        <Field label="Exchange Rate (to ZAR)">
          <input type="number" placeholder="18.50" value={form.exchangeRate} onChange={e=>setForm(v=>({...v,exchangeRate:e.target.value}))} style={inp}/>
        </Field>
      )}
      <Field label="Due Date">
        <input type="date" value={form.due} onChange={e=>setForm(v=>({...v,due:e.target.value}))} style={inp}/>
      </Field>
      <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:20,padding:"12px",background:C.accentLt,borderRadius:10}}>
        <input type="checkbox" checked={form.vatApplicable} onChange={e=>setForm(v=>({...v,vatApplicable:e.target.checked}))} style={{width:18,height:18}}/>
        <span style={{fontSize:14,color:C.ink}}>VAT applicable (15%)</span>
      </div>
      {form.amount && (
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:10,padding:14,marginBottom:20,fontSize:13}}>
          <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}><span style={{color:C.inkMid}}>Subtotal</span><span>{fmt(+form.amount)}</span></div>
          {form.vatApplicable && <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}><span style={{color:C.inkMid}}>VAT (15%)</span><span>{fmt(+form.amount*0.15)}</span></div>}
          <div style={{display:"flex",justifyContent:"space-between",fontWeight:700,borderTop:`1px solid ${C.border}`,paddingTop:8,marginTop:4}}><span>Total</span><span style={{color:C.accent}}>{fmt(+form.amount*(form.vatApplicable?1.15:1))}</span></div>
        </div>
      )}
      <div style={{display:"flex",gap:10}}>
        <Btn label="Cancel" variant="secondary" onClick={()=>setShowForm(false)}/>
        <Btn label={saving?"Saving...":"Send Invoice"} onClick={handleCreate} disabled={saving}/>
      </div>
    </div>
  );

  if (selected) return (
    <div style={{padding:"20px 16px 100px"}}>
      <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:20}}>
        <button onClick={()=>setSelected(null)} style={{background:"none",border:"none",fontSize:22,cursor:"pointer",color:C.ink}}>←</button>
        <h2 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:0}}>{selected.id}</h2>
      </div>
      <Card>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12}}>
          <div>
            <div style={{fontWeight:700,fontSize:18,color:C.ink}}>{selected.client}</div>
            <div style={{color:C.inkMid,fontSize:13,marginTop:3}}>{selected.desc}</div>
          </div>
          <Pill label={selected.status} color={statusColor(selected.status)} bg={statusBg(selected.status)}/>
        </div>
        <div style={{fontSize:28,fontWeight:800,color:C.accent,marginBottom:12}}>{fmt(toZar(selected))}</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,fontSize:13}}>
          <div><span style={{color:C.inkMid}}>Issued: </span>{fmtD(selected.date)}</div>
          <div><span style={{color:C.inkMid}}>Due: </span>{fmtD(selected.due)}</div>
          {selected.currency && selected.currency !== "ZAR" && <div><span style={{color:C.inkMid}}>Currency: </span>{selected.currency}</div>}
        </div>
      </Card>
      {selected.status !== "paid" && (
        <div style={{marginTop:10}}>
          <Btn label="Record Payment" variant="success" onClick={()=>setPayModal({inv:selected,date:new Date().toISOString().slice(0,10)})}/>
        </div>
      )}
      {payModal && payModal.inv.id === selected.id && (
        <div style={{marginTop:16,background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:16}}>
          <div style={{fontWeight:600,marginBottom:12}}>Confirm Payment</div>
          <Field label="Payment Date">
            <input type="date" value={payModal.date} onChange={e=>setPayModal(v=>({...v,date:e.target.value}))} style={inp}/>
          </Field>
          <div style={{display:"flex",gap:10}}>
            <Btn label="Cancel" variant="secondary" onClick={()=>setPayModal(null)}/>
            <Btn label="Confirm Paid" variant="success" onClick={recordPayment}/>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div style={{padding:"20px 16px 100px"}}>
      <h2 style={{fontFamily:"serif",fontSize:24,color:C.ink,margin:"0 0 16px"}}>Invoices</h2>
      <KPIRow items={[{label:"Paid",value:fmt(totalPaid),color:C.green},{label:"Pending",value:fmt(totalPending),color:C.gold},{label:"Overdue",value:fmt(totalOverdue),color:C.red}]}/>
      {loading ? <div style={{textAlign:"center",color:C.inkMid,padding:40}}>Loading...</div> : invoices.length === 0 ? (
        <div style={{textAlign:"center",color:C.inkMid,padding:40}}>No invoices yet. Tap + to create one.</div>
      ) : invoices.map(inv => (
        <Card key={inv.id} onClick={()=>setSelected(inv)}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
            <div>
              <div style={{fontWeight:700,color:C.ink,fontSize:15}}>{inv.client}</div>
              <div style={{fontSize:12,color:C.inkMid,marginTop:2}}>{inv.id} · Due {fmtD(inv.due)}</div>
            </div>
            <div style={{textAlign:"right"}}>
              <div style={{fontWeight:700,color:C.accent,fontSize:16}}>{fmt(toZar(inv))}</div>
              <Pill label={inv.status} color={statusColor(inv.status)} bg={statusBg(inv.status)}/>
            </div>
          </div>
        </Card>
      ))}
      <FAB onClick={()=>setShowForm(true)}/>
    </div>
  );
}

// ── EXPENSES ──────────────────────────────────────────────────────────────────
const EXP_CATS = ["Utilities","Telecoms","Office Supplies","Banking","Insurance","Travel","Equipment","Marketing","Professional Fees","Rent","Salaries","Other"];

function Expenses() {
  const [expenses,  setExpenses]  = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [showForm,  setShowForm]  = useState(false);
  const [saving,    setSaving]    = useState(false);
  const [form, setForm] = useState({vendor:"",amount:"",category:EXP_CATS[0],date:new Date().toISOString().slice(0,10),desc:"",vatAmount:"",vatApplicable:false});

  const load = async () => {
    setLoading(true);
    try { const d = await api("/expenses/"); setExpenses(d); } catch(e) { console.warn(e); }
    setLoading(false);
  };
  useEffect(()=>{ load(); },[]);

  const thisMonth = new Date().toISOString().slice(0,7);
  const totalMonth = expenses.filter(e=>e.date&&e.date.startsWith(thisMonth)).reduce((s,e)=>s+(e.amount||0),0);
  const totalAll   = expenses.reduce((s,e)=>s+(e.amount||0),0);

  const handleAdd = async () => {
    if (!form.vendor || !form.amount) { alert("Vendor and amount are required."); return; }
    setSaving(true);
    try {
      const vatAmt = form.vatApplicable ? +form.amount * (15/115) : 0;
      await api("/expenses/", {method:"POST", body:JSON.stringify({
        vendor: form.vendor, amount: +form.amount,
        category: form.category, date: form.date,
        description: form.desc||null,
        vat_amount: vatAmt || null,
      })});
      setForm({vendor:"",amount:"",category:EXP_CATS[0],date:new Date().toISOString().slice(0,10),desc:"",vatAmount:"",vatApplicable:false});
      setShowForm(false);
      load();
    } catch(e) { alert("Failed: "+e.message); }
    setSaving(false);
  };

  if (showForm) return (
    <div style={{padding:"20px 16px 100px"}}>
      <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:20}}>
        <button onClick={()=>setShowForm(false)} style={{background:"none",border:"none",fontSize:22,cursor:"pointer",color:C.ink}}>←</button>
        <h2 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:0}}>Add Expense</h2>
      </div>
      <Field label="Vendor / Supplier">
        <input placeholder="e.g. Eskom, Telkom, ABSA" value={form.vendor} onChange={e=>setForm(v=>({...v,vendor:e.target.value}))} style={inp}/>
      </Field>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
        <Field label="Amount (ZAR)">
          <input type="number" placeholder="0.00" value={form.amount} onChange={e=>setForm(v=>({...v,amount:e.target.value}))} style={inp}/>
        </Field>
        <Field label="Date">
          <input type="date" value={form.date} onChange={e=>setForm(v=>({...v,date:e.target.value}))} style={inp}/>
        </Field>
      </div>
      <Field label="Category">
        <select value={form.category} onChange={e=>setForm(v=>({...v,category:e.target.value}))} style={inp}>
          {EXP_CATS.map(c=><option key={c}>{c}</option>)}
        </select>
      </Field>
      <Field label="Reference (optional)">
        <input placeholder="Invoice ref, PO number..." value={form.desc} onChange={e=>setForm(v=>({...v,desc:e.target.value}))} style={inp}/>
      </Field>
      <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:20,padding:"12px",background:`${C.gold}15`,borderRadius:10}}>
        <input type="checkbox" checked={form.vatApplicable} onChange={e=>setForm(v=>({...v,vatApplicable:e.target.checked}))} style={{width:18,height:18}}/>
        <span style={{fontSize:14,color:C.ink}}>Amount includes VAT (15%)</span>
      </div>
      <div style={{display:"flex",gap:10}}>
        <Btn label="Cancel" variant="secondary" onClick={()=>setShowForm(false)}/>
        <Btn label={saving?"Saving...":"Save Expense"} onClick={handleAdd} disabled={saving}/>
      </div>
    </div>
  );

  return (
    <div style={{padding:"20px 16px 100px"}}>
      <h2 style={{fontFamily:"serif",fontSize:24,color:C.ink,margin:"0 0 16px"}}>Expenses</h2>
      <KPIRow items={[{label:"This Month",value:fmt(totalMonth),color:C.accent},{label:"All Time",value:fmt(totalAll),color:C.inkMid}]}/>
      {loading ? <div style={{textAlign:"center",color:C.inkMid,padding:40}}>Loading...</div> : expenses.length === 0 ? (
        <div style={{textAlign:"center",color:C.inkMid,padding:40}}>No expenses yet. Tap + to add one.</div>
      ) : expenses.map((exp,i) => (
        <Card key={exp.id||i}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
            <div>
              <div style={{fontWeight:700,color:C.ink,fontSize:15}}>{exp.vendor||exp.description}</div>
              <div style={{fontSize:12,color:C.inkMid,marginTop:2}}>{exp.category} · {fmtD(exp.date)}</div>
            </div>
            <div style={{fontWeight:700,color:C.red,fontSize:16,whiteSpace:"nowrap"}}>−{fmt(exp.amount)}</div>
          </div>
        </Card>
      ))}
      <FAB onClick={()=>setShowForm(true)}/>
    </div>
  );
}

// ── QUOTES ────────────────────────────────────────────────────────────────────
function Quotes() {
  const [quotes,     setQuotes]     = useState([]);
  const [customers,  setCustomers]  = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [showForm,   setShowForm]   = useState(false);
  const [saving,     setSaving]     = useState(false);
  const [form, setForm] = useState({client:"",amount:"",desc:"",vatApplicable:true,currency:"ZAR",validDays:"30"});

  const load = async () => {
    setLoading(true);
    try {
      const [q, c] = await Promise.all([api("/quotes/"), api("/customers/").catch(()=>[])]);
      setQuotes(q); setCustomers(c);
    } catch(e) { console.warn(e); }
    setLoading(false);
  };
  useEffect(()=>{ load(); },[]);

  const accepted = quotes.filter(q=>q.status==="accepted").reduce((s,q)=>s+(q.total_amount||q.amount||0),0);
  const pending  = quotes.filter(q=>q.status==="sent").reduce((s,q)=>s+(q.total_amount||q.amount||0),0);

  const handleCreate = async (status="draft") => {
    if (!form.client || !form.amount || !form.desc) { alert("Client, description and amount are required."); return; }
    setSaving(true);
    try {
      const vatAmt = form.vatApplicable ? +form.amount * 0.15 : 0;
      const total  = +form.amount + vatAmt;
      const expiry = new Date(Date.now() + (+form.validDays||30)*86400000).toISOString().slice(0,10);
      await api("/quotes/", {method:"POST", body:JSON.stringify({
        client_name: form.client, description: form.desc,
        amount: total, vat_amount: vatAmt,
        currency: form.currency, valid_until: expiry, status,
      })});
      setForm({client:"",amount:"",desc:"",vatApplicable:true,currency:"ZAR",validDays:"30"});
      setShowForm(false);
      load();
    } catch(e) { alert("Failed: "+e.message); }
    setSaving(false);
  };

  if (showForm) return (
    <div style={{padding:"20px 16px 100px"}}>
      <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:20}}>
        <button onClick={()=>setShowForm(false)} style={{background:"none",border:"none",fontSize:22,cursor:"pointer",color:C.ink}}>←</button>
        <h2 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:0}}>New Quote</h2>
      </div>
      <Field label="Client">
        {customers.length > 0 ? (
          <select value={form.client} onChange={e=>setForm(v=>({...v,client:e.target.value}))} style={inp}>
            <option value="">— Select customer —</option>
            {customers.map(c=><option key={c.id} value={c.name}>{c.name}</option>)}
          </select>
        ) : (
          <input placeholder="Client name" value={form.client} onChange={e=>setForm(v=>({...v,client:e.target.value}))} style={inp}/>
        )}
      </Field>
      <Field label="Description">
        <input placeholder="e.g. Website development — Phase 1" value={form.desc} onChange={e=>setForm(v=>({...v,desc:e.target.value}))} style={inp}/>
      </Field>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
        <Field label="Amount (excl. VAT)">
          <input type="number" placeholder="0.00" value={form.amount} onChange={e=>setForm(v=>({...v,amount:e.target.value}))} style={inp}/>
        </Field>
        <Field label="Valid for (days)">
          <input type="number" placeholder="30" value={form.validDays} onChange={e=>setForm(v=>({...v,validDays:e.target.value}))} style={inp}/>
        </Field>
      </div>
      <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:20,padding:"12px",background:C.accentLt,borderRadius:10}}>
        <input type="checkbox" checked={form.vatApplicable} onChange={e=>setForm(v=>({...v,vatApplicable:e.target.checked}))} style={{width:18,height:18}}/>
        <span style={{fontSize:14,color:C.ink}}>VAT applicable (15%)</span>
      </div>
      {form.amount && (
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:10,padding:14,marginBottom:20,fontSize:13}}>
          <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}><span style={{color:C.inkMid}}>Subtotal</span><span>{fmt(+form.amount)}</span></div>
          {form.vatApplicable && <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}><span style={{color:C.inkMid}}>VAT (15%)</span><span>{fmt(+form.amount*0.15)}</span></div>}
          <div style={{display:"flex",justifyContent:"space-between",fontWeight:700,borderTop:`1px solid ${C.border}`,paddingTop:8,marginTop:4}}><span>Total</span><span style={{color:C.accent}}>{fmt(+form.amount*(form.vatApplicable?1.15:1))}</span></div>
        </div>
      )}
      <div style={{display:"flex",gap:10}}>
        <Btn label="Save Draft" variant="secondary" onClick={()=>handleCreate("draft")} disabled={saving}/>
        <Btn label={saving?"Saving...":"Send Quote"} onClick={()=>handleCreate("sent")} disabled={saving}/>
      </div>
    </div>
  );

  return (
    <div style={{padding:"20px 16px 100px"}}>
      <h2 style={{fontFamily:"serif",fontSize:24,color:C.ink,margin:"0 0 16px"}}>Quotes</h2>
      <KPIRow items={[{label:"Accepted",value:fmt(accepted),color:C.green},{label:"Pending",value:fmt(pending),color:C.gold},{label:"Total",value:quotes.length,color:C.ink}]}/>
      {loading ? <div style={{textAlign:"center",color:C.inkMid,padding:40}}>Loading...</div> : quotes.length === 0 ? (
        <div style={{textAlign:"center",color:C.inkMid,padding:40}}>No quotes yet. Tap + to create one.</div>
      ) : quotes.map((q,i) => (
        <Card key={q.id||i}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
            <div>
              <div style={{fontWeight:700,color:C.ink,fontSize:15}}>{q.client_name||q.client}</div>
              <div style={{fontSize:12,color:C.inkMid,marginTop:2}}>{q.quote_number||`QT-${i+1}`} · {q.description||"—"}</div>
              {q.valid_until && <div style={{fontSize:11,color:C.inkDim,marginTop:2}}>Valid until {fmtD(q.valid_until)}</div>}
            </div>
            <div style={{textAlign:"right"}}>
              <div style={{fontWeight:700,color:C.accent,fontSize:16,marginBottom:4}}>{fmt(q.total_amount||q.amount||0)}</div>
              <Pill label={q.status||"draft"} color={statusColor(q.status||"draft")} bg={statusBg(q.status||"draft")}/>
            </div>
          </div>
        </Card>
      ))}
      <FAB onClick={()=>setShowForm(true)}/>
    </div>
  );
}

// ── LOGIN ─────────────────────────────────────────────────────────────────────
function Login({onLogin}) {
  const [form, setForm] = useState({email:"",password:""});
  const [busy, setBusy]  = useState(false);
  const [err,  setErr]   = useState("");

  const handleLogin = async () => {
    if (!form.email || !form.password) { setErr("Email and password are required."); return; }
    setBusy(true); setErr("");
    try {
      const body = new URLSearchParams({username: form.email, password: form.password});
      const res  = await fetch(`${BASE_URL}/auth/token`, {method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body});
      if (!res.ok) throw new Error("Invalid credentials");
      const d = await res.json();
      localStorage.setItem("zuzan_token", d.access_token);
      onLogin();
    } catch(e) { setErr(e.message||"Login failed"); }
    setBusy(false);
  };

  return (
    <div style={{minHeight:"100vh",background:C.bg,display:"flex",alignItems:"center",justifyContent:"center",padding:20}}>
      <div style={{width:"100%",maxWidth:380}}>
        <div style={{textAlign:"center",marginBottom:32}}>
          <div style={{fontSize:36,marginBottom:8}}>📒</div>
          <h1 style={{fontFamily:"serif",fontSize:28,color:C.ink,margin:0}}>ZuZan</h1>
          <p style={{color:C.inkMid,fontSize:14,marginTop:6}}>Smart bookkeeping for South Africa</p>
        </div>
        <div style={{background:C.surface,borderRadius:20,padding:28,boxShadow:"0 4px 24px #0000000a"}}>
          <Field label="Email">
            <input type="email" placeholder="your@email.com" value={form.email} onChange={e=>setForm(v=>({...v,email:e.target.value}))} style={inp} autoComplete="email"/>
          </Field>
          <Field label="Password">
            <input type="password" placeholder="••••••••" value={form.password} onChange={e=>setForm(v=>({...v,password:e.target.value}))} style={inp} onKeyDown={e=>e.key==="Enter"&&handleLogin()} autoComplete="current-password"/>
          </Field>
          {err && <div style={{color:C.red,fontSize:13,marginBottom:12,padding:"10px",background:C.redLt,borderRadius:8}}>{err}</div>}
          <Btn label={busy?"Signing in...":"Sign In"} onClick={handleLogin} disabled={busy}/>
        </div>
      </div>
    </div>
  );
}

// ── APP ROOT ──────────────────────────────────────────────────────────────────
export default function App() {
  const [tab,       setTab]       = useState("invoices");
  const [loggedIn,  setLoggedIn]  = useState(!!localStorage.getItem("zuzan_token"));

  if (!loggedIn) return <Login onLogin={()=>setLoggedIn(true)}/>;

  return (
    <div style={{background:C.bg,minHeight:"100vh",fontFamily:"-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",maxWidth:480,margin:"0 auto",position:"relative"}}>
      {/* Header */}
      <div style={{background:C.surface,borderBottom:`1px solid ${C.border}`,padding:"14px 16px",display:"flex",justifyContent:"space-between",alignItems:"center",position:"sticky",top:0,zIndex:100}}>
        <span style={{fontFamily:"serif",fontSize:20,fontWeight:700,color:C.ink}}>ZuZan</span>
        <button onClick={()=>{localStorage.removeItem("zuzan_token");setLoggedIn(false);}} style={{background:"none",border:`1px solid ${C.border}`,borderRadius:8,padding:"6px 12px",fontSize:12,color:C.inkMid,cursor:"pointer",fontFamily:"inherit"}}>Sign out</button>
      </div>

      {/* Content */}
      {tab === "invoices" && <Invoices/>}
      {tab === "expenses" && <Expenses/>}
      {tab === "quotes"   && <Quotes/>}

      <BottomNav tab={tab} setTab={setTab}/>
    </div>
  );
}
