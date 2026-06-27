// ZuZan App v2.1 — PO module: retry, draft, pay
import { useState, useEffect, useRef } from "react";
import * as XLSX from "xlsx";
import { BarChart, Bar, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell } from "recharts";

const C = {
  bg:"#FAF7F2", surface:"#FFFFFF", card:"#FDFCFA", border:"#E8E0D5",
  ink:"#1A1209", inkMid:"#6B5E4E", inkDim:"#B5A898",
  accent:"#C8401A", accentLt:"#C8401A12",
  green:"#2A6B3C", greenLt:"#2A6B3C12",
  gold:"#C4920A", goldLt:"#C4920A12",
  blue:"#1A3A6B", blueLt:"#1A3A6B12",
  red:"#C82A2A", redLt:"#C82A2A12",
  purple:"#6B2A8B", purpleLt:"#6B2A8B12",
};

const DEFAULT_DOC_TEMPLATE = {
  layout:       "classic",        // classic | modern | minimal | bold
  primaryColor: "#C8401A",
  fontFamily:   "Arial, sans-serif",
  invoiceTitle: "TAX INVOICE",
  quoteTitle:   "QUOTE / ESTIMATE",
  footerNote:   "",
  tableStyle:   "shaded",         // shaded | lines | clean
};

const BASE_URL = "https://zuzan-backend.onrender.com";
const fmt = n => `R${Number(n).toLocaleString("en-ZA",{minimumFractionDigits:2})}`;
const fmtDate = d => new Date(d).toLocaleDateString("en-ZA",{day:"2-digit",month:"short",year:"numeric"});

// ── API HELPER ────────────────────────────────────────────────────────────────
async function api(path, options = {}) {
  const token = localStorage.getItem("zuzan_token");
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token && !token.startsWith("demo_token") ? {"Authorization": `Bearer ${token}`} : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// ── LIVE DATA HOOK ────────────────────────────────────────────────────────────
function useLiveData() {
  const [dashboard, setDashboard] = useState(null);
  const [expenses,  setExpenses]  = useState(null);
  const [invoices,  setInvoices]  = useState(null);
  const [employees, setEmployees] = useState(null);
  const [trend,     setTrend]     = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [connected, setConnected] = useState(false);

  const loadAll = async () => {
    const token = localStorage.getItem("zuzan_token");
    if (!token || token.startsWith("demo_")) {
      setLoading(false);
      setConnected(false);
      return;
    }
    try {
      const [dash, exp, inv, emp, tr] = await Promise.all([
        api("/reports/dashboard").catch(() => null),
        api("/expenses/").catch(() => null),
        api("/invoices/").catch(() => null),
        api("/employees/").catch(() => null),
        api("/reports/monthly-trend").catch(() => null),
      ]);
      if (dash) { setDashboard(dash); setConnected(true); }
      if (exp)  setExpenses(exp);
      if (inv)  setInvoices(inv);
      if (emp)  setEmployees(emp);
      if (tr)   setTrend(tr);
    } catch(e) {
      console.warn("Live data error:", e.message);
      setConnected(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAll(); }, []);

  return { dashboard, expenses, invoices, employees, trend, loading, connected, reload: loadAll };
}

const PLANS = [
  { id:"starter",      name:"Starter",      monthly:399,  annual:3990,  usdMonthly:22, users:2,  invoices:20,         color:C.blue,   icon:"🌱", features:["2 users","20 invoices/month","Invoicing & quotes","Expense tracking","Payroll (PAYE/UIF/SDL)","Bank feed (all SA banks)","Basic P&L report","Email support"] },
  { id:"professional", name:"Professional", monthly:899,  annual:8990,  usdMonthly:49, users:5,  invoices:50,         color:C.accent, icon:"⚡", popular:true, features:["5 users","50 invoices/month","Everything in Starter","Double-entry general ledger","Trial balance & journal viewer","Balance sheet reconciliation","Advanced reports","Priority support"] },
  { id:"business",     name:"Business",     monthly:1499, annual:14990, usdMonthly:82, users:20, invoices:"Unlimited", color:C.green,  icon:"🏢", features:["20 users","Unlimited invoices","Everything in Professional","Budgeting vs actuals","Cash flow forecast","Department budgets","API access","Dedicated account manager"] },
];

const MOCK_INVOICES = [
  {id:"INV-001",client:"Example Client (Pty) Ltd",amount:10000,date:"2026-05-01",due:"2026-06-01",status:"sent",desc:"Add your first invoice using the + New Invoice button"},
];

const MOCK_EXPENSES = [
  {id:"EXP-001",vendor:"Example Supplier",amount:1150,date:"2026-05-01",category:"6360 - Bank Charges",desc:"Add your first expense using the + Add Expense button"},
];

const MOCK_EMPLOYEES = [
  {id:"EMP-001",name:"Example Employee",position:"Position",salary:25000,dept:"General"},
];

const REVENUE_DATA = [
  {month:"Jan",revenue:0,expenses:0,profit:0},
  {month:"Feb",revenue:0,expenses:0,profit:0},
  {month:"Mar",revenue:0,expenses:0,profit:0},
  {month:"Apr",revenue:0,expenses:0,profit:0},
  {month:"May",revenue:0,expenses:0,profit:0},
  {month:"Jun",revenue:0,expenses:0,profit:0},
];

const EXPENSE_PIE = [
  {name:"No data yet",value:1,color:C.inkDim},
];

const ALL_CATS = ["Revenue","Interest Income","Cost of Sales","Utilities","Telecoms","Office","Banking","Insurance","Tax","Equipment","Travel","Salaries","Rent","Marketing","Professional Fees","Other"];

const TAX_YEARS = {
  "2024/2025": {
    brackets: [{min:0,max:237100,rate:0.18,base:0},{min:237101,max:370500,rate:0.26,base:42678},{min:370501,max:512800,rate:0.31,base:77362},{min:512801,max:673000,rate:0.36,base:121475},{min:673001,max:857900,rate:0.39,base:179147},{min:857901,max:1817000,rate:0.41,base:251258},{min:1817001,max:9999999,rate:0.45,base:644489}],
    rebate: 17235, uifCeil: 17712,
  },
  "2025/2026": {
    brackets: [{min:0,max:237100,rate:0.18,base:0},{min:237101,max:370500,rate:0.26,base:42678},{min:370501,max:512800,rate:0.31,base:77362},{min:512801,max:673000,rate:0.36,base:121475},{min:673001,max:857900,rate:0.39,base:179147},{min:857901,max:1817000,rate:0.41,base:251258},{min:1817001,max:9999999,rate:0.45,base:644489}],
    rebate: 17235, uifCeil: 17712,
  },
  "2026/2027": {
    brackets: [{min:0,max:245100,rate:0.18,base:0},{min:245101,max:383100,rate:0.26,base:44118},{min:383101,max:530200,rate:0.31,base:79998},{min:530201,max:695800,rate:0.36,base:125599},{min:695801,max:887000,rate:0.39,base:185215},{min:887001,max:1878600,rate:0.41,base:259783},{min:1878601,max:9999999,rate:0.45,base:666339}],
    rebate: 17820, uifCeil: 17712,
  },
};
const CURRENT_TAX_YEAR = "2026/2027";

function calcPAYE(annual, taxYear) {
  const yr = TAX_YEARS[taxYear || CURRENT_TAX_YEAR] || TAX_YEARS[CURRENT_TAX_YEAR];
  const b = yr.brackets.find(b => annual >= b.min && annual <= b.max);
  if (!b) return 0;
  return Math.max(0, b.base + (annual - b.min) * b.rate - yr.rebate);
}

// BCEA overtime constants (mirrors backend payroll.py)
const BCEA_WEEKLY_HOURS    = 45;
const BCEA_WEEKS_PER_MONTH = 52 / 12;  // 4.3333
const BCEA_OT_WEEKDAY      = 1.5;      // s10 weekday/Saturday
const BCEA_OT_SUNDAY       = 2.0;      // s16
const BCEA_OT_PH           = 2.0;      // s18 public holiday

function bceaHourlyRate(grossMonthly, explicitHourlyRate) {
  if (explicitHourlyRate) return explicitHourlyRate;
  return grossMonthly / (BCEA_WEEKLY_HOURS * BCEA_WEEKS_PER_MONTH);
}

function calcOvertime(grossMonthly, otHours=0, sunHours=0, phHours=0, explicitHourlyRate=null) {
  const hr = bceaHourlyRate(grossMonthly, explicitHourlyRate);
  const otAmt  = Math.round(otHours  * hr * BCEA_OT_WEEKDAY * 100) / 100;
  const sunAmt = Math.round(sunHours * hr * BCEA_OT_SUNDAY  * 100) / 100;
  const phAmt  = Math.round(phHours  * hr * BCEA_OT_PH      * 100) / 100;
  return { hourlyRate:hr, otAmount:otAmt, sunAmount:sunAmt, phAmount:phAmt,
           total: Math.round((otAmt + sunAmt + phAmt)*100)/100 };
}

function calcPayroll(salary, taxYear, otHours=0, sunHours=0, phHours=0, explicitHourlyRate=null) {
  const yr = TAX_YEARS[taxYear || CURRENT_TAX_YEAR] || TAX_YEARS[CURRENT_TAX_YEAR];
  const ot = calcOvertime(salary, otHours, sunHours, phHours, explicitHourlyRate);
  const taxableGross = salary + ot.total;
  const paye = calcPAYE(taxableGross*12, taxYear)/12;
  // UIF on base salary only (SARS excludes overtime from UIF)
  const uifBase = Math.min(salary, yr.uifCeil);
  const uifEmp = uifBase*0.01, uifEmpr = uifBase*0.01, sdl = taxableGross*0.01;
  return {
    gross:salary,
    overtime: ot,
    taxableGross: Math.round(taxableGross),
    paye:Math.round(paye),
    uifEmployee:Math.round(uifEmp),
    uifEmployer:Math.round(uifEmpr),
    sdl:Math.round(sdl),
    netPay:Math.round(taxableGross-paye-uifEmp),
    totalCost:Math.round(taxableGross+uifEmpr+sdl)
  };
}

const Badge = ({label,color,bg}) => (
  <span style={{fontSize:10,fontWeight:700,color,background:bg,padding:"3px 9px",borderRadius:20,letterSpacing:0.5,textTransform:"uppercase"}}>{label}</span>
);

const StatusBadge = ({status}) => {
  const m={
    paid:   [C.green,  C.greenLt,  "Paid"],
    sent:   [C.blue,   C.blueLt,   "Sent"],
    pending:[C.gold,   C.goldLt,   "Pending"],
    draft:  [C.inkMid, C.border,   "Draft"],
    overdue:[C.red,    C.redLt,    "Overdue"],
  };
  const [c,bg,l]=m[status]||m.pending;
  return <Badge label={l} color={c} bg={bg}/>;
};

const KPI = ({label,value,sub,color=C.ink,icon,onClick,active=false}) => (
  <div onClick={onClick} style={{background:C.surface,border:active?`2px solid ${color}`:`1px solid ${C.border}`,borderRadius:14,padding:active?"15px 17px":"16px 18px",flex:1,cursor:onClick?"pointer":"default",transition:"box-shadow 0.15s, border 0.15s",boxShadow:active?"0 0 0 3px "+color+"18":"none"}}
    onMouseEnter={e=>{if(onClick)e.currentTarget.style.boxShadow=active?"0 0 0 3px "+color+"18":"0 4px 16px rgba(0,0,0,0.10)";}}
    onMouseLeave={e=>{e.currentTarget.style.boxShadow=active?"0 0 0 3px "+color+"18":"none";}}>
    <div style={{display:"flex",justifyContent:"space-between",marginBottom:8}}>
      <span style={{fontSize:10,color:C.inkMid,letterSpacing:0.5,textTransform:"uppercase",fontWeight:600}}>{label}</span>
      <span style={{fontSize:16}}>{icon}</span>
    </div>
    <div style={{fontSize:22,fontWeight:800,color,fontFamily:"'Playfair Display',serif",marginBottom:3}}>{value}</div>
    {sub && <div style={{fontSize:11,color:C.inkDim}}>{sub}</div>}
    {onClick && <div style={{fontSize:10,color:C.inkMid,marginTop:4,opacity:0.6}}>Tap to view breakdown ›</div>}
  </div>
);

const Tooltip2 = ({active,payload,label}) => {
  if (!active||!payload?.length) return null;
  return (
    <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 14px",fontSize:12}}>
      <div style={{color:C.inkMid,marginBottom:6,fontWeight:600}}>{label}</div>
      {payload.map((p,i)=><div key={i} style={{color:p.color}}>{p.name}: {fmt(p.value)}</div>)}
    </div>
  );
};

const SectionHeader = ({title,sub,action,onAction}) => (
  <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-end",marginBottom:20}}>
    <div>
      <h2 style={{fontFamily:"'Playfair Display',serif",fontSize:26,color:C.ink,margin:0}}>{title}</h2>
      {sub&&<p style={{fontSize:12,color:C.inkMid,marginTop:3}}>{sub}</p>}
    </div>
    {action&&<button onClick={onAction} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>{action}</button>}
  </div>
);
// ── COA DATA ──────────────────────────────────────────────────────────────────
const COA_GROUPS = ["Assets","Liabilities","Equity","Income","Cost of Sales","Expenses"];
const EXPENSE_COA_GROUPS = ["Cost of Sales","Expenses"];

const GROUP_COLORS = {
  "Assets":        {color:C.blue,  bg:C.blueLt,  icon:"🏛️"},
  "Liabilities":   {color:C.red,   bg:C.redLt,   icon:"📋"},
  "Equity":        {color:C.purple,bg:C.purpleLt, icon:"⚖️"},
  "Income":        {color:C.green, bg:C.greenLt,  icon:"💰"},
  "Cost of Sales": {color:C.gold,  bg:C.goldLt,   icon:"🏭"},
  "Expenses":      {color:C.accent,bg:C.accentLt, icon:"📤"},
};

const DEFAULT_COA = [
  {code:"1000",name:"ASSETS",type:"Header",group:"Assets",normal:"Debit",description:"All assets of the business"},
  {code:"1110",name:"Cash and Cash Equivalents",type:"Detail",group:"Assets",normal:"Debit",description:"Bank accounts and petty cash"},
  {code:"1111",name:"FNB Business Account",type:"Detail",group:"Assets",normal:"Debit",description:"Primary FNB business cheque account"},
  {code:"1112",name:"ABSA Business Account",type:"Detail",group:"Assets",normal:"Debit",description:"ABSA business account"},
  {code:"1113",name:"Petty Cash",type:"Detail",group:"Assets",normal:"Debit",description:"Cash on hand for small expenses"},
  {code:"1120",name:"Trade Receivables (Debtors)",type:"Detail",group:"Assets",normal:"Debit",description:"Amounts owed by customers"},
  {code:"1130",name:"Inventory",type:"Detail",group:"Assets",normal:"Debit",description:"Stock on hand"},
  {code:"1140",name:"Prepaid Expenses",type:"Detail",group:"Assets",normal:"Debit",description:"Expenses paid in advance"},
  {code:"1150",name:"VAT Input",type:"Detail",group:"Assets",normal:"Debit",description:"VAT claimable from SARS"},
  {code:"1160",name:"SARS Income Tax Receivable",type:"Detail",group:"Assets",normal:"Debit",description:"Income tax refund due from SARS"},
  {code:"1210",name:"Property Plant and Equipment",type:"Header",group:"Assets",normal:"Debit",description:"Tangible fixed assets"},
  {code:"1211",name:"Land and Buildings",type:"Detail",group:"Assets",normal:"Debit",description:"Owned property"},
  {code:"1212",name:"Vehicles",type:"Detail",group:"Assets",normal:"Debit",description:"Motor vehicles"},
  {code:"1213",name:"Computer Equipment",type:"Detail",group:"Assets",normal:"Debit",description:"Computers and laptops"},
  {code:"1214",name:"Office Furniture and Equipment",type:"Detail",group:"Assets",normal:"Debit",description:"Desks, chairs, office equipment"},
  {code:"1221",name:"Accum Dep - Vehicles",type:"Detail",group:"Assets",normal:"Credit",description:"Depreciation on vehicles"},
  {code:"1222",name:"Accum Dep - Computer Equipment",type:"Detail",group:"Assets",normal:"Credit",description:"Depreciation on computers"},
  {code:"2000",name:"LIABILITIES",type:"Header",group:"Liabilities",normal:"Credit",description:"All liabilities of the business"},
  {code:"2110",name:"Trade Payables (Creditors)",type:"Detail",group:"Liabilities",normal:"Credit",description:"Amounts owed to suppliers"},
  {code:"2121",name:"PAYE Payable",type:"Detail",group:"Liabilities",normal:"Credit",description:"Employee tax withheld - due to SARS by 7th"},
  {code:"2122",name:"UIF Payable",type:"Detail",group:"Liabilities",normal:"Credit",description:"UIF contributions due to SARS"},
  {code:"2123",name:"SDL Payable",type:"Detail",group:"Liabilities",normal:"Credit",description:"Skills Development Levy due to SARS"},
  {code:"2124",name:"VAT Output",type:"Detail",group:"Liabilities",normal:"Credit",description:"VAT collected on sales - due to SARS"},
  {code:"2125",name:"VAT Control",type:"Detail",group:"Liabilities",normal:"Credit",description:"Net VAT position"},
  {code:"2126",name:"Income Tax Payable",type:"Detail",group:"Liabilities",normal:"Credit",description:"Corporate income tax due to SARS"},
  {code:"2127",name:"Provisional Tax Payable",type:"Detail",group:"Liabilities",normal:"Credit",description:"Provisional tax IRP6 submissions"},
  {code:"2130",name:"Accrued Salaries",type:"Detail",group:"Liabilities",normal:"Credit",description:"Salaries earned but not yet paid"},
  {code:"2140",name:"Deferred Revenue",type:"Detail",group:"Liabilities",normal:"Credit",description:"Income received in advance"},
  {code:"2150",name:"Short-term Loan",type:"Detail",group:"Liabilities",normal:"Credit",description:"Bank overdraft or short-term borrowings"},
  {code:"2160",name:"Directors Loan Account",type:"Detail",group:"Liabilities",normal:"Credit",description:"Amounts owed to directors"},
  {code:"2210",name:"Long-term Loan",type:"Detail",group:"Liabilities",normal:"Credit",description:"Bank loans repayable after 12 months"},
  {code:"2220",name:"Mortgage Bond",type:"Detail",group:"Liabilities",normal:"Credit",description:"Property mortgage"},
  {code:"3000",name:"EQUITY",type:"Header",group:"Equity",normal:"Credit",description:"Owners interest in the business"},
  {code:"3110",name:"Ordinary Share Capital",type:"Detail",group:"Equity",normal:"Credit",description:"Ordinary shares issued"},
  {code:"3200",name:"Retained Income",type:"Detail",group:"Equity",normal:"Credit",description:"Accumulated profits not distributed"},
  {code:"3300",name:"Dividends Paid",type:"Detail",group:"Equity",normal:"Debit",description:"Dividends declared and paid to shareholders"},
  {code:"3400",name:"Drawings",type:"Detail",group:"Equity",normal:"Debit",description:"Amounts withdrawn by owners"},
  {code:"4000",name:"INCOME",type:"Header",group:"Income",normal:"Credit",description:"All revenue earned by the business"},
  {code:"4110",name:"Sales - Products",type:"Detail",group:"Income",normal:"Credit",description:"Revenue from sale of goods"},
  {code:"4120",name:"Sales - Services",type:"Detail",group:"Income",normal:"Credit",description:"Revenue from services rendered"},
  {code:"4130",name:"Consulting Fees",type:"Detail",group:"Income",normal:"Credit",description:"Professional consulting income"},
  {code:"4140",name:"Commission Income",type:"Detail",group:"Income",normal:"Credit",description:"Commission earned"},
  {code:"4150",name:"Rental Income",type:"Detail",group:"Income",normal:"Credit",description:"Income from property rental"},
  {code:"4160",name:"Subscription Income",type:"Detail",group:"Income",normal:"Credit",description:"Recurring subscription revenue"},
  {code:"4210",name:"Interest Income",type:"Detail",group:"Income",normal:"Credit",description:"Interest earned on bank accounts"},
  {code:"4220",name:"Discount Received",type:"Detail",group:"Income",normal:"Credit",description:"Discounts received from suppliers"},
  {code:"4230",name:"Government Grants",type:"Detail",group:"Income",normal:"Credit",description:"SEDA, SEFA or government grants"},
  {code:"5000",name:"COST OF SALES",type:"Header",group:"Cost of Sales",normal:"Debit",description:"Direct costs of generating revenue"},
  {code:"5110",name:"Purchases",type:"Detail",group:"Cost of Sales",normal:"Debit",description:"Goods purchased for resale"},
  {code:"5120",name:"Freight and Delivery",type:"Detail",group:"Cost of Sales",normal:"Debit",description:"Delivery costs for goods purchased"},
  {code:"5130",name:"Import Duties",type:"Detail",group:"Cost of Sales",normal:"Debit",description:"Customs and import duties"},
  {code:"5140",name:"Direct Labour",type:"Detail",group:"Cost of Sales",normal:"Debit",description:"Labour directly used in production"},
  {code:"5150",name:"Direct Materials",type:"Detail",group:"Cost of Sales",normal:"Debit",description:"Raw materials used in production"},
  {code:"6000",name:"OPERATING EXPENSES",type:"Header",group:"Expenses",normal:"Debit",description:"All operating expenses"},
  {code:"6110",name:"Salaries and Wages",type:"Detail",group:"Expenses",normal:"Debit",description:"Gross salaries paid to employees"},
  {code:"6120",name:"Employer UIF Contributions",type:"Detail",group:"Expenses",normal:"Debit",description:"Employer portion of UIF 1 percent of salary"},
  {code:"6130",name:"SDL Skills Development Levy",type:"Detail",group:"Expenses",normal:"Debit",description:"1 percent of payroll skills levy"},
  {code:"6140",name:"Medical Aid Contributions",type:"Detail",group:"Expenses",normal:"Debit",description:"Employer medical aid contributions"},
  {code:"6150",name:"Pension and Provident Fund",type:"Detail",group:"Expenses",normal:"Debit",description:"Employer retirement fund contributions"},
  {code:"6160",name:"Leave Pay Expense",type:"Detail",group:"Expenses",normal:"Debit",description:"Annual leave provision"},
  {code:"6210",name:"Rent - Office",type:"Detail",group:"Expenses",normal:"Debit",description:"Monthly office rental"},
  {code:"6220",name:"Electricity and Water",type:"Detail",group:"Expenses",normal:"Debit",description:"Eskom and municipal utilities"},
  {code:"6230",name:"Rates and Taxes",type:"Detail",group:"Expenses",normal:"Debit",description:"Municipal rates on owned property"},
  {code:"6240",name:"Cleaning and Hygiene",type:"Detail",group:"Expenses",normal:"Debit",description:"Office cleaning services"},
  {code:"6250",name:"Security",type:"Detail",group:"Expenses",normal:"Debit",description:"Security services and systems"},
  {code:"6260",name:"Repairs and Maintenance",type:"Detail",group:"Expenses",normal:"Debit",description:"Office and equipment maintenance"},
  {code:"6310",name:"Stationery and Office Supplies",type:"Detail",group:"Expenses",normal:"Debit",description:"Paper, pens, printing supplies"},
  {code:"6320",name:"Printing and Photocopying",type:"Detail",group:"Expenses",normal:"Debit",description:"Printing costs"},
  {code:"6340",name:"Subscriptions",type:"Detail",group:"Expenses",normal:"Debit",description:"Software and service subscriptions"},
  {code:"6350",name:"Computer Software",type:"Detail",group:"Expenses",normal:"Debit",description:"Software licences and SaaS"},
  {code:"6360",name:"Bank Charges",type:"Detail",group:"Expenses",normal:"Debit",description:"Monthly bank service fees"},
  {code:"6370",name:"Sundry Expenses",type:"Detail",group:"Expenses",normal:"Debit",description:"Miscellaneous small expenses"},
  {code:"6410",name:"Telephone Landline",type:"Detail",group:"Expenses",normal:"Debit",description:"Telkom and landline costs"},
  {code:"6420",name:"Cellphone Expenses",type:"Detail",group:"Expenses",normal:"Debit",description:"Mobile phone costs"},
  {code:"6430",name:"Internet Fibre",type:"Detail",group:"Expenses",normal:"Debit",description:"Fibre and internet connectivity"},
  {code:"6510",name:"Fuel and Oil",type:"Detail",group:"Expenses",normal:"Debit",description:"Petrol, diesel, oil"},
  {code:"6520",name:"Vehicle Maintenance",type:"Detail",group:"Expenses",normal:"Debit",description:"Servicing and repairs"},
  {code:"6530",name:"Vehicle Insurance",type:"Detail",group:"Expenses",normal:"Debit",description:"Motor vehicle insurance"},
  {code:"6540",name:"Toll Fees",type:"Detail",group:"Expenses",normal:"Debit",description:"E-tolls and toll gates"},
  {code:"6560",name:"Air Travel",type:"Detail",group:"Expenses",normal:"Debit",description:"Flights for business"},
  {code:"6570",name:"Accommodation",type:"Detail",group:"Expenses",normal:"Debit",description:"Hotels and lodging"},
  {code:"6610",name:"Advertising",type:"Detail",group:"Expenses",normal:"Debit",description:"Print and media advertising"},
  {code:"6620",name:"Digital Marketing",type:"Detail",group:"Expenses",normal:"Debit",description:"Google Ads, Facebook, Instagram"},
  {code:"6630",name:"Website Costs",type:"Detail",group:"Expenses",normal:"Debit",description:"Hosting, domain, web development"},
  {code:"6640",name:"Branding and Design",type:"Detail",group:"Expenses",normal:"Debit",description:"Logo, branding, graphic design"},
  {code:"6660",name:"Entertainment Clients",type:"Detail",group:"Expenses",normal:"Debit",description:"Client entertainment"},
  {code:"6710",name:"Accounting and Audit Fees",type:"Detail",group:"Expenses",normal:"Debit",description:"Accountant, bookkeeper, auditor fees"},
  {code:"6720",name:"Legal Fees",type:"Detail",group:"Expenses",normal:"Debit",description:"Attorney and legal costs"},
  {code:"6730",name:"Consulting Fees Expense",type:"Detail",group:"Expenses",normal:"Debit",description:"Business consultants"},
  {code:"6740",name:"IT Support",type:"Detail",group:"Expenses",normal:"Debit",description:"Technical support and IT services"},
  {code:"6750",name:"CIPC Annual Return",type:"Detail",group:"Expenses",normal:"Debit",description:"Annual return filing fee"},
  {code:"6810",name:"Business Insurance",type:"Detail",group:"Expenses",normal:"Debit",description:"General business insurance"},
  {code:"6820",name:"Professional Indemnity",type:"Detail",group:"Expenses",normal:"Debit",description:"PI insurance"},
  {code:"6910",name:"Income Tax Expense",type:"Detail",group:"Expenses",normal:"Debit",description:"Corporate income tax 27 percent of taxable income"},
  {code:"6930",name:"Penalties and Interest SARS",type:"Detail",group:"Expenses",normal:"Debit",description:"SARS penalties and interest charged"},
  {code:"7100",name:"Depreciation",type:"Detail",group:"Expenses",normal:"Debit",description:"Depreciation on fixed assets"},
  {code:"7200",name:"Interest Expense",type:"Detail",group:"Expenses",normal:"Debit",description:"Interest paid on loans and overdrafts"},
  {code:"7300",name:"Bad Debts Written Off",type:"Detail",group:"Expenses",normal:"Debit",description:"Uncollectable debts written off"},
  {code:"7600",name:"Donations",type:"Detail",group:"Expenses",normal:"Debit",description:"Charitable donations Section 18A"},
];

const BANK_FORMATS = {
  fnb:          {name:"FNB",           logo:"🟢",skipRows:4,dateCol:0,descCol:2,amtCol:4},
  absa:         {name:"ABSA",          logo:"🔴",skipRows:1,dateCol:0,descCol:1,amtCol:3},
  standardbank: {name:"Standard Bank", logo:"🔵",skipRows:1,dateCol:0,descCol:1,amtCol:2},
  nedbank:      {name:"Nedbank",       logo:"🟩",skipRows:1,dateCol:0,descCol:1,amtCol:2},
  capitec:      {name:"Capitec",       logo:"🟦",skipRows:1,dateCol:0,descCol:2,amtCol:3},
  discovery:    {name:"Discovery Bank",logo:"🟣",skipRows:1,dateCol:0,descCol:1,amtCol:2},
  investec:     {name:"Investec",      logo:"🔷",skipRows:1,dateCol:0,descCol:1,amtCol:3},
  tymebank:     {name:"TymeBank",      logo:"🩵",skipRows:1,dateCol:0,descCol:1,amtCol:2},
};

function autoCategory(desc) {
  const d = desc.toLowerCase();
  if (d.includes("interest")) return "Interest Income";
  if (d.includes("eskom") || d.includes("electric") || d.includes("water")) return "Utilities";
  if (d.includes("telkom") || d.includes("vodacom") || d.includes("mtn") || d.includes("fibre")) return "Telecoms";
  if (d.includes("sars") || d.includes("tax") || d.includes("vat")) return "Tax";
  if (d.includes("salary") || d.includes("payroll") || d.includes("wages")) return "Salaries";
  if (d.includes("rent") || d.includes("lease")) return "Rent";
  if (d.includes("bank") || d.includes("charge") || d.includes("fee")) return "Banking";
  if (d.includes("insurance") || d.includes("assurance")) return "Insurance";
  if (d.includes("fuel") || d.includes("petrol") || d.includes("shell") || d.includes("engen")) return "Travel";
  if (d.includes("office") || d.includes("stationery")) return "Office";
  if (d.includes("advertis") || d.includes("google") || d.includes("facebook")) return "Marketing";
  if (d.includes("attorney") || d.includes("accountant") || d.includes("audit")) return "Professional Fees";
  return "Other";
}

function parseCSVLine(line) {
  const result = [];
  let current = "";
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    if (line[i] === '"') inQ = !inQ;
    else if (line[i] === ',' && !inQ) { result.push(current.trim().replace(/^"|"$/g,"")); current = ""; }
    else current += line[i];
  }
  result.push(current.trim().replace(/^"|"$/g,""));
  return result;
}

function parseAmt(str) {
  if (!str) return 0;
  return parseFloat(str.replace(/[R,\s]/g,"").replace("(","-").replace(")","")) || 0;
}

function parseDt(str) {
  if (!str) return new Date().toISOString().slice(0,10);
  const m1 = str.trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (m1) return `${m1[3]}-${m1[2]}-${m1[1]}`;
  const m2 = str.trim().match(/^(\d{4})\/(\d{2})\/(\d{2})$/);
  if (m2) return `${m2[1]}-${m2[2]}-${m2[3]}`;
  return new Date().toISOString().slice(0,10);
}
// ── DASHBOARD ─────────────────────────────────────────────────────────────────
function CIPCBanner({cipc, poDupWarning}) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const banners = [];
  if (cipc && cipc.warning) {
    banners.push({
      msg:   cipc.message,
      color: cipc.overdue ? "#C82A2A" : "#C4920A",
      bg:    cipc.overdue ? "#FFF0F0" : "#FFFBF0",
      link:  "https://www.cipc.co.za",
      label: "File at CIPC ↗",
    });
  }
  if (poDupWarning) {
    banners.push({
      msg:   poDupWarning,
      color: "#C8401A",
      bg:    "#FFF5F0",
      link:  null,
      label: null,
    });
  }
  if (banners.length === 0) return null;

  return (
    <div style={{marginBottom:16}}>
      {banners.map((b,i) => (
        <div key={i} style={{
          display:"flex", alignItems:"center", justifyContent:"space-between",
          background:b.bg, border:`1px solid ${b.color}30`,
          borderLeft:`4px solid ${b.color}`, borderRadius:10,
          padding:"10px 16px", marginBottom:8, gap:12,
        }}>
          <span style={{fontSize:13, color:b.color, fontWeight:600, flex:1}}>{b.msg}</span>
          <div style={{display:"flex",gap:8,flexShrink:0}}>
            {b.link && (
              <a href={b.link} target="_blank" rel="noopener noreferrer"
                style={{fontSize:12,fontWeight:700,color:b.color,textDecoration:"none",
                  padding:"4px 12px",border:`1px solid ${b.color}`,borderRadius:6}}>
                {b.label}
              </a>
            )}
            <button onClick={()=>setDismissed(true)}
              style={{background:"none",border:"none",color:b.color,cursor:"pointer",
                fontSize:16,lineHeight:1,padding:"2px 4px",opacity:0.6}}>✕</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function Dashboard({live = {}}) {
  const d = live.dashboard;
  const revenueData = live.trend || REVENUE_DATA;
  const isLive = live.connected;
  const [drill, setDrill] = useState(null); // {type, title, rows, cols, total, color}
  const [drillLoading, setDrillLoading] = useState(false);

  // Use total_amount (VAT-inclusive) for ZAR — matches backend _to_zar exactly
  const toZarD = i => (i.currency && i.currency !== "ZAR")
    ? (i.paid_amount_zar || (i.total_amount||i.amount||0)*(i.exchange_rate||1))
    : (i.total_amount||i.amount||0);

  const openDrill = async (type) => {
    setDrillLoading(true);
    setDrill({type, rows:[], cols:[], title:"", total:0, color:C.ink});
    try {
      if (type === "revenue") {
        const invs = await api("/invoices");
        // All-time paid — matches dashboard revenue KPI exactly
        const rows = invs.filter(i => i.status==="paid")
          .sort((a,b) => new Date(b.paid_date||b.created_at||0)-new Date(a.paid_date||a.created_at||0));
        setDrill({type, title:"Revenue — All Paid Invoices", color:C.green,
          total: rows.reduce((s,i)=>s+toZarD(i),0),
          cols:["Invoice","Client","Currency","Amount (ZAR)","Paid Date"],
          rows: rows.map(i=>[i.invoice_number||i.id, i.client_name||i.client, i.currency||"ZAR",
            fmt(toZarD(i)), i.paid_date ? new Date(i.paid_date).toLocaleDateString("en-ZA") : "—"])});
      } else if (type === "expenses") {
        const [exps, deprSchedule, allPOs] = await Promise.all([
          api("/expenses"),
          api("/fixed-assets/schedule").catch(()=>[]),
          api("/purchase-orders/").catch(()=>[]),
        ]);
        // Expense rows — VAT-exclusive
        const expRows = exps.map(e=>({
          _date: new Date(e.expense_date||e.created_at||0),
          cols: [e.description||"—", e.category||"—", fmt((e.amount||0)-(e.vat_amount||0)),
            e.expense_date ? new Date(e.expense_date).toLocaleDateString("en-ZA") : "—"],
          amount: (e.amount||0)-(e.vat_amount||0),
        }));
        // Depreciation rows — one row per DepreciationEntry
        const deprRows = (deprSchedule||[]).map(d=>({
          _date: new Date(d.period+"-01"),
          cols: [`${d.asset_name} — Depreciation`, "Depreciation (IAS 16)", fmt(d.amount||0),
            d.period ? new Date(d.period+"-01").toLocaleDateString("en-ZA",{year:"numeric",month:"short"}) : "—"],
          amount: d.amount||0,
        }));
        // PO COGS rows — received/partial/paid purchase orders (ex-VAT, matching backend)
        const poRows = (allPOs||[]).filter(po=>["received","partial","paid"].includes(po.status)).map(po=>({
          _date: new Date(po.received_date||po.created_at||0),
          cols: [po.description||po.po_number||"Purchase Order", "Cost of Sales (POs)",
            fmt((po.total_amount||0)-(po.vat_amount||0)),
            po.received_date ? new Date(po.received_date).toLocaleDateString("en-ZA") : "—"],
          amount: (po.total_amount||0)-(po.vat_amount||0),
        }));
        const allRows = [...expRows, ...deprRows, ...poRows].sort((a,b)=>b._date-a._date);
        setDrill({type, title:"Expenses — All Time (excl. VAT, incl. Depreciation & PO COGS)", color:C.red,
          total: allRows.reduce((s,r)=>s+r.amount,0),
          cols:["Description","Category","Amount (excl. VAT)","Date"],
          rows: allRows.map(r=>r.cols)});
      } else if (type === "outstanding") {
        const invs = await api("/invoices");
        const rows = invs.filter(i => ["pending","sent","overdue"].includes(i.status))
          .sort((a,b) => new Date(a.due_date||0)-new Date(b.due_date||0));
        const today = new Date();
        setDrill({type, title:"Outstanding — Pending & Overdue", color:C.gold,
          total: rows.reduce((s,i)=>s+toZarD(i),0),
          cols:["Invoice","Client","Amount (ZAR)","Due Date","Days Overdue"],
          rows: rows.map(i=>{
            const due = i.due_date ? new Date(i.due_date) : null;
            const overdue = due ? Math.max(0, Math.floor((today-due)/(1000*60*60*24))) : 0;
            return [i.invoice_number||i.id, i.client_name||i.client, fmt(toZarD(i)),
              due ? due.toLocaleDateString("en-ZA") : "—",
              overdue > 0 ? `${overdue}d` : "Current"];
          })});
      } else if (type === "payroll") {
        const emps = await api("/employees");
        const rows = emps.filter(e=>e.is_active!==false);
        setDrill({type, title:"Payroll — Active Employees", color:C.blue,
          total: rows.reduce((s,e)=>s+calcPayroll(e.gross_salary).totalCost,0),
          cols:["Employee","Position","Gross Salary","Net Pay","Employer Cost"],
          rows: rows.map(e=>{
            const p = calcPayroll(e.gross_salary);
            return [e.name, e.position||"—", fmt(e.gross_salary), fmt(p.netPay), fmt(p.totalCost)];
          })});
      } else if (type === "vat") {
        const invs = await api("/invoices");
        const exps = await api("/expenses");
        const outputVat = invs.reduce((s,i)=>s+(i.vat_amount||0),0);
        const inputVat  = exps.reduce((s,e)=>s+(e.vat_amount||0),0);
        const netVat    = outputVat - inputVat;
        setDrill({type, title:"VAT Position — All Time", color: netVat>=0?C.red:C.green,
          total: netVat,
          cols:["Description","Amount"],
          rows:[
            ["Output VAT (charged on invoices)", fmt(outputVat)],
            ["Input VAT (claimable on expenses)", `- ${fmt(inputVat)}`],
            [netVat>=0?"Net VAT payable to SARS":"Net VAT refund due from SARS", fmt(Math.abs(netVat))],
          ]});
      } else if (type === "profit") {
        const [invs, exps, allPOs, deprSchedule, emps] = await Promise.all([
          api("/invoices"),
          api("/expenses"),
          api("/purchase-orders/").catch(()=>[]),
          api("/fixed-assets/schedule").catch(()=>[]),
          api("/employees").catch(()=>[]),
        ]);
        const paidInvs = invs.filter(i=>i.status==="paid");
        const rev  = paidInvs.reduce((s,i)=>s+toZarD(i),0);
        const exp  = exps.reduce((s,e)=>s+((e.amount||0)-(e.vat_amount||0)),0);
        const poCogs = (allPOs||[])
          .filter(po=>["received","partial","paid"].includes(po.status))
          .reduce((s,po)=>s+((po.total_amount||0)-(po.vat_amount||0)),0);
        const depr = (deprSchedule||[]).reduce((s,d)=>s+(d.amount||0),0);
        const payrollCost = (emps||[]).filter(e=>e.is_active!==false)
          .reduce((s,e)=>s+calcPayroll(e.gross_salary).totalCost,0);
        const netProfit = rev - exp - poCogs - depr - payrollCost;
        setDrill({type, title:"Net Profit Breakdown — All Time", color:C.accent,
          total: netProfit,
          cols:["Category","Amount"],
          rows:[
            ["Revenue (paid invoices)",          fmt(rev)],
            ["Expenses (excl. VAT)",             `- ${fmt(exp)}`],
            ["Cost of Sales — POs (excl. VAT)",  `- ${fmt(poCogs)}`],
            ["Depreciation (IAS 16)",            `- ${fmt(depr)}`],
            ["Payroll (employer total cost)",    `- ${fmt(payrollCost)}`],
            ["Net Profit",                        fmt(netProfit)],
          ]});
      }
    } catch(e) { setDrill(null); }
    setDrillLoading(false);
  };

  // Use live data if available, otherwise fall back to mock
  const totalRevenue  = d ? d.total_revenue  : MOCK_INVOICES.filter(i => i.status === "paid").reduce((s,i) => s + i.amount, 0);
  const totalExpenses = d ? d.total_expenses : MOCK_EXPENSES.reduce((s,e) => s + e.amount, 0);
  const outstanding   = d ? d.total_outstanding : MOCK_INVOICES.filter(i => i.status !== "paid").reduce((s,i) => s + i.amount, 0);
  const profit        = d ? Math.round((d.net_profit - (d.tax_provision||0))*100)/100 : totalRevenue - totalExpenses;
  const totalPayroll  = d ? d.total_payroll  : MOCK_EMPLOYEES.reduce((s,e) => s + calcPayroll(e.salary).totalCost, 0);
  const netVatPayable = d ? d.net_vat_payable : null;
  const vatColor      = netVatPayable === null ? C.inkMid : netVatPayable >= 0 ? C.red : C.green;
  const vatSub        = netVatPayable === null ? "Output minus input VAT" : netVatPayable >= 0 ? "Payable to SARS" : "Refund due from SARS";
  return (
    <div>
      <CIPCBanner cipc={d?.cipc} poDupWarning={d?.po_duplicate_warning}/>
      <div style={{marginBottom:24,display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
        <div>
          <h1 style={{fontFamily:"serif",fontSize:28,color:C.ink,margin:"0 0 4px"}}>{(()=>{const h=new Date().getHours();return h<12?"Good morning":h<17?"Good afternoon":"Good evening";})()}</h1>
          <p style={{color:C.inkMid,fontSize:13}}>Financial overview - {d ? d.period : new Date().toLocaleDateString("en-ZA",{month:"long",year:"numeric"})}</p>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:6,padding:"6px 14px",borderRadius:20,background:isLive?C.greenLt:C.goldLt,border:`1px solid ${isLive?C.green:C.gold}`}}>
          <div style={{width:6,height:6,borderRadius:"50%",background:isLive?C.green:C.gold}}/>
          <span style={{fontSize:11,fontWeight:600,color:isLive?C.green:C.gold}}>{isLive?"Live Data":"Demo Mode"}</span>
        </div>
      </div>
      <div style={{display:"flex",gap:12,marginBottom:20,flexWrap:"wrap"}}>
        <KPI label="Revenue" value={fmt(totalRevenue)} sub="All paid invoices" color={C.green} icon="💰" onClick={()=>openDrill("revenue")}/>
        <KPI label="Expenses" value={fmt(totalExpenses)} sub="Excl. VAT, all time" color={C.red} icon="📤" onClick={()=>openDrill("expenses")}/>
        <KPI label="Net Profit" value={fmt(profit)} sub="After all costs &amp; 27% tax" color={C.accent} icon="📊" onClick={()=>openDrill("profit")}/>
        <KPI label="Outstanding" value={fmt(outstanding)} sub="Pending invoices" color={C.gold} icon="⏳" onClick={()=>openDrill("outstanding")}/>
        <KPI label="Payroll" value={fmt(totalPayroll)} sub={`${d?.employee_count||""} employees`} color={C.blue} icon="👥" onClick={()=>openDrill("payroll")}/>
        <KPI label="Net VAT" value={netVatPayable !== null ? fmt(Math.abs(netVatPayable)) : "—"} sub={vatSub} color={vatColor} icon="🏛️" onClick={()=>openDrill("vat")}/>
      </div>

      {/* ── KPI Drill-down Modal ── */}
      {(drill || drillLoading) && (
        <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.45)",zIndex:900,display:"flex",alignItems:"center",justifyContent:"center",padding:24}}
          onClick={e=>{if(e.target===e.currentTarget){setDrill(null);setDrillLoading(false);}}}>
          <div style={{background:C.surface,borderRadius:20,width:"100%",maxWidth:780,maxHeight:"80vh",display:"flex",flexDirection:"column",boxShadow:"0 8px 40px rgba(0,0,0,0.22)"}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"20px 24px 12px",borderBottom:`1px solid ${C.border}`}}>
              <div>
                <div style={{fontSize:15,fontWeight:800,color:C.ink}}>{drill?.title||"Loading…"}</div>
                {drill?.total !== undefined && <div style={{fontSize:12,color:drill.color,fontWeight:700,marginTop:2}}>Total: {fmt(drill.total)}</div>}
              </div>
              <button onClick={()=>{setDrill(null);setDrillLoading(false);}} style={{background:"none",border:"none",fontSize:20,cursor:"pointer",color:C.inkMid}}>✕</button>
            </div>
            <div style={{overflowY:"auto",padding:"0 24px 24px"}}>
              {drillLoading ? (
                <div style={{textAlign:"center",padding:40,color:C.inkMid,fontSize:13}}>Loading…</div>
              ) : drill?.rows?.length === 0 ? (
                <div style={{textAlign:"center",padding:40,color:C.inkMid,fontSize:13}}>No records found for this period.</div>
              ) : (
                <table style={{width:"100%",borderCollapse:"collapse",fontSize:13,marginTop:12}}>
                  <thead><tr>{drill?.cols?.map(c=><th key={c} style={{textAlign:"left",padding:"8px 10px",color:C.inkMid,fontWeight:600,fontSize:11,textTransform:"uppercase",borderBottom:`1px solid ${C.border}`,whiteSpace:"nowrap"}}>{c}</th>)}</tr></thead>
                  <tbody>{drill?.rows?.map((row,ri)=>(
                    <tr key={ri} style={{borderBottom:`1px solid ${C.border}`}}>
                      {row.map((cell,ci)=><td key={ci} style={{padding:"10px 10px",color:ci===0?C.ink:C.inkMid,fontWeight:ci===0?600:400}}>{cell}</td>)}
                    </tr>
                  ))}</tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      <div style={{display:"grid",gridTemplateColumns:"2fr 1fr",gap:16,marginBottom:20}}>
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:20}}>
          <div style={{fontSize:14,fontWeight:700,color:C.ink,marginBottom:16}}>Revenue vs Expenses - Last 6 months</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={revenueData} barGap={4}>
              <CartesianGrid stroke={C.border} strokeDasharray="3 3" vertical={false}/>
              <XAxis dataKey="month" tick={{fontSize:10,fill:C.inkMid}} tickLine={false} axisLine={false}/>
              <YAxis tick={{fontSize:10,fill:C.inkMid}} tickLine={false} axisLine={false} tickFormatter={v => `R${v/1000}k`} width={45}/>
              <Tooltip content={<Tooltip2/>}/>
              <Bar dataKey="revenue" name="Revenue" fill={C.green} radius={[4,4,0,0]}/>
              <Bar dataKey="expenses" name="Expenses" fill={C.accent} radius={[4,4,0,0]}/>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:20}}>
          <div style={{fontSize:14,fontWeight:700,color:C.ink,marginBottom:16}}>Expense Breakdown</div>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie data={EXPENSE_PIE} dataKey="value" cx="50%" cy="50%" innerRadius={45} outerRadius={70}>
                {EXPENSE_PIE.map((e,i) => <Cell key={i} fill={e.color}/>)}
              </Pie>
              <Tooltip formatter={v => fmt(v)}/>
            </PieChart>
          </ResponsiveContainer>
          {EXPENSE_PIE.map((e,i) => (
            <div key={i} style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
              <div style={{display:"flex",gap:6,alignItems:"center"}}>
                <div style={{width:8,height:8,borderRadius:"50%",background:e.color}}/>
                <span style={{fontSize:10,color:C.inkMid}}>{e.name}</span>
              </div>
              <span style={{fontSize:10,fontWeight:600}}>{fmt(e.value)}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:20,marginBottom:20}}>
        <div style={{fontSize:14,fontWeight:700,color:C.ink,marginBottom:4}}>Gross Profit Trend</div>
        <div style={{fontSize:11,color:C.inkMid,marginBottom:12}}>Revenue minus expenses (excl. payroll)</div>
        <ResponsiveContainer width="100%" height={130}>
          <AreaChart data={REVENUE_DATA}>
            <defs>
              <linearGradient id="pg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={C.green} stopOpacity={0.2}/>
                <stop offset="100%" stopColor={C.green} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid stroke={C.border} strokeDasharray="3 3" vertical={false}/>
            <XAxis dataKey="month" tick={{fontSize:10,fill:C.inkMid}} tickLine={false} axisLine={false}/>
            <YAxis tick={{fontSize:10,fill:C.inkMid}} tickLine={false} axisLine={false} tickFormatter={v => `R${v/1000}k`} width={45}/>
            <Tooltip content={<Tooltip2/>}/>
            <Area type="monotone" dataKey="gross_profit" name="Gross Profit" stroke={C.green} strokeWidth={2} fill="url(#pg)" dot={false}/>
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
        <div style={{padding:"16px 20px",borderBottom:`1px solid ${C.border}`,fontWeight:700,fontSize:14,color:C.ink}}>Recent Invoices</div>
        <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
          <thead>
            <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
              {["Invoice","Client","Amount","Due","Status"].map(h => <th key={h} style={{textAlign:"left",padding:"10px 16px",fontSize:10,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {MOCK_INVOICES.map((inv,i) => (
              <tr key={inv.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                <td style={{padding:"12px 16px",fontWeight:700,color:C.accent}}>{inv.id}</td>
                <td style={{padding:"12px 16px"}}>{inv.client}</td>
                <td style={{padding:"12px 16px",fontWeight:700}}>{fmt(inv.amount)}</td>
                <td style={{padding:"12px 16px",color:C.inkMid}}>{fmtDate(inv.due)}</td>
                <td style={{padding:"12px 16px"}}><StatusBadge status={inv.status}/></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Defined outside Invoicing so it never remounts on parent re-render (fixes cursor-jump bug)
function InvFormFields({data, onChange, customers=[]}) {
  const is = {width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"};
  const lb = (txt) => <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{txt}</label>;
  return (
    <>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
        <div>
          {lb("Client")}
          {customers.length>0 && (
            <select value="" onChange={e=>{if(e.target.value) onChange(d=>({...d,client:e.target.value}));}} style={{...is,marginBottom:6}}>
              <option value="">— Select from customers —</option>
              {customers.map(c=><option key={c.id} value={c.name}>{c.name}</option>)}
            </select>
          )}
          <input placeholder="Or type client name" value={data.client||""} onChange={e=>onChange(d=>({...d,client:e.target.value}))} style={is}/>
        </div>
        <div>{lb("Amount (excl. VAT)")}<input type="number" placeholder="50000" value={data.amount||""} onChange={e=>onChange(d=>({...d,amount:e.target.value}))} style={is}/></div>
        <div>{lb("Description")}<input placeholder="Services rendered" value={data.desc||""} onChange={e=>onChange(d=>({...d,desc:e.target.value}))} style={is}/></div>
        <div>{lb("Due Date")}<input type="date" value={data.due||""} onChange={e=>onChange(d=>({...d,due:e.target.value}))} style={is}/></div>
        <div>
          {lb("Currency")}
          <select value={data.currency||"ZAR"} onChange={e=>onChange(d=>({...d,currency:e.target.value}))} style={is}>
            <option value="ZAR">ZAR — South African Rand</option>
            <option value="USD">USD — US Dollar</option>
            <option value="EUR">EUR — Euro</option>
            <option value="GBP">GBP — British Pound</option>
            <option value="BWP">BWP — Botswana Pula</option>
            <option value="ZMW">ZMW — Zambian Kwacha</option>
            <option value="MZN">MZN — Mozambican Metical</option>
            <option value="NAD">NAD — Namibian Dollar</option>
            <option value="KES">KES — Kenyan Shilling</option>
            <option value="CNY">CNY — Chinese Yuan</option>
          </select>
        </div>
        {data.currency && data.currency!=="ZAR" && (
          <div>{lb(`Exchange Rate (1 ${data.currency} = R)`)}<input type="number" value={data.exchangeRate||"18.5"} onChange={e=>onChange(d=>({...d,exchangeRate:e.target.value}))} style={is}/></div>
        )}
      </div>
      {/* VAT — auto 15% for ZAR, manual amount for foreign currency */}
      {(!data.currency || data.currency === "ZAR") ? (
        <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:12}}>
          <label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer",fontSize:13,color:C.ink}}>
            <input type="checkbox" checked={data.vatApplicable !== false} onChange={e=>onChange(d=>({...d,vatApplicable:e.target.checked}))} style={{width:16,height:16,cursor:"pointer"}}/>
            Apply VAT @ 15%
          </label>
        </div>
      ) : (
        <div style={{marginBottom:12}}>
          <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>VAT Amount ({data.currency}) — enter 0 if not applicable</label>
          <input type="number" min="0" placeholder="0" value={data.vatAmount||"0"} onChange={e=>onChange(d=>({...d,vatAmount:e.target.value}))} style={{...is,width:"180px"}}/>
        </div>
      )}
      {data.amount && (
        <div style={{display:"flex",gap:16,fontSize:12,marginBottom:12,flexWrap:"wrap",background:C.bg,padding:"10px 14px",borderRadius:8}}>
          <span style={{color:C.inkMid}}>Excl. VAT: <strong>{fmtCurrency(+data.amount||0,data.currency||"ZAR")}</strong></span>
          {(!data.currency||data.currency==="ZAR")
            ? (data.vatApplicable !== false && <span style={{color:C.inkMid}}>VAT (15%): <strong style={{color:C.gold}}>{fmtCurrency((+data.amount||0)*0.15,"ZAR")}</strong></span>)
            : (+data.vatAmount > 0 && <span style={{color:C.inkMid}}>VAT: <strong style={{color:C.gold}}>{fmtCurrency(+data.vatAmount,data.currency)}</strong></span>)
          }
          <span style={{color:C.inkMid}}>Total: <strong style={{color:C.green}}>{fmtCurrency(
            (!data.currency||data.currency==="ZAR")
              ? (+data.amount||0)*(data.vatApplicable!==false?1.15:1)
              : (+data.amount||0)+(+data.vatAmount||0),
            data.currency||"ZAR"
          )}</strong></span>
          {data.currency&&data.currency!=="ZAR" && <span style={{color:C.blue}}>≈ {fmt(((+data.amount||0)+(+data.vatAmount||0))*(+data.exchangeRate||18.5))} ZAR</span>}
        </div>
      )}
    </>
  );
}

// ── DOCUMENT RENDERER ────────────────────────────────────────────────────────
// Renders invoice or quote in the chosen template layout.
// type: "invoice" | "quote"
// doc:  the invoice/quote object
// user: company info
// tmpl: document template config
function InvoiceDocument({type, doc, user, tmpl = DEFAULT_DOC_TEMPLATE}) {
  const t = {...DEFAULT_DOC_TEMPLATE, ...tmpl};
  const pc = t.primaryColor;
  const ff = t.fontFamily;
  const title = type === "quote" ? t.quoteTitle : t.invoiceTitle;
  const currency = doc.currency || "ZAR";
  const amount   = doc.amount || 0;
  const vatAmt   = doc.vatAmount || 0;
  const total    = doc.totalAmount || (amount + vatAmt) || amount;

  const logoBlock = user.logoUrl
    ? <img src={user.logoUrl} alt="logo" style={{height:56,maxWidth:180,objectFit:"contain",display:"block",marginBottom:2}}/>
    : <div style={{fontFamily:"serif",fontSize:22,fontWeight:800,color:pc}}>{user.companyName||"Your Company"}</div>;

  const tableHeader = (
    <thead>
      <tr style={{
        background: t.tableStyle==="shaded" ? "#f4f4f4" : "transparent",
        borderBottom: `2px solid ${t.tableStyle==="lines"||t.tableStyle==="shaded" ? "#ddd" : "transparent"}`,
      }}>
        <th style={{padding:"9px 12px",textAlign:"left",fontSize:11,color:"#555",fontFamily:ff}}>Description</th>
        <th style={{padding:"9px 12px",textAlign:"right",fontSize:11,color:"#555",fontFamily:ff}}>Amount</th>
      </tr>
    </thead>
  );

  const tableBody = (
    <tbody>
      <tr style={{borderBottom:t.tableStyle!=="clean"?"1px solid #eee":"none"}}>
        <td style={{padding:"12px",color:"#1A1209",fontFamily:ff}}>{doc.desc}</td>
        <td style={{padding:"12px",textAlign:"right",fontWeight:600,fontFamily:ff}}>{fmtCurrency(amount, currency)}</td>
      </tr>
      {vatAmt > 0 && <tr style={{borderBottom:t.tableStyle!=="clean"?"1px solid #eee":"none"}}>
        <td style={{padding:"12px",color:"#888",fontSize:12,fontFamily:ff}}>VAT</td>
        <td style={{padding:"12px",textAlign:"right",color:"#C4920A",fontWeight:600,fontFamily:ff}}>{fmtCurrency(vatAmt, currency)}</td>
      </tr>}
    </tbody>
  );

  const bankingBlock = (t.tableStyle !== "clean" || type === "invoice") && user.bankingDetails
    ? <div style={{background:"#f9f9f9",borderRadius:8,padding:"10px 14px",marginTop:16,fontSize:11,color:"#666",fontFamily:ff}}>
        {user.bankingDetails}
      </div>
    : null;

  const footerBlock = t.footerNote
    ? <div style={{marginTop:12,fontSize:11,color:"#888",fontFamily:ff,borderTop:"1px solid #eee",paddingTop:10}}>{t.footerNote}</div>
    : null;

  // ── CLASSIC ──
  if (t.layout === "classic") return (
    <div style={{fontFamily:ff,color:"#1A1209"}}>
      <div style={{display:"flex",justifyContent:"space-between",marginBottom:28,paddingBottom:16,borderBottom:`2px solid ${pc}`}}>
        <div>{logoBlock}{user.logoUrl&&<div style={{fontSize:12,fontWeight:700,marginTop:2}}>{user.companyName||""}</div>}</div>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:20,fontWeight:800,color:"#1A1209"}}>{title}</div>
          <div style={{fontSize:13,color:"#888",marginTop:4}}>{doc.id}</div>
          {type==="quote"&&doc.validUntil&&<div style={{fontSize:12,color:"#888"}}>Valid until: {fmtDate(doc.validUntil)}</div>}
        </div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:20,marginBottom:24}}>
        <div>
          <div style={{fontSize:10,color:"#888",fontWeight:600,textTransform:"uppercase",marginBottom:6}}>Bill To</div>
          <div style={{fontWeight:700}}>{doc.client}</div>
        </div>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:12,color:"#888"}}>Date: {fmtDate(doc.date)}</div>
          {doc.due&&<div style={{fontSize:12,color:"#888"}}>Due: {fmtDate(doc.due)}</div>}
        </div>
      </div>
      <table style={{width:"100%",borderCollapse:"collapse",marginBottom:24}}>{tableHeader}{tableBody}</table>
      <div style={{borderTop:`2px solid #ddd`,paddingTop:16}}>
        <div style={{display:"flex",justifyContent:"space-between",padding:"8px 0"}}>
          <span style={{fontWeight:800,fontSize:15}}>TOTAL {type==="invoice"?"DUE":""}</span>
          <span style={{fontWeight:800,fontSize:18,color:pc}}>{fmtCurrency(total, currency)}</span>
        </div>
      </div>
      {type==="invoice"&&bankingBlock}
      {footerBlock}
    </div>
  );

  // ── MODERN ──
  if (t.layout === "modern") return (
    <div style={{fontFamily:ff,color:"#1A1209"}}>
      <div style={{background:pc,borderRadius:"8px 8px 0 0",padding:"24px 28px",marginBottom:24,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div>
          {user.logoUrl
            ? <div style={{background:"#fff",borderRadius:8,padding:"6px 10px",display:"inline-block"}}>
                <img src={user.logoUrl} alt="logo" style={{height:42,maxWidth:150,objectFit:"contain",display:"block"}}/>
              </div>
            : <div style={{fontSize:22,fontWeight:800,color:"#fff"}}>{user.companyName||"Your Company"}</div>}
          {user.logoUrl&&<div style={{fontSize:11,color:"rgba(255,255,255,0.85)",marginTop:6}}>{user.companyName}</div>}
        </div>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:22,fontWeight:800,color:"#fff"}}>{title}</div>
          <div style={{fontSize:13,color:"rgba(255,255,255,0.85)",marginTop:4}}>{doc.id}</div>
          {type==="quote"&&doc.validUntil&&<div style={{fontSize:11,color:"rgba(255,255,255,0.75)"}}>Valid until: {fmtDate(doc.validUntil)}</div>}
        </div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:20,marginBottom:24,padding:"0 4px"}}>
        <div>
          <div style={{fontSize:10,color:"#888",fontWeight:600,textTransform:"uppercase",marginBottom:6}}>Bill To</div>
          <div style={{fontWeight:700,fontSize:14}}>{doc.client}</div>
        </div>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:12,color:"#888"}}>Date: {fmtDate(doc.date)}</div>
          {doc.due&&<div style={{fontSize:12,color:"#888"}}>Due: {fmtDate(doc.due)}</div>}
        </div>
      </div>
      <table style={{width:"100%",borderCollapse:"collapse",marginBottom:24}}>
        <thead><tr style={{background:pc}}>
          <th style={{padding:"10px 12px",textAlign:"left",fontSize:11,color:"#fff",fontFamily:ff}}>Description</th>
          <th style={{padding:"10px 12px",textAlign:"right",fontSize:11,color:"#fff",fontFamily:ff}}>Amount</th>
        </tr></thead>
        {tableBody}
      </table>
      <div style={{background:pc+"18",border:`1px solid ${pc}30`,borderRadius:8,padding:"14px 18px",display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
        <span style={{fontWeight:800,fontSize:15}}>TOTAL {type==="invoice"?"DUE":""}</span>
        <span style={{fontWeight:800,fontSize:20,color:pc}}>{fmtCurrency(total, currency)}</span>
      </div>
      {type==="invoice"&&bankingBlock}
      {footerBlock}
    </div>
  );

  // ── MINIMAL ──
  if (t.layout === "minimal") return (
    <div style={{fontFamily:ff,color:"#1A1209"}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:32}}>
        <div>
          {user.logoUrl
            ? <img src={user.logoUrl} alt="logo" style={{height:40,maxWidth:140,objectFit:"contain",display:"block",marginBottom:4}}/>
            : <div style={{fontSize:16,fontWeight:700,letterSpacing:2,textTransform:"uppercase",color:"#1A1209"}}>{user.companyName||"Your Company"}</div>}
          {user.logoUrl&&<div style={{fontSize:11,color:"#888",marginTop:2,letterSpacing:1}}>{user.companyName}</div>}
        </div>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:11,fontWeight:700,letterSpacing:2,textTransform:"uppercase",color:pc}}>{title}</div>
          <div style={{fontSize:18,fontWeight:800,color:"#1A1209",marginTop:4}}>{doc.id}</div>
          {type==="quote"&&doc.validUntil&&<div style={{fontSize:11,color:"#888",marginTop:2}}>Valid: {fmtDate(doc.validUntil)}</div>}
        </div>
      </div>
      <div style={{borderTop:"1px solid #eee",paddingTop:16,marginBottom:20,display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
        <div>
          <div style={{fontSize:10,color:"#888",fontWeight:600,textTransform:"uppercase",letterSpacing:1,marginBottom:4}}>Bill To</div>
          <div style={{fontWeight:600}}>{doc.client}</div>
        </div>
        <div style={{textAlign:"right",fontSize:12,color:"#888"}}>
          <div>Date: {fmtDate(doc.date)}</div>
          {doc.due&&<div>Due: {fmtDate(doc.due)}</div>}
        </div>
      </div>
      <table style={{width:"100%",borderCollapse:"collapse",marginBottom:24}}>
        <thead><tr style={{borderBottom:"1px solid #ddd"}}>
          <th style={{padding:"8px 0",textAlign:"left",fontSize:10,color:"#888",letterSpacing:1,fontWeight:600,textTransform:"uppercase",fontFamily:ff}}>Description</th>
          <th style={{padding:"8px 0",textAlign:"right",fontSize:10,color:"#888",letterSpacing:1,fontWeight:600,textTransform:"uppercase",fontFamily:ff}}>Amount</th>
        </tr></thead>
        <tbody>
          <tr><td style={{padding:"12px 0",color:"#1A1209",fontFamily:ff}}>{doc.desc}</td><td style={{padding:"12px 0",textAlign:"right",fontWeight:600,fontFamily:ff}}>{fmtCurrency(amount,currency)}</td></tr>
          {vatAmt>0&&<tr style={{borderTop:"1px solid #f0f0f0"}}><td style={{padding:"8px 0",color:"#888",fontSize:12,fontFamily:ff}}>VAT</td><td style={{padding:"8px 0",textAlign:"right",fontFamily:ff}}>{fmtCurrency(vatAmt,currency)}</td></tr>}
        </tbody>
      </table>
      <div style={{borderTop:"1px solid #ddd",paddingTop:12,display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
        <span style={{fontSize:11,fontWeight:700,letterSpacing:2,textTransform:"uppercase",color:"#888"}}>Total {type==="invoice"?"Due":""}</span>
        <span style={{fontSize:22,fontWeight:800,color:pc}}>{fmtCurrency(total,currency)}</span>
      </div>
      {type==="invoice"&&user.bankingDetails&&<div style={{marginTop:16,fontSize:11,color:"#888",fontFamily:ff}}>{user.bankingDetails}</div>}
      {footerBlock}
    </div>
  );

  // ── BOLD ──
  return (
    <div style={{fontFamily:ff,color:"#1A1209"}}>
      <div style={{background:"#1A1209",padding:"28px 32px",marginBottom:0,display:"flex",justifyContent:"space-between",alignItems:"flex-end"}}>
        <div>
          {user.logoUrl
            ? <div style={{background:"#fff",borderRadius:8,padding:"6px 10px",display:"inline-block"}}>
                <img src={user.logoUrl} alt="logo" style={{height:42,maxWidth:150,objectFit:"contain",display:"block"}}/>
              </div>
            : <div style={{fontSize:20,fontWeight:800,color:"#fff"}}>{user.companyName||"Your Company"}</div>}
        </div>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:11,fontWeight:700,letterSpacing:3,color:pc,textTransform:"uppercase"}}>{title}</div>
          <div style={{fontSize:28,fontWeight:900,color:"#fff",lineHeight:1.1,marginTop:4}}>{doc.id}</div>
        </div>
      </div>
      <div style={{background:pc,padding:"12px 32px",display:"flex",justifyContent:"space-between",marginBottom:24}}>
        <div style={{fontSize:12,color:"rgba(255,255,255,0.9)"}}>Bill To: <strong style={{color:"#fff"}}>{doc.client}</strong></div>
        <div style={{fontSize:12,color:"rgba(255,255,255,0.9)"}}>Date: {fmtDate(doc.date)}{doc.due?` · Due: ${fmtDate(doc.due)}`:""}</div>
      </div>
      <table style={{width:"100%",borderCollapse:"collapse",marginBottom:24}}>
        <thead><tr style={{background:"#f5f5f5"}}>
          <th style={{padding:"11px 16px",textAlign:"left",fontSize:11,fontWeight:700,letterSpacing:1,textTransform:"uppercase",color:"#555",fontFamily:ff}}>Description</th>
          <th style={{padding:"11px 16px",textAlign:"right",fontSize:11,fontWeight:700,letterSpacing:1,textTransform:"uppercase",color:"#555",fontFamily:ff}}>Amount</th>
        </tr></thead>
        <tbody>
          <tr style={{borderBottom:"1px solid #eee"}}><td style={{padding:"14px 16px",fontFamily:ff}}>{doc.desc}</td><td style={{padding:"14px 16px",textAlign:"right",fontWeight:700,fontFamily:ff}}>{fmtCurrency(amount,currency)}</td></tr>
          {vatAmt>0&&<tr style={{borderBottom:"1px solid #eee"}}><td style={{padding:"10px 16px",color:"#888",fontSize:12,fontFamily:ff}}>VAT</td><td style={{padding:"10px 16px",textAlign:"right",fontFamily:ff}}>{fmtCurrency(vatAmt,currency)}</td></tr>}
        </tbody>
      </table>
      <div style={{background:"#1A1209",borderRadius:8,padding:"16px 20px",display:"flex",justifyContent:"space-between",alignItems:"center",margin:"0 0 16px"}}>
        <span style={{fontWeight:800,fontSize:14,color:"#fff",letterSpacing:1,textTransform:"uppercase"}}>Total {type==="invoice"?"Due":""}</span>
        <span style={{fontWeight:900,fontSize:22,color:pc}}>{fmtCurrency(total,currency)}</span>
      </div>
      {type==="invoice"&&user.bankingDetails&&<div style={{background:"#f9f9f9",borderRadius:6,padding:"10px 14px",fontSize:11,color:"#666",fontFamily:ff}}>{user.bankingDetails}</div>}
      {footerBlock}
    </div>
  );
}

// ── DOCUMENT TEMPLATE SETTINGS ───────────────────────────────────────────────
function DocumentTemplateSettings({template, onChange}) {
  const t = {...DEFAULT_DOC_TEMPLATE, ...template};
  const set = (k, v) => onChange({...t, [k]: v});

  const LAYOUTS = [
    {id:"classic", label:"Classic",  desc:"Logo left, title right. Clean professional.",   preview:"🗒️"},
    {id:"modern",  label:"Modern",   desc:"Coloured header band. Bold and contemporary.",  preview:"🎨"},
    {id:"minimal", label:"Minimal",  desc:"Clean lines, elegant typography. Less is more.", preview:"✏️"},
    {id:"bold",    label:"Bold",     desc:"Dark header, large number. High impact.",        preview:"⚡"},
  ];
  const FONTS = [
    {id:"Arial, sans-serif",           label:"Arial (Sans-serif)"},
    {id:"Georgia, serif",              label:"Georgia (Serif)"},
    {id:"'Courier New', monospace",    label:"Courier (Monospace)"},
    {id:"Helvetica, Arial, sans-serif",label:"Helvetica"},
  ];
  const TABLE_STYLES = [
    {id:"shaded", label:"Shaded header"},
    {id:"lines",  label:"Lines only"},
    {id:"clean",  label:"Clean / no lines"},
  ];

  const inputStyle = {width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"};
  const labelStyle = {fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5};

  // Sample doc for live preview
  const sampleDoc = {id:"INV-001",client:"Sample Client Pty Ltd",desc:"Professional services rendered",date:new Date().toISOString().slice(0,10),due:new Date(Date.now()+30*864e5).toISOString().slice(0,10),amount:10000,vatAmount:1500,totalAmount:11500,currency:"ZAR"};
  const sampleUser = {companyName:"Your Company",logoUrl:"",bankingDetails:"FNB Business · Acc: 123456789 · Branch: 250655",...(template||{})};

  return (
    <div style={{display:"grid",gridTemplateColumns:"1fr 420px",gap:24,alignItems:"start"}}>
      {/* ── Left: Controls ── */}
      <div>
        {/* Layout picker */}
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:20,marginBottom:16}}>
          <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:14}}>Layout</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
            {LAYOUTS.map(l=>(
              <div key={l.id} onClick={()=>set("layout",l.id)} style={{border:`2px solid ${t.layout===l.id?t.primaryColor:C.border}`,background:t.layout===l.id?t.primaryColor+"10":"transparent",borderRadius:12,padding:"14px 16px",cursor:"pointer",transition:"all 0.15s"}}>
                <div style={{fontSize:22,marginBottom:6}}>{l.preview}</div>
                <div style={{fontSize:13,fontWeight:700,color:C.ink}}>{l.label}</div>
                <div style={{fontSize:11,color:C.inkMid,marginTop:3}}>{l.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Colours + Font */}
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:20,marginBottom:16}}>
          <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:14}}>Branding</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
            <div>
              <label style={labelStyle}>Primary Colour</label>
              <div style={{display:"flex",alignItems:"center",gap:10}}>
                <input type="color" value={t.primaryColor} onChange={e=>set("primaryColor",e.target.value)} style={{width:44,height:36,border:`1px solid ${C.border}`,borderRadius:6,cursor:"pointer",padding:2}}/>
                <input value={t.primaryColor} onChange={e=>set("primaryColor",e.target.value)} style={{...inputStyle,flex:1}} placeholder="#C8401A"/>
              </div>
            </div>
            <div>
              <label style={labelStyle}>Font</label>
              <select value={t.fontFamily} onChange={e=>set("fontFamily",e.target.value)} style={inputStyle}>
                {FONTS.map(f=><option key={f.id} value={f.id}>{f.label}</option>)}
              </select>
            </div>
          </div>
        </div>

        {/* Table style */}
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:20,marginBottom:16}}>
          <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:14}}>Table Style</div>
          <div style={{display:"flex",gap:8}}>
            {TABLE_STYLES.map(s=>(
              <button key={s.id} onClick={()=>set("tableStyle",s.id)} style={{flex:1,padding:"9px 12px",borderRadius:8,border:`2px solid ${t.tableStyle===s.id?t.primaryColor:C.border}`,background:t.tableStyle===s.id?t.primaryColor+"10":"transparent",color:t.tableStyle===s.id?C.ink:C.inkMid,fontSize:12,fontWeight:t.tableStyle===s.id?700:400,cursor:"pointer",fontFamily:"inherit"}}>{s.label}</button>
            ))}
          </div>
        </div>

        {/* Titles + Footer */}
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:20,marginBottom:16}}>
          <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:14}}>Document Titles &amp; Footer</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:14}}>
            <div>
              <label style={labelStyle}>Invoice Title</label>
              <input value={t.invoiceTitle} onChange={e=>set("invoiceTitle",e.target.value)} style={inputStyle} placeholder="TAX INVOICE"/>
            </div>
            <div>
              <label style={labelStyle}>Quote Title</label>
              <input value={t.quoteTitle} onChange={e=>set("quoteTitle",e.target.value)} style={inputStyle} placeholder="QUOTE / ESTIMATE"/>
            </div>
          </div>
          <div>
            <label style={labelStyle}>Footer Note (appears at bottom of every document)</label>
            <textarea value={t.footerNote} onChange={e=>set("footerNote",e.target.value)} rows={3} style={{...inputStyle,resize:"vertical"}} placeholder="e.g. Payment terms: 30 days. Thank you for your business!"/>
          </div>
        </div>
      </div>

      {/* ── Right: Live Preview ── */}
      <div style={{position:"sticky",top:24}}>
        <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:10}}>Live Preview</div>
        <div style={{background:"#fff",border:`1px solid ${C.border}`,borderRadius:12,overflow:"hidden",boxShadow:"0 4px 24px rgba(0,0,0,0.08)"}}>
          <div style={{padding:24,transform:"scale(0.85)",transformOrigin:"top left",width:"117%"}}>
            <InvoiceDocument type="invoice" doc={sampleDoc} user={sampleUser} tmpl={t}/>
          </div>
        </div>
        <div style={{fontSize:11,color:C.inkMid,marginTop:8,textAlign:"center"}}>Preview updates in real time</div>
      </div>
    </div>
  );
}

// ── INVOICING ─────────────────────────────────────────────────────────────────
function Invoicing({live = {}, user = {}, docTemplate}) {
  const liveInvoices = live.invoices;
  const [invoices, setInvoices] = useState(MOCK_INVOICES);
  useEffect(() => { if (liveInvoices && liveInvoices.length > 0) setInvoices(liveInvoices.map(i => ({...i, _dbId: i.id, date: i.issue_date || i.date, due: i.due_date || i.due, client: i.client_name || i.client, desc: i.description, amount: i.total_amount || i.amount, id: i.invoice_number || `INV-${String(i.id).padStart(3,"0")}`}))); }, [liveInvoices]);

  const [showNew,      setShowNew]      = useState(false);
  const [preview,      setPreview]      = useState(null);   // view modal
  const [editInv,      setEditInv]      = useState(null);   // amend modal
  const [payModal,     setPayModal]     = useState(null);   // {inv, zarAmt, payDate, ref}
  const [filterStatus, setFilterStatus] = useState(null);   // null | "paid" | "pending" | "overdue"
  const [form, setForm] = useState({client:"",amount:"",desc:"",due:"",vatApplicable:true,currency:"ZAR",exchangeRate:"18.5",vatAmount:"0"});
  const [saving, setSaving] = useState(false);
  const [customers, setCustomers] = useState([]);
  useEffect(()=>{ api("/customers/").then(setCustomers).catch(()=>{}); },[]);

  const toZar = i => (i.currency && i.currency !== "ZAR") ? (i.amount||0) * (i.exchange_rate||1) : (i.amount||0);
  const totalPaid    = invoices.filter(i => i.status === "paid").reduce((s,i) => s + toZar(i), 0);
  const totalPending = invoices.filter(i => i.status === "pending").reduce((s,i) => s + toZar(i), 0);
  const totalOverdue = invoices.filter(i => i.status === "overdue").reduce((s,i) => s + toZar(i), 0);
  const displayedInvoices = filterStatus ? invoices.filter(i => i.status === filterStatus) : invoices;
  const toggleFilter = (status) => setFilterStatus(prev => prev === status ? null : status);

  const openPayModal = (inv) => {
    const zarAmt = inv.currency && inv.currency !== "ZAR"
      ? ((inv.amount||0) * (inv.exchange_rate||inv.rate||18.5)).toFixed(2)
      : (inv.amount||"");
    setPayModal({inv, zarAmt, payDate: new Date().toISOString().slice(0,10), ref:""});
  };

  const handleRecordPayment = async () => {
    const {inv, zarAmt, payDate, ref} = payModal;
    setInvoices(prev => prev.map(i => i.id === inv.id ? {...i, status:"paid"} : i));
    setPayModal(null);
    try {
      await api(`/invoices/${inv._dbId || inv.id}`, { method:"PUT", body: JSON.stringify({
        status: "paid",
        paid_date: payDate || new Date().toISOString().slice(0,10),
        paid_amount_zar: +zarAmt || null,
        notes: ref || null,
      })});
      if (live && live.reload) live.reload();
    } catch(e) { console.warn("Record payment failed:", e.message); }
  };

  const handleCreate = async () => {
    if(!form.client||!form.amount||!form.desc){alert("Client, description and amount are required.");return;}
    setSaving(true);
    try {
      const invBody = { client_name:form.client, description:form.desc, amount:+form.amount, vat_applicable:form.vatApplicable, due_date:form.due||null, currency:form.currency||"ZAR", exchange_rate:+form.exchangeRate||1.0 };
      if (form.currency && form.currency !== "ZAR") invBody.vat_amount_override = +form.vatAmount||0;
      await api("/invoices/", { method:"POST", body: JSON.stringify(invBody) });
      if (live && live.reload) live.reload();
      setShowNew(false);
      setForm({client:"",amount:"",desc:"",due:"",vatApplicable:true});
    } catch(err) { alert("Failed to create invoice. Please try again."); }
    finally { setSaving(false); }
  };

  const handleAmend = async () => {
    setInvoices(prev => prev.map(i => i.id === editInv.id ? {...editInv} : i));
    setEditInv(null);
    try {
      await api(`/invoices/${editInv._dbId || editInv.id}`, { method:"PUT", body: JSON.stringify({ client_name:editInv.client, description:editInv.desc, amount:+editInv.amount, due_date:editInv.due||null, status:editInv.status }) });
      if (live && live.reload) live.reload();
    } catch(err) { console.warn("Amend failed:", err.message); }
  };

  // InvFormFields moved outside component — see top-level definition below

  const isMobile = typeof window !== "undefined" && window.innerWidth <= 768;
  const printInvoice = () => { const el=document.getElementById("invoice-preview-content"); if(!el)return; const w=window.open("","_blank"); if(!w){alert("Allow popups to print.");return;} w.document.write(`<html><head><title>Invoice ${preview.id}</title><style>body{font-family:Arial,sans-serif;padding:40px;color:#1A1209;}@media print{body{padding:20px;}}</style></head><body>${el.innerHTML}</body></html>`); w.document.close(); w.onload=()=>{w.focus();w.print();w.close();}; };

  return (
    <div>
      <SectionHeader title="Invoicing" sub="Manage your client invoices" action="+ New Invoice" onAction={() => setShowNew(true)}/>
      <div style={{display:"flex",gap:12,marginBottom:filterStatus?12:24}}>
        <KPI label="Paid"    value={fmt(totalPaid)}    color={C.green} icon="✅" onClick={()=>toggleFilter("paid")}    active={filterStatus==="paid"}/>
        <KPI label="Pending" value={fmt(totalPending)} color={C.gold}  icon="⏳" onClick={()=>toggleFilter("pending")} active={filterStatus==="pending"}/>
        <KPI label="Overdue" value={fmt(totalOverdue)} color={C.red}   icon="⚠️" onClick={()=>toggleFilter("overdue")} active={filterStatus==="overdue"}/>
      </div>
      {filterStatus && (
        <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:16,padding:"10px 16px",background:C.accentLt,border:`1px solid ${C.accent}30`,borderRadius:10}}>
          <span style={{fontSize:13,color:C.accent,fontWeight:600,textTransform:"capitalize"}}>Showing: {filterStatus} ({displayedInvoices.length} invoice{displayedInvoices.length!==1?"s":""})</span>
          <button onClick={()=>setFilterStatus(null)} style={{marginLeft:"auto",background:"none",border:`1px solid ${C.accent}40`,borderRadius:6,padding:"4px 10px",fontSize:12,color:C.accent,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>✕ Show All</button>
        </div>
      )}

      {/* New Invoice */}
      {showNew && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:24,marginBottom:20}}>
          <h3 style={{fontFamily:"serif",margin:"0 0 16px",color:C.ink}}>New Invoice</h3>
          <InvFormFields data={form} onChange={setForm} customers={customers}/>
          <div style={{display:"flex",gap:8}}>
            <button onClick={handleCreate} disabled={saving} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>{saving?"Saving...":"Create Invoice"}</button>
            <button onClick={() => setShowNew(false)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
          </div>
        </div>
      )}

      {/* ── MOBILE: Full-screen invoice detail ── */}
      {preview && isMobile && (
        <div style={{position:"fixed",inset:0,background:C.bg,zIndex:200,display:"flex",flexDirection:"column",overflowY:"hidden"}}>
          {/* Sticky header */}
          <div style={{display:"flex",alignItems:"center",gap:12,padding:"14px 16px",background:C.surface,borderBottom:`1px solid ${C.border}`,flexShrink:0}}>
            <button onClick={()=>setPreview(null)} style={{background:"none",border:"none",fontSize:22,cursor:"pointer",color:C.ink,lineHeight:1,padding:"0 4px"}}>←</button>
            <div style={{flex:1}}>
              <div style={{fontWeight:800,fontSize:16,color:C.accent}}>{preview.id}</div>
              <div style={{fontSize:12,color:C.inkMid}}>{preview.client}</div>
            </div>
            <StatusBadge status={preview.status}/>
          </div>
          {/* Scrollable document body */}
          <div style={{flex:1,overflowY:"auto",padding:"20px 16px",WebkitOverflowScrolling:"touch"}}>
            <div id="invoice-preview-content">
              <InvoiceDocument type="invoice" doc={preview} user={user} tmpl={docTemplate}/>
            </div>
            {user.payfastMerchantId && (
              <div style={{background:C.greenLt,border:`1px solid ${C.green}30`,borderRadius:10,padding:"12px 14px",marginTop:16,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                <div><div style={{fontSize:12,fontWeight:700,color:C.green}}>Online Payment</div><div style={{fontSize:11,color:C.inkMid}}>PayFast payment link</div></div>
                <button onClick={()=>{const params=new URLSearchParams({merchant_id:user.payfastMerchantId,merchant_key:user.payfastMerchantKey||"",amount:preview.amount.toFixed(2),item_name:`Invoice ${preview.id}`,item_description:preview.desc||"Payment",email_address:preview.clientEmail||""});window.open(`https://www.payfast.co.za/eng/process?${params.toString()}`,"_blank");}} style={{background:C.green,color:"#fff",border:"none",borderRadius:8,padding:"8px 14px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Pay →</button>
              </div>
            )}
          </div>
          {/* Sticky action bar */}
          <div style={{flexShrink:0,background:C.surface,borderTop:`1px solid ${C.border}`,padding:"12px 16px",display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
            {preview.status !== "paid" && (
              <button onClick={()=>{setPreview(null);openPayModal(preview);}} style={{gridColumn:"1/-1",background:C.green,color:"#fff",border:"none",borderRadius:12,padding:"14px",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>✓ Record Payment</button>
            )}
            <button onClick={()=>{setPreview(null);setEditInv({...preview});}} style={{background:C.goldLt,color:C.gold,border:`1px solid ${C.gold}30`,borderRadius:12,padding:"13px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Amend</button>
            <button onClick={printInvoice} style={{background:C.accent,color:"#fff",border:"none",borderRadius:12,padding:"13px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Print / PDF</button>
            <button onClick={async()=>{if(!window.confirm(`Delete ${preview.id}?`))return;setInvoices(p=>p.filter(i=>i.id!==preview.id));setPreview(null);try{await api(`/invoices/${preview._dbId||preview.id}`,{method:"DELETE"});}catch(e){}}} style={{background:C.redLt,color:C.red,border:`1px solid ${C.red}30`,borderRadius:12,padding:"13px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Delete</button>
            <button onClick={()=>setPreview(null)} style={{background:"transparent",border:`1px solid ${C.border}`,borderRadius:12,padding:"13px",fontSize:13,cursor:"pointer",fontFamily:"inherit",color:C.inkMid}}>Close</button>
          </div>
        </div>
      )}

      {/* ── DESKTOP: floating modal ── */}
      {preview && !isMobile && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center"}} onClick={() => setPreview(null)}>
          <div style={{background:"#fff",borderRadius:20,padding:40,width:560,maxHeight:"80vh",overflow:"auto"}} onClick={e => e.stopPropagation()}>
            <div id="invoice-preview-content">
            <InvoiceDocument type="invoice" doc={preview} user={user} tmpl={docTemplate}/>
            </div>
            {user.payfastMerchantId && (
              <div style={{background:C.greenLt,border:`1px solid ${C.green}30`,borderRadius:10,padding:"12px 16px",marginTop:16,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                <div><div style={{fontSize:12,fontWeight:700,color:C.green}}>Online Payment</div><div style={{fontSize:11,color:C.inkMid}}>Send client a PayFast payment link</div></div>
                <button onClick={()=>{const params=new URLSearchParams({merchant_id:user.payfastMerchantId,merchant_key:user.payfastMerchantKey||"",amount:preview.amount.toFixed(2),item_name:`Invoice ${preview.id}`,item_description:preview.desc||"Payment",email_address:preview.clientEmail||""});window.open(`https://www.payfast.co.za/eng/process?${params.toString()}`,"_blank");}} style={{background:C.green,color:"#fff",border:"none",borderRadius:8,padding:"8px 16px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Open PayFast →</button>
              </div>
            )}
            {!user.payfastMerchantId && (
              <div style={{background:C.goldLt,border:`1px solid ${C.gold}30`,borderRadius:10,padding:"10px 16px",marginTop:12,fontSize:11,color:C.inkMid}}>Add your PayFast Merchant ID in Settings to enable online payments.</div>
            )}
            <div style={{display:"flex",gap:8,marginTop:16}}>
              <button onClick={() => { setPreview(null); setEditInv({...preview}); }} style={{flex:1,background:C.goldLt,color:C.gold,border:`1px solid ${C.gold}40`,borderRadius:10,padding:"11px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Amend</button>
              <button onClick={printInvoice} style={{flex:1,background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"11px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Print / PDF</button>
              <button onClick={() => setPreview(null)} style={{flex:1,background:"transparent",border:`1px solid ${C.border}`,borderRadius:10,padding:"11px",fontSize:13,cursor:"pointer",fontFamily:"inherit",color:C.inkMid}}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Amend Modal */}
      {editInv && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center",padding:20}} onClick={() => setEditInv(null)}>
          <div style={{background:C.surface,borderRadius:20,padding:32,width:580,maxHeight:"90vh",overflow:"auto"}} onClick={e=>e.stopPropagation()}>
            <h3 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:"0 0 20px"}}>Amend Invoice — {editInv.id}</h3>
            <InvFormFields data={editInv} onChange={setEditInv} customers={customers}/>
            <div style={{marginBottom:16}}>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Status</label>
              <select value={editInv.status} onChange={e=>setEditInv({...editInv,status:e.target.value})} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                <option value="pending">Pending</option>
                <option value="paid">Paid</option>
                <option value="overdue">Overdue</option>
              </select>
            </div>
            <div style={{display:"flex",gap:8}}>
              <button onClick={handleAmend} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 24px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Save Changes</button>
              <button onClick={() => setEditInv(null)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Record Payment Modal */}
      {payModal && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center",padding:20}} onClick={()=>setPayModal(null)}>
          <div style={{background:C.surface,borderRadius:20,padding:32,width:460}} onClick={e=>e.stopPropagation()}>
            <h3 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:"0 0 4px"}}>Record Payment</h3>
            <p style={{fontSize:13,color:C.inkMid,marginBottom:24}}>{payModal.inv.id} — {payModal.inv.client}</p>
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <div>
                <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>ZAR Amount Received</label>
                <input type="number" min="0" step="0.01" value={payModal.zarAmt}
                  onChange={e=>setPayModal(p=>({...p,zarAmt:e.target.value}))}
                  style={{width:"100%",padding:"11px 14px",border:`1.5px solid ${C.border}`,borderRadius:10,fontSize:15,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
                {payModal.inv.currency&&payModal.inv.currency!=="ZAR" && (
                  <div style={{fontSize:11,color:C.blue,marginTop:4}}>Invoice is {payModal.inv.currency} — enter the ZAR actually received into your bank account</div>
                )}
              </div>
              <div>
                <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Payment Date</label>
                <input type="date" value={payModal.payDate}
                  onChange={e=>setPayModal(p=>({...p,payDate:e.target.value}))}
                  style={{width:"100%",padding:"11px 14px",border:`1.5px solid ${C.border}`,borderRadius:10,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
              </div>
              <div>
                <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Reference / Notes (optional)</label>
                <input placeholder="e.g. EFT Ref 12345" value={payModal.ref}
                  onChange={e=>setPayModal(p=>({...p,ref:e.target.value}))}
                  style={{width:"100%",padding:"11px 14px",border:`1.5px solid ${C.border}`,borderRadius:10,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
              </div>
            </div>
            <div style={{display:"flex",gap:8,marginTop:24}}>
              <button onClick={handleRecordPayment} style={{flex:1,background:C.green,color:"#fff",border:"none",borderRadius:10,padding:"12px",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>✓ Record Payment</button>
              <button onClick={()=>setPayModal(null)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"12px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* ── MOBILE: card list ── */}
      {isMobile ? (
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          {displayedInvoices.length === 0 && (
            <div style={{padding:"32px",textAlign:"center",color:C.inkMid,fontSize:13,background:C.surface,borderRadius:16,border:`1px solid ${C.border}`}}>No {filterStatus||""} invoices found.</div>
          )}
          {displayedInvoices.map(inv => (
            <div key={inv.id} onClick={()=>setPreview(inv)} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:"16px",cursor:"pointer",WebkitTapHighlightColor:"transparent"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:6}}>
                <div style={{fontWeight:800,fontSize:15,color:C.accent}}>{inv.id}</div>
                <StatusBadge status={inv.status}/>
              </div>
              <div style={{fontWeight:600,fontSize:14,color:C.ink,marginBottom:2}}>{inv.client}</div>
              <div style={{fontSize:12,color:C.inkMid,marginBottom:10,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{inv.desc}</div>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
                <div style={{fontWeight:800,fontSize:16,color:C.ink}}>
                  {inv.currency && inv.currency!=="ZAR" ? fmt((inv.amount||0)*(inv.exchange_rate||1)) : fmt(inv.amount||0)}
                </div>
                <div style={{fontSize:11,color:inv.status==="overdue"?C.red:C.inkMid}}>Due {fmtDate(inv.due)}</div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* ── DESKTOP: table ── */
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
            <thead>
              <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                {["Invoice #","Client","Description","Amount","Date","Due","Status","Actions"].map(h => <th key={h} style={{textAlign:"left",padding:"12px 16px",fontSize:10,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {displayedInvoices.length === 0 && (
                <tr><td colSpan={8} style={{padding:"32px",textAlign:"center",color:C.inkMid,fontSize:13}}>No {filterStatus} invoices found.</td></tr>
              )}
              {displayedInvoices.map((inv) => (
                <tr key={inv.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                  <td style={{padding:"13px 16px",fontWeight:700,color:C.accent,cursor:"pointer"}} onClick={()=>setPreview(inv)}>{inv.id}</td>
                  <td style={{padding:"13px 16px",fontWeight:500}}>{inv.client}</td>
                  <td style={{padding:"13px 16px",color:C.inkMid,fontSize:12}}>{inv.desc}</td>
                  <td style={{padding:"13px 16px",fontWeight:700}}>
                    {inv.currency && inv.currency!=="ZAR"
                      ? <>{fmt((inv.amount||0)*(inv.exchange_rate||1))}<div style={{fontSize:10,color:C.blue,fontWeight:400,marginTop:2}}>{fmtCurrency(inv.amount,inv.currency)}</div></>
                      : fmt(inv.amount||0)}
                  </td>
                  <td style={{padding:"13px 16px",color:C.inkMid}}>{fmtDate(inv.date)}</td>
                  <td style={{padding:"13px 16px",color:inv.status==="overdue"?C.red:C.inkMid}}>{fmtDate(inv.due)}</td>
                  <td style={{padding:"13px 16px"}}><StatusBadge status={inv.status}/></td>
                  <td style={{padding:"13px 16px"}}>
                    <div style={{display:"flex",gap:6}}>
                      <button onClick={() => setPreview(inv)} style={{background:C.blueLt,color:C.blue,border:"none",borderRadius:6,padding:"5px 10px",fontSize:11,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>View</button>
                      <button onClick={() => setEditInv({...inv})} style={{background:C.goldLt,color:C.gold,border:"none",borderRadius:6,padding:"5px 10px",fontSize:11,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Amend</button>
                      {inv.status !== "paid" && (
                        <button onClick={() => openPayModal(inv)} style={{background:C.greenLt,color:C.green,border:"none",borderRadius:6,padding:"5px 10px",fontSize:11,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Record Payment</button>
                      )}
                      <button onClick={async()=>{ if(!window.confirm(`Delete ${inv.id}?`))return; setInvoices(p=>p.filter(i=>i.id!==inv.id)); try{await api(`/invoices/${inv._dbId || inv.id}`,{method:"DELETE"});}catch(e){} }} style={{background:C.redLt,color:C.red,border:"none",borderRadius:6,padding:"5px 10px",fontSize:11,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
// ── EXPENSES ──────────────────────────────────────────────────────────────────
// An expense is "posted" (categorised) when its category is a COA code e.g. "6220 - Electricity and Water"
const isPosted = cat => cat && /^\d{4}/.test(cat);

function Expenses({live = {}}) {
  const liveExpenses = live.expenses;
  const [expenses, setExpenses] = useState(MOCK_EXPENSES);
  const [pendingCats, setPendingCats] = useState({}); // {id: selectedCategory}
  const [view, setView] = useState("unposted"); // "unposted" | "posted"
  const [viewExp,  setViewExp]  = useState(null);
  const [editExp,  setEditExp]  = useState(null);

  useEffect(() => {
    const expRows = liveExpenses && liveExpenses.length > 0
      ? liveExpenses.map(e => ({...e, date: e.expense_date || e.date, desc: e.description, vendor: e.vendor, amount: e.amount, vat_amount: e.vat_amount||0, category: e.category || "", id: `EXP-${String(e.id).padStart(3,"0")}`}))
      : [];
    // Fetch depreciation entries and merge as auto-posted expense rows
    api("/fixed-assets/schedule").then(deprEntries => {
      const deprRows = (deprEntries||[]).map(d => ({
        id: `DEP-${d.id}`,
        date: d.period ? d.period+"-01" : null,
        desc: `${d.asset_name} — Monthly Depreciation`,
        vendor: "Fixed Assets",
        amount: d.amount||0,
        vat_amount: 0,
        category: "5800 - Depreciation",
        _readonly: true,
      }));
      const merged = [...expRows, ...deprRows].sort((a,b)=>new Date(b.date||0)-new Date(a.date||0));
      if (merged.length > 0) setExpenses(merged);
    }).catch(()=>{ if (expRows.length > 0) setExpenses(expRows); });
  }, [liveExpenses]);

  const [showNew,    setShowNew]    = useState(false);
  const [form,       setForm]       = useState({vendor:"",amount:"",category:"",desc:"",vatApplicable:true});
  const [autoNotice, setAutoNotice] = useState("");
  const [saving,     setSaving]     = useState(false);

  const unposted = expenses.filter(e => !isPosted(e.category));
  const posted   = expenses.filter(e => isPosted(e.category));
  const displayed = view === "unposted" ? unposted : posted;
  const total = displayed.reduce((s,e) => s + (e.amount||0) - (e.vat_amount||0), 0);

  // ── Auto-categorise engine ────────────────────────────────────────
  // Build vendor→category map from posted expenses
  const buildMemory = (expList) => {
    const mem = {};
    expList.filter(e => isPosted(e.category)).forEach(e => {
      const key = e.vendor.trim().toLowerCase();
      mem[key] = e.category; // last known category wins
      // also index first word of description
      if (e.desc) {
        const descKey = e.desc.trim().toLowerCase().split(" ").slice(0,3).join(" ");
        if (!mem[descKey]) mem[descKey] = e.category;
      }
    });
    return mem;
  };

  const findSuggestion = (exp, memory) => {
    const vendor = exp.vendor.trim().toLowerCase();
    if (memory[vendor]) return memory[vendor]; // exact vendor match
    // partial vendor match
    const partialKey = Object.keys(memory).find(k => vendor.includes(k) || k.includes(vendor));
    if (partialKey) return memory[partialKey];
    // description match
    if (exp.desc) {
      const descKey = exp.desc.trim().toLowerCase().split(" ").slice(0,3).join(" ");
      if (memory[descKey]) return memory[descKey];
    }
    return null;
  };

  // Run auto-categorise when expenses load — but NOT while form is open (avoids focus loss)
  useEffect(() => {
    if (showNew) return;
    const memory = buildMemory(expenses);
    if (Object.keys(memory).length === 0) return;
    const toPost = [];
    const suggestions = {};
    expenses.filter(e => !isPosted(e.category)).forEach(e => {
      const suggestion = findSuggestion(e, memory);
      if (suggestion) {
        suggestions[e.id] = suggestion;
        toPost.push({...e, category: suggestion});
      }
    });
    if (toPost.length === 0) return;
    // Auto-post exact matches and pre-fill suggestions
    setPendingCats(prev => ({...prev, ...suggestions}));
    // Auto-post all matched
    setExpenses(prev => prev.map(e => {
      const match = toPost.find(t => t.id === e.id);
      return match ? {...e, category: match.category} : e;
    }));
    setAutoNotice(`Auto-categorised ${toPost.length} expense${toPost.length>1?"s":""} based on past history.`);
    setTimeout(() => setAutoNotice(""), 5000);
    // Save to backend
    toPost.forEach(e => {
      api(`/expenses/${e.id}`, { method:"PUT", body: JSON.stringify({category: e.category}) }).catch(()=>{});
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expenses.length, posted.length]);

  const handleAmendExp = async () => {
    setExpenses(prev => prev.map(e => e.id === editExp.id ? {...editExp} : e));
    setEditExp(null);
    try {
      await api(`/expenses/${editExp.id}`, { method:"PUT", body: JSON.stringify({ vendor:editExp.vendor, description:editExp.desc, amount:+editExp.amount, category:editExp.category, expense_date:editExp.date }) });
      if (live && live.reload) live.reload();
    } catch(e) { console.warn("Amend expense failed:", e.message); }
  };

  const handlePost = async (exp) => {
    const cat = pendingCats[exp.id];
    if (!cat || !isPosted(cat)) return;
    setExpenses(prev => prev.map(e => e.id === exp.id ? {...e, category: cat} : e));
    setPendingCats(prev => { const n = {...prev}; delete n[exp.id]; return n; });
    try {
      await api(`/expenses/${exp.id}`, { method:"PUT", body: JSON.stringify({category: cat}) });
      if (live && live.reload) live.reload();
    } catch(err) { console.warn("Category save failed:", err.message); }
  };

  const handleAdd = async () => {
    if(!form.vendor||!form.amount){alert("Vendor and amount are required.");return;}
    setSaving(true);
    try {
      await api("/expenses/", { method:"POST", body: JSON.stringify({ vendor:form.vendor, description:form.desc, amount:+form.amount, vat_applicable:form.vatApplicable, category:form.category, expense_date:new Date().toISOString().slice(0,10), is_on_credit:form.onCredit||false }) });
      if (live && live.reload) live.reload();
      setShowNew(false);
      setForm({vendor:"",amount:"",category:"",desc:"",vatApplicable:true,onCredit:false});
    } catch(err) { alert("Failed to save expense. Please try again."); }
    finally { setSaving(false); }
  };

  return (
    <div>
      <SectionHeader title="Expenses" sub="Categorise expenses to post them to the Income Statement" action="+ Add Expense" onAction={() => setShowNew(true)}/>

      {/* Summary bar */}
      <div style={{display:"flex",gap:12,marginBottom:16}}>
        <KPI label="To Categorise"     value={unposted.length} sub={fmt(unposted.reduce((s,e)=>s+(e.amount||0)-(e.vat_amount||0),0))} color={C.gold}  icon="⏳" onClick={()=>setView("unposted")} active={view==="unposted"}/>
        <KPI label="Posted to Accounts" value={posted.length}  sub={fmt(posted.reduce((s,e)=>s+(e.amount||0)-(e.vat_amount||0),0))}  color={C.green} icon="✅" onClick={()=>setView("posted")}   active={view==="posted"}/>
      </div>
      <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:16,padding:"10px 16px",background:view==="unposted"?C.goldLt:C.greenLt,border:`1px solid ${view==="unposted"?C.gold:C.green}30`,borderRadius:10}}>
        <span style={{fontSize:13,fontWeight:600,color:view==="unposted"?C.gold:C.green}}>
          {view==="unposted"?"Showing uncategorised expenses":"Showing posted expenses"} — {displayed.length} record{displayed.length!==1?"s":""}, {fmt(total)}
        </span>
        <button onClick={()=>setView(view==="unposted"?"posted":"unposted")} style={{marginLeft:"auto",background:"none",border:`1px solid ${view==="unposted"?C.gold:C.green}40`,borderRadius:6,padding:"4px 10px",fontSize:12,color:view==="unposted"?C.gold:C.green,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>
          Switch to {view==="unposted"?"Posted":"Uncategorised"}
        </button>
      </div>

      {showNew && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:24,marginBottom:20}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
            <h3 style={{fontFamily:"serif",margin:0,color:C.ink}}>Add Expense</h3>
            <label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer",padding:"8px 14px",borderRadius:10,border:`1px solid ${C.border}`,background:C.bg,fontSize:12,color:C.blue,fontWeight:600}}>
              📷 Scan Receipt
              <input type="file" accept="image/*" capture="camera" style={{display:"none"}} onChange={async e=>{
                const file = e.target.files[0];
                if(!file) return;
                const reader = new FileReader();
                reader.onload = async ev => {
                  // Show receipt preview
                  setForm(f=>({...f,receiptImage:ev.target.result}));
                  // Try OCR via backend
                  try {
                    const res = await api("/expenses/scan-receipt",{method:"POST",body:JSON.stringify({image:ev.target.result.split(",")[1]})});
                    if(res.vendor)  setForm(f=>({...f,vendor:res.vendor}));
                    if(res.amount)  setForm(f=>({...f,amount:String(res.amount)}));
                    if(res.date)    setForm(f=>({...f,date:res.date}));
                    if(res.desc)    setForm(f=>({...f,desc:res.desc}));
                  } catch(err) { console.warn("OCR failed:",err.message); }
                };
                reader.readAsDataURL(file);
              }}/>
            </label>
          </div>
          {form.receiptImage && (
            <div style={{marginBottom:12,position:"relative"}}>
              <img src={form.receiptImage} alt="Receipt" style={{width:"100%",maxHeight:180,objectFit:"cover",borderRadius:8,border:`1px solid ${C.border}`}}/>
              <button onClick={()=>setForm(f=>({...f,receiptImage:null}))} style={{position:"absolute",top:6,right:6,background:"rgba(0,0,0,0.6)",color:"#fff",border:"none",borderRadius:"50%",width:24,height:24,cursor:"pointer",fontSize:12}}>✕</button>
              <div style={{background:C.greenLt,borderRadius:6,padding:"6px 10px",marginTop:6,fontSize:11,color:C.green}}>✓ Receipt captured — fields pre-filled where possible</div>
            </div>
          )}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Vendor</label>
              <input placeholder="Eskom" value={form.vendor} onChange={e => setForm(f=>({...f,vendor:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
            </div>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Amount (ZAR excl. VAT)</label>
              <input placeholder="1500" value={form.amount} onChange={e => setForm(f=>({...f,amount:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
            </div>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Description</label>
              <input placeholder="Monthly bill" value={form.desc} onChange={e => setForm(f=>({...f,desc:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
            </div>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Account (optional)</label>
              <select value={form.category} onChange={e => setForm({...form,category:e.target.value})} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                <option value="">-- Categorise later --</option>
                {EXPENSE_COA_GROUPS.map(group => (
                  <optgroup key={group} label={group}>
                    {DEFAULT_COA.filter(a => a.group === group && a.type === "Detail").map(a => (
                      <option key={a.code} value={`${a.code} - ${a.name}`}>{a.code} - {a.name}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
          </div>
          <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:12,flexWrap:"wrap"}}>
            <label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer",fontSize:13,color:C.ink}}>
              <input type="checkbox" checked={form.vatApplicable} onChange={e=>setForm({...form,vatApplicable:e.target.checked})} style={{width:16,height:16,cursor:"pointer"}}/>
              Apply VAT @ 15%
            </label>
            <label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer",fontSize:13,color:C.ink}}>
              <input type="checkbox" checked={form.onCredit||false} onChange={e=>setForm({...form,onCredit:e.target.checked})} style={{width:16,height:16,cursor:"pointer"}}/>
              On Credit
            </label>
            {form.onCredit && (
              <span style={{fontSize:11,color:C.inkMid,background:C.surface,border:`1px solid ${C.border}`,borderRadius:6,padding:"3px 8px"}}>
                Posts to Accounts Payable — record payment separately when cash leaves the bank
              </span>
            )}
            {form.amount && (
              <div style={{marginLeft:"auto",display:"flex",gap:16,fontSize:12}}>
                <span style={{color:C.inkMid}}>Excl. VAT: <strong style={{color:C.ink}}>{fmt(+form.amount||0)}</strong></span>
                {form.vatApplicable && <span style={{color:C.inkMid}}>VAT: <strong style={{color:C.gold}}>{fmt((+form.amount||0)*0.15)}</strong></span>}
                <span style={{color:C.inkMid}}>Total: <strong style={{color:C.red}}>{fmt((+form.amount||0)*(form.vatApplicable?1.15:1))}</strong></span>
              </div>
            )}
          </div>
          <div style={{display:"flex",gap:8}}>
            <button onClick={handleAdd} disabled={saving} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>{saving?"Saving...":"Add Expense"}</button>
            <button onClick={() => setShowNew(false)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
          </div>
        </div>
      )}

      {/* View Expense Modal */}
      {viewExp && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center"}} onClick={() => setViewExp(null)}>
          <div style={{background:C.surface,borderRadius:20,padding:32,width:480}} onClick={e=>e.stopPropagation()}>
            <h3 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:"0 0 20px"}}>Expense — {viewExp.id}</h3>
            {[["Vendor",viewExp.vendor],["Description",viewExp.desc],["Date",fmtDate(viewExp.date)],["Amount (excl. VAT)",fmt((viewExp.amount||0)-(viewExp.vat_amount||0))],["VAT",fmt(viewExp.vat_amount||0)],["Total (incl. VAT)",fmt(viewExp.amount||0)],["Account",viewExp.category||"Uncategorised"]].map(([l,v])=>(
              <div key={l} style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:`1px solid ${C.border}30`,fontSize:13}}>
                <span style={{color:C.inkMid,fontWeight:600}}>{l}</span>
                <span style={{color:C.ink,fontWeight:l==="Amount"?700:400}}>{v}</span>
              </div>
            ))}
            <div style={{display:"flex",gap:8,marginTop:20}}>
              <button onClick={() => { setViewExp(null); setEditExp({...viewExp}); }} style={{flex:1,background:C.goldLt,color:C.gold,border:`1px solid ${C.gold}40`,borderRadius:10,padding:"10px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Amend</button>
              <button onClick={() => setViewExp(null)} style={{flex:1,background:"transparent",border:`1px solid ${C.border}`,borderRadius:10,padding:"10px",fontSize:13,cursor:"pointer",fontFamily:"inherit",color:C.inkMid}}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Amend Expense Modal */}
      {editExp && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center",padding:20}} onClick={() => setEditExp(null)}>
          <div style={{background:C.surface,borderRadius:20,padding:32,width:520}} onClick={e=>e.stopPropagation()}>
            <h3 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:"0 0 20px"}}>Amend Expense — {editExp.id}</h3>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
              {[{l:"Vendor",k:"vendor",t:"text"},{l:"Amount (ZAR)",k:"amount",t:"number"},{l:"Description",k:"desc",t:"text"},{l:"Date",k:"date",t:"date"}].map(f=>(
                <div key={f.k}>
                  <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                  <input type={f.t} value={editExp[f.k]||""} onChange={e=>setEditExp({...editExp,[f.k]:e.target.value})} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
                </div>
              ))}
            </div>
            <div style={{marginBottom:16}}>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Account</label>
              <select value={editExp.category||""} onChange={e=>setEditExp({...editExp,category:e.target.value})} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                <option value="">-- Uncategorised --</option>
                {EXPENSE_COA_GROUPS.map(group=>(
                  <optgroup key={group} label={group}>
                    {DEFAULT_COA.filter(a=>a.group===group&&a.type==="Detail").map(a=>(
                      <option key={a.code} value={`${a.code} - ${a.name}`}>{a.code} - {a.name}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
            <div style={{display:"flex",gap:8}}>
              <button onClick={handleAmendExp} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 24px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Save Changes</button>
              <button onClick={() => setEditExp(null)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Auto-categorise notice */}
      {autoNotice && (
        <div style={{background:C.greenLt,border:`1px solid ${C.green}40`,borderRadius:10,padding:"10px 16px",marginBottom:14,fontSize:13,color:C.green,display:"flex",alignItems:"center",gap:8}}>
          <span>✨</span> {autoNotice}
        </div>
      )}

      {/* View toggle */}
      <div style={{display:"flex",gap:8,marginBottom:16,alignItems:"center"}}>
        {[["unposted","⏳ Needs Categorising"],["posted","✅ Posted to Accounts"]].map(([v,l]) => (
          <button key={v} onClick={()=>setView(v)} style={{padding:"7px 16px",borderRadius:20,border:`1px solid ${view===v?C.accent:C.border}`,background:view===v?C.accentLt:"transparent",color:view===v?C.accent:C.inkMid,fontSize:12,fontWeight:view===v?700:400,cursor:"pointer",fontFamily:"inherit"}}>{l}</button>
        ))}
        <div style={{marginLeft:"auto",fontSize:13,fontWeight:700,color:C.ink}}>Total: {fmt(total)}</div>
      </div>

      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
        {displayed.length === 0 ? (
          <div style={{padding:40,textAlign:"center",color:C.inkMid,fontSize:13}}>
            {view==="unposted" ? "All expenses have been categorised." : "No posted expenses yet."}
          </div>
        ) : (
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
            <thead>
              <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                {["#","Vendor","Description","Date","Amount", view==="unposted"?"Assign Account":"Account","Actions"].map(h => <th key={h} style={{textAlign:"left",padding:"12px 16px",fontSize:10,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {displayed.map((exp) => (
                <tr key={exp.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                  <td style={{padding:"13px 16px",fontWeight:600,color:C.inkMid,fontSize:11}}>{exp.id}</td>
                  <td style={{padding:"13px 16px",fontWeight:600}}>{exp.vendor}</td>
                  <td style={{padding:"13px 16px",color:C.inkMid,fontSize:12}}>{exp.desc}</td>
                  <td style={{padding:"13px 16px",color:C.inkMid}}>{fmtDate(exp.date)}</td>
                  <td style={{padding:"13px 16px",fontWeight:700,color:C.red}}>{fmt((exp.amount||0)-(exp.vat_amount||0))}</td>
                  <td style={{padding:"13px 16px"}}>
                    {view === "unposted" ? (
                      <select value={pendingCats[exp.id] || ""} onChange={e => setPendingCats(p=>({...p,[exp.id]:e.target.value}))}
                        style={{padding:"5px 8px",border:`1px solid ${C.border}`,borderRadius:6,fontSize:11,fontFamily:"inherit",background:C.bg,color:C.ink,maxWidth:220}}>
                        <option value="">-- Select Account --</option>
                        {EXPENSE_COA_GROUPS.map(group => (
                          <optgroup key={group} label={group}>
                            {DEFAULT_COA.filter(a => a.group === group && a.type === "Detail").map(a => (
                              <option key={a.code} value={`${a.code} - ${a.name}`}>{a.code} - {a.name}</option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    ) : (
                      <Badge label={exp.category} color={C.green} bg={C.greenLt}/>
                    )}
                  </td>
                  <td style={{padding:"13px 16px"}}>
                    <div style={{display:"flex",gap:6}}>
                      <button onClick={() => setViewExp(exp)} style={{background:C.blueLt,color:C.blue,border:"none",borderRadius:6,padding:"5px 10px",fontSize:11,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>View</button>
                      <button onClick={() => setEditExp({...exp})} style={{background:C.goldLt,color:C.gold,border:"none",borderRadius:6,padding:"5px 10px",fontSize:11,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Amend</button>
                      {view === "unposted" && (
                        <button onClick={() => handlePost(exp)}
                          disabled={!isPosted(pendingCats[exp.id])}
                          style={{background:isPosted(pendingCats[exp.id])?C.green:"transparent",color:isPosted(pendingCats[exp.id])?"#fff":C.inkDim,border:`1px solid ${isPosted(pendingCats[exp.id])?C.green:C.border}`,borderRadius:6,padding:"5px 10px",fontSize:11,cursor:isPosted(pendingCats[exp.id])?"pointer":"default",fontFamily:"inherit",fontWeight:700}}>
                          Post →
                        </button>
                      )}
                      <button onClick={async()=>{ if(!window.confirm(`Delete ${exp.id}?`))return; setExpenses(p=>p.filter(e=>e.id!==exp.id)); try{await api(`/expenses/${exp.id}`,{method:"DELETE"});}catch(e){} }} style={{background:C.redLt,color:C.red,border:"none",borderRadius:6,padding:"5px 10px",fontSize:11,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}


// ── PAYSLIP MODAL ─────────────────────────────────────────────────────────────
function PayslipModal({employee, payroll, period, company, logoUrl, onClose}) {
  const p = payroll;
  const today = new Date().toLocaleDateString("en-ZA", {day:"2-digit", month:"long", year:"numeric"});

  const handlePrint = () => {
    const printContent = document.getElementById("payslip-content").innerHTML;
    const win = window.open("", "_blank");
    if (!win) {
      alert("Please allow popups for this site to print payslips.");
      return;
    }
    win.document.write(`
      <html><head><title>Payslip - ${employee.name}</title>
      <style>
        body { font-family: Arial, sans-serif; padding: 40px; color: #1A1209; }
        .header { display: flex; justify-content: space-between; margin-bottom: 30px; border-bottom: 2px solid #C8401A; padding-bottom: 16px; }
        .logo { font-size: 28px; font-weight: 800; color: #C8401A; }
        .title { font-size: 20px; font-weight: 700; text-align: right; }
        .section { margin-bottom: 20px; }
        .section-title { font-size: 11px; font-weight: 700; color: #6B5E4E; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; border-bottom: 1px solid #E8E0D5; padding-bottom: 4px; }
        .row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 13px; border-bottom: 1px solid #f0ebe3; }
        .row.total { font-weight: 800; font-size: 15px; border-top: 2px solid #1A1209; border-bottom: none; margin-top: 8px; padding-top: 10px; }
        .green { color: #2A6B3C; }
        .red { color: #C82A2A; }
        .blue { color: #1A3A6B; }
        .footer { margin-top: 40px; font-size: 11px; color: #B5A898; border-top: 1px solid #E8E0D5; padding-top: 16px; }
        @media print { body { padding: 20px; } }
      </style></head><body>${printContent}</body></html>
    `);
    win.document.close();
    win.onload = () => {
      win.focus();
      win.print();
      win.close();
    };
  };

  return (
    <div style={{position:"fixed",inset:0,background:"#00000070",zIndex:200,display:"flex",alignItems:"center",justifyContent:"center",padding:20}} onClick={onClose}>
      <div style={{background:"#fff",borderRadius:20,width:600,maxHeight:"90vh",overflow:"auto",boxShadow:"0 20px 60px rgba(0,0,0,0.3)"}} onClick={e=>e.stopPropagation()}>

        {/* Actions bar */}
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"16px 24px",borderBottom:`1px solid ${C.border}`,position:"sticky",top:0,background:"#fff",zIndex:10}}>
          <span style={{fontSize:14,fontWeight:700,color:C.ink}}>Payslip — {employee.name}</span>
          <div style={{display:"flex",gap:8}}>
            <button onClick={handlePrint} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"8px 18px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>🖨️ Print / PDF</button>
            <button onClick={onClose} style={{background:C.bg,color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:8,padding:"8px 16px",fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>Close</button>
          </div>
        </div>

        {/* Payslip content */}
        <div id="payslip-content" style={{padding:"32px 40px"}}>

          {/* Header */}
          <div style={{display:"flex",justifyContent:"space-between",marginBottom:28,paddingBottom:16,borderBottom:`2px solid ${C.accent}`}}>
            <div>
              {logoUrl
                ? <img src={logoUrl} alt="logo" style={{height:56,maxWidth:180,objectFit:"contain",display:"block",marginBottom:4}}/>
                : <div style={{fontFamily:"serif",fontSize:24,fontWeight:800,color:C.accent}}>{company||"Your Company"}</div>}
              {logoUrl && <div style={{fontSize:12,fontWeight:700,color:C.ink}}>{company||""}</div>}
            </div>
            <div style={{textAlign:"right"}}>
              <div style={{fontSize:18,fontWeight:800,color:C.ink}}>PAYSLIP</div>
              <div style={{fontSize:12,color:C.inkMid,marginTop:4}}>Period: {period || "Current Month"}</div>
              <div style={{fontSize:12,color:C.inkMid}}>Date: {today}</div>
            </div>
          </div>

          {/* Employee details */}
          <div style={{background:C.bg,borderRadius:12,padding:"16px 20px",marginBottom:24}}>
            <div style={{fontSize:11,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:12}}>Employee Details</div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
              {[
                ["Employee Name", employee.name],
                ["Employee ID",   employee.employee_number || employee.id || "EMP-001"],
                ["Position",      employee.position || "Staff"],
                ["Department",    employee.dept || "General"],
                ...(employee.grade ? [["Grade / Pay Band", employee.grade]] : []),
                ...(employee.employment_type ? [["Employment Type", employee.employment_type === "hourly" ? "Hourly" : "Salaried"]] : []),
              ].map(([l,v]) => (
                <div key={l}>
                  <div style={{fontSize:10,color:C.inkMid,marginBottom:2}}>{l}</div>
                  <div style={{fontSize:13,fontWeight:600,color:C.ink}}>{v}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Earnings */}
          <div style={{marginBottom:20}}>
            <div style={{fontSize:11,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:10,borderBottom:`1px solid ${C.border}`,paddingBottom:4}}>Earnings</div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"8px 0",fontSize:13,borderBottom:`1px solid ${C.border}30`}}>
              <span style={{color:C.inkMid}}>Basic Salary</span>
              <span style={{fontWeight:600,color:C.green}}>{fmt(p.gross)}</span>
            </div>
            {p.overtime && p.overtime.total > 0 && (
              <>
                {p.overtime.overtime_amount > 0 && (
                  <div style={{display:"flex",justifyContent:"space-between",padding:"8px 0",fontSize:13,borderBottom:`1px solid ${C.border}30`}}>
                    <span style={{color:C.inkMid}}>Weekday/Sat Overtime ({p.overtime.overtime_hours}h × 1.5×)</span>
                    <span style={{fontWeight:600,color:C.green}}>{fmt(p.overtime.overtime_amount)}</span>
                  </div>
                )}
                {p.overtime.sunday_amount > 0 && (
                  <div style={{display:"flex",justifyContent:"space-between",padding:"8px 0",fontSize:13,borderBottom:`1px solid ${C.border}30`}}>
                    <span style={{color:C.inkMid}}>Sunday Time ({p.overtime.sunday_hours}h × 2×)</span>
                    <span style={{fontWeight:600,color:C.green}}>{fmt(p.overtime.sunday_amount)}</span>
                  </div>
                )}
                {p.overtime.ph_amount > 0 && (
                  <div style={{display:"flex",justifyContent:"space-between",padding:"8px 0",fontSize:13,borderBottom:`1px solid ${C.border}30`}}>
                    <span style={{color:C.inkMid}}>Public Holiday ({p.overtime.ph_hours}h × 2×)</span>
                    <span style={{fontWeight:600,color:C.green}}>{fmt(p.overtime.ph_amount)}</span>
                  </div>
                )}
                <div style={{display:"flex",justifyContent:"space-between",padding:"8px 0",fontSize:13,borderBottom:`1px solid ${C.border}30`,fontWeight:700}}>
                  <span style={{color:C.inkMid}}>Taxable Gross (incl. OT)</span>
                  <span style={{color:C.green}}>{fmt(p.taxableGross || p.gross)}</span>
                </div>
              </>
            )}
          </div>

          {/* Deductions */}
          <div style={{marginBottom:20}}>
            <div style={{fontSize:11,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:10,borderBottom:`1px solid ${C.border}`,paddingBottom:4}}>Deductions</div>
            {[
              ["PAYE (Income Tax)",     p.paye,        C.red],
              ["UIF (Employee Contribution)", p.uifEmployee, C.gold],
            ].map(([l,v,c]) => (
              <div key={l} style={{display:"flex",justifyContent:"space-between",padding:"8px 0",fontSize:13,borderBottom:`1px solid ${C.border}30`}}>
                <span style={{color:C.inkMid}}>{l}</span>
                <span style={{fontWeight:600,color:c}}>({fmt(v)})</span>
              </div>
            ))}
            <div style={{display:"flex",justifyContent:"space-between",padding:"10px 0",fontSize:14,fontWeight:800,borderTop:`2px solid ${C.border}`,marginTop:8}}>
              <span>Total Deductions</span>
              <span style={{color:C.red}}>({fmt(p.paye + p.uifEmployee)})</span>
            </div>
          </div>

          {/* Net Pay */}
          <div style={{background:`linear-gradient(135deg,${C.greenLt},transparent)`,border:`2px solid ${C.green}`,borderRadius:12,padding:"16px 20px",marginBottom:24}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <div>
                <div style={{fontSize:12,color:C.inkMid,marginBottom:4}}>NET PAY THIS PERIOD</div>
                <div style={{fontSize:11,color:C.inkDim}}>Amount payable to employee</div>
              </div>
              <div style={{fontFamily:"serif",fontSize:32,fontWeight:800,color:C.green}}>{fmt(p.netPay)}</div>
            </div>
          </div>

          {/* Employer contributions */}
          <div style={{marginBottom:20}}>
            <div style={{fontSize:11,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:10,borderBottom:`1px solid ${C.border}`,paddingBottom:4}}>Employer Contributions (for info)</div>
            {[
              ["UIF (Employer Contribution)", p.uifEmployer, C.blue],
              ["SDL (Skills Development Levy)", p.sdl,        C.blue],
            ].map(([l,v,c]) => (
              <div key={l} style={{display:"flex",justifyContent:"space-between",padding:"8px 0",fontSize:13,borderBottom:`1px solid ${C.border}30`}}>
                <span style={{color:C.inkMid}}>{l}</span>
                <span style={{fontWeight:600,color:c}}>{fmt(v)}</span>
              </div>
            ))}
            <div style={{display:"flex",justifyContent:"space-between",padding:"10px 0",fontSize:13,fontWeight:700,borderTop:`1px solid ${C.border}`,marginTop:4}}>
              <span style={{color:C.inkMid}}>Total Employer Cost</span>
              <span style={{color:C.accent}}>{fmt(p.totalCost)}</span>
            </div>
          </div>

          {/* SARS info */}
          <div style={{background:C.bg,borderRadius:10,padding:"12px 16px",fontSize:11,color:C.inkMid,lineHeight:1.8}}>
            <strong style={{color:C.ink}}>SARS Reference (2026/2027)</strong><br/>
            PAYE calculated on annualised taxable gross of {fmt((p.taxableGross||p.gross) * 12)} — Primary rebate R17,820/year<br/>
            UIF: 1% employee + 1% employer — capped at R17,712/month (on basic salary only)<br/>
            SDL: 1% of taxable gross payroll<br/>
            {p.overtime && p.overtime.total > 0 && `BCEA Overtime: Weekday/Sat 1.5× · Sunday 2× · Public Holiday 2× · Hourly rate: ${fmt(p.overtime.hourly_rate||p.overtime.hourlyRate)}/hr`}
          </div>

        </div>
      </div>
    </div>
  );
}

// ── BATCH PAYMENT HELPERS ─────────────────────────────────────────────────────
const SARS_BANKING = { bank:"ABSA", branch:"632005", account:"4048718850", type:"Cheque" };
const ACCOUNT_TYPE_CODE = { Cheque:"1", Savings:"2", Transmission:"3" };
const payDate = () => { const d = new Date(); d.setDate(d.getDate()+1); return d.toISOString().slice(0,10).replace(/-/g,""); };

function downloadCSV(filename, content) {
  const blob = new Blob([content], {type:"text/plain"});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url; a.download = filename.replace(".csv",".txt"); a.click();
  URL.revokeObjectURL(url);
}

// Generic EFT format — accepted by FNB, Standard Bank, Nedbank, Capitec, TymeBank
function buildGenericEFT(rows) {
  const header = "Action,BranchCode,AccountNumber,AccountType,AccountName,Amount,OwnReference,BeneficiaryReference";
  const lines  = rows.map(r =>
    `CREDIT,${r.branch},${r.account},${ACCOUNT_TYPE_CODE[r.type]||"1"},"${r.name}",${r.amount.toFixed(2)},"${r.ownRef}","${r.benRef}"`
  );
  return [header, ...lines].join("\r\n");
}

// ABSA-specific format
function buildABSA(rows) {
  const header = "RecordIdentifier,DestinationBranch,DestinationAccount,AccountType,DestinationName,Amount,ActionDate,OwnStatement,DestinationStatement";
  const lines  = rows.map(r =>
    `10,${r.branch},${r.account},${ACCOUNT_TYPE_CODE[r.type]||"1"},"${r.name}",${Math.round(r.amount*100)},${payDate()},"${r.ownRef}","${r.benRef}"`
  );
  return [header, ...lines].join("\r\n");
}

// FNB-specific format (Pay & Clear)
function buildFNB(rows) {
  const header = "TransactionType,BranchCode,AccountNumber,AccountType,AccountName,Amount,Reference";
  const lines  = rows.map(r =>
    `EFT,${r.branch},${r.account},${ACCOUNT_TYPE_CODE[r.type]||"1"},"${r.name}",${r.amount.toFixed(2)},"${r.benRef}"`
  );
  return [header, ...lines].join("\r\n");
}

// Standard Bank format
function buildStdBank(rows) {
  const header = "SequenceNo,BranchCode,AccountNo,AccountType,BeneficiaryName,Amount,OurRef,TheirRef,Email";
  const lines  = rows.map((r,i) =>
    `${i+1},${r.branch},${r.account},${ACCOUNT_TYPE_CODE[r.type]||"1"},"${r.name}",${r.amount.toFixed(2)},"${r.ownRef}","${r.benRef}",""`
  );
  return [header, ...lines].join("\r\n");
}

function BatchPaymentModal({employees, payroll, period, onClose}) {
  const periodStr = period || new Date().toLocaleDateString("en-ZA",{month:"long",year:"numeric"});
  const totalPAYE = employees.reduce((s,e) => s + calcPayroll(e.salary).paye, 0);
  const totalUIF  = employees.reduce((s,e) => s + calcPayroll(e.salary).uifEmployee + calcPayroll(e.salary).uifEmployer, 0);
  const totalSDL  = employees.reduce((s,e) => s + calcPayroll(e.salary).sdl, 0);
  const sarsTotal = totalPAYE + totalUIF + totalSDL;

  const empRows = employees.map(e => {
    const p = calcPayroll(e.salary);
    return {
      branch:  e.branchCode  || "250655",
      account: e.accountNumber || "000000000",
      type:    e.accountType  || "Cheque",
      name:    e.name,
      amount:  p.netPay,
      ownRef:  `SALARY ${periodStr}`,
      benRef:  `SALARY ${periodStr}`,
    };
  });

  const sarsRow = [{
    branch:  SARS_BANKING.branch,
    account: SARS_BANKING.account,
    type:    SARS_BANKING.type,
    name:    "SARS",
    amount:  sarsTotal,
    ownRef:  `EMP201 ${periodStr}`,
    benRef:  `EMP201 ${periodStr}`,
  }];

  const FORMATS = [
    { label:"Generic EFT (FNB / Nedbank / Capitec / TymeBank / Discovery / Investec)", icon:"🏦", color:C.blue,
      dlSalary: () => downloadCSV(`salary-eft-${periodStr}.csv`,   buildGenericEFT(empRows)),
      dlSars:   () => downloadCSV(`sars-eft-${periodStr}.csv`,     buildGenericEFT(sarsRow)) },
    { label:"ABSA Batch Payment", icon:"🔴", color:"#B11116",
      dlSalary: () => downloadCSV(`salary-absa-${periodStr}.csv`,  buildABSA(empRows)),
      dlSars:   () => downloadCSV(`sars-absa-${periodStr}.csv`,    buildABSA(sarsRow)) },
    { label:"FNB Pay & Clear",    icon:"🟢", color:"#007A39",
      dlSalary: () => downloadCSV(`salary-fnb-${periodStr}.csv`,   buildFNB(empRows)),
      dlSars:   () => downloadCSV(`sars-fnb-${periodStr}.csv`,     buildFNB(sarsRow)) },
    { label:"Standard Bank",      icon:"🔵", color:"#0033A0",
      dlSalary: () => downloadCSV(`salary-std-${periodStr}.csv`,   buildStdBank(empRows)),
      dlSars:   () => downloadCSV(`sars-std-${periodStr}.csv`,     buildStdBank(sarsRow)) },
  ];

  return (
    <div style={{position:"fixed",inset:0,background:"#00000070",zIndex:200,display:"flex",alignItems:"center",justifyContent:"center",padding:20}} onClick={onClose}>
      <div style={{background:C.surface,borderRadius:20,width:660,maxHeight:"90vh",overflow:"auto",boxShadow:"0 20px 60px rgba(0,0,0,0.3)"}} onClick={e=>e.stopPropagation()}>
        <div style={{padding:"20px 28px",borderBottom:`1px solid ${C.border}`,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
          <div>
            <div style={{fontSize:16,fontWeight:800,color:C.ink}}>Batch Payment Files</div>
            <div style={{fontSize:12,color:C.inkMid,marginTop:2}}>{periodStr} — download and import into your bank</div>
          </div>
          <button onClick={onClose} style={{background:C.bg,border:`1px solid ${C.border}`,borderRadius:8,padding:"7px 14px",fontSize:12,cursor:"pointer",fontFamily:"inherit",color:C.inkMid}}>Close</button>
        </div>

        {/* Summary */}
        <div style={{padding:"16px 28px",background:C.bg,borderBottom:`1px solid ${C.border}`,display:"flex",gap:20}}>
          {[
            ["Salary Payments", fmt(empRows.reduce((s,r)=>s+r.amount,0)), `${employees.length} employees`, C.green],
            ["PAYE",  fmt(totalPAYE), "To SARS", C.red],
            ["UIF",   fmt(totalUIF),  "To SARS", C.gold],
            ["SDL",   fmt(totalSDL),  "To SARS", C.blue],
            ["SARS Total", fmt(sarsTotal), "EMP201", C.red],
          ].map(([l,v,s,c])=>(
            <div key={l} style={{flex:1}}>
              <div style={{fontSize:10,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:3}}>{l}</div>
              <div style={{fontSize:15,fontWeight:800,color:c}}>{v}</div>
              <div style={{fontSize:10,color:C.inkDim}}>{s}</div>
            </div>
          ))}
        </div>

        {/* Format rows */}
        <div style={{padding:"20px 28px"}}>
          <div style={{fontSize:11,fontWeight:700,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:14}}>Select your bank format</div>
          {FORMATS.map((f,i)=>(
            <div key={i} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"14px 16px",borderRadius:12,border:`1px solid ${C.border}`,marginBottom:10,background:C.bg}}>
              <div style={{display:"flex",alignItems:"center",gap:12}}>
                <span style={{fontSize:22}}>{f.icon}</span>
                <span style={{fontSize:13,fontWeight:600,color:C.ink}}>{f.label}</span>
              </div>
              <div style={{display:"flex",gap:8}}>
                <button onClick={f.dlSalary} style={{background:C.greenLt,color:C.green,border:`1px solid ${C.green}30`,borderRadius:8,padding:"7px 14px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>⬇ Salary EFT</button>
                <button onClick={f.dlSars}   style={{background:C.redLt,  color:C.red,  border:`1px solid ${C.red}30`,  borderRadius:8,padding:"7px 14px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>⬇ SARS EMP201</button>
              </div>
            </div>
          ))}
          <div style={{background:C.goldLt,border:`1px solid ${C.gold}40`,borderRadius:10,padding:"12px 16px",marginTop:8,fontSize:12,color:C.inkMid,lineHeight:1.7}}>
            <strong style={{color:C.ink}}>How to import:</strong> Log in to your bank's business banking portal → Payments → Batch Payments / EFT → Import File → select the downloaded CSV. SARS EMP201 payment due by the 7th of each month.
          </div>
        </div>
      </div>
    </div>
  );
}

// ── PAYROLL ───────────────────────────────────────────────────────────────────
// ── LEAVE MANAGEMENT ─────────────────────────────────────────────────────────
function LeaveManagement({employees = []}) {
  const [balances,  setBalances]  = useState([]);
  const [requests,  setRequests]  = useState([]);
  const [loadingBal, setLoadingBal] = useState(false);
  const [loadingReq, setLoadingReq] = useState(false);
  const [leaveSection, setLeaveSection] = useState("requests"); // requests | balances | submit
  const [submitForm, setSubmitForm] = useState({employee_id:"",leave_type:"annual",start_date:"",end_date:"",reason:""});
  const [submitMsg, setSubmitMsg]   = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const fetchAll = async () => {
    setLoadingBal(true); setLoadingReq(true);
    try { const d = await api("/leave/balances"); setBalances(d); } catch(e) { console.warn("leave balances:", e); } finally { setLoadingBal(false); }
    try { const d = await api("/leave/requests"); setRequests(d); } catch(e) { console.warn("leave requests:", e); } finally { setLoadingReq(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  const handleReview = async (reqId, status) => {
    try {
      await api(`/leave/requests/${reqId}`, {method:"PUT", body:JSON.stringify({status})});
      fetchAll();
    } catch(e) { alert("Failed: " + (e.message||"unknown error")); }
  };

  const handleSubmit = async () => {
    if (!submitForm.employee_id || !submitForm.start_date || !submitForm.end_date) {
      setSubmitMsg({type:"error", text:"Employee, start date and end date are required."}); return;
    }
    setSubmitting(true); setSubmitMsg(null);
    try {
      const res = await api("/leave/requests", {method:"POST", body:JSON.stringify({
        employee_id: +submitForm.employee_id,
        leave_type:  submitForm.leave_type,
        start_date:  submitForm.start_date,
        end_date:    submitForm.end_date,
        reason:      submitForm.reason || undefined,
      })});
      setSubmitMsg({type:"ok", text: res.message || "Leave request submitted."});
      setSubmitForm({employee_id:"",leave_type:"annual",start_date:"",end_date:"",reason:""});
      fetchAll();
    } catch(e) { setSubmitMsg({type:"error", text: e.message||"Submission failed."}); }
    setSubmitting(false);
  };

  const pending  = requests.filter(r => r.status === "pending").length;
  const approved = requests.filter(r => r.status === "approved").length;

  const statusColor = s => s === "approved" ? C.green : s === "pending" ? C.gold : s === "rejected" ? C.red : C.inkMid;
  const statusBg    = s => s === "approved" ? C.greenLt : s === "pending" ? C.goldLt : s === "rejected" ? C.redLt : C.bg;

  const tabs = [{id:"requests",label:"Requests"},{id:"balances",label:"Leave Balances"},{id:"submit",label:"Submit Leave"}];

  return (
    <div>
      <div style={{marginBottom:20}}>
        <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:"0 0 4px"}}>Leave Management</h2>
        <p style={{fontSize:12,color:C.inkMid,margin:0}}>BCEA-compliant leave tracking — annual (15 days), sick (30/3yr), family responsibility (3 days)</p>
      </div>

      {/* KPI cards */}
      <div style={{display:"flex",gap:12,marginBottom:20,flexWrap:"wrap"}}>
        <KPI label="Pending Requests"  value={pending}  color={C.gold}  icon="⏳"/>
        <KPI label="Approved (all)"    value={approved} color={C.green} icon="✅"/>
        <KPI label="Total Employees"   value={balances.length} color={C.accent} icon="👥"/>
        <KPI label="Auto-approve in"   value="48 hrs"   color={C.blue}  icon="🕐"/>
      </div>

      {/* Sub-section tabs */}
      <div style={{display:"flex",gap:4,marginBottom:20,borderBottom:`1px solid ${C.border}`,paddingBottom:0}}>
        {tabs.map(t => (
          <button key={t.id} onClick={()=>setLeaveSection(t.id)} style={{background:"none",border:"none",borderBottom: leaveSection===t.id ? `2px solid ${C.accent}` : "2px solid transparent",padding:"8px 18px",fontSize:13,fontWeight:leaveSection===t.id?700:400,color:leaveSection===t.id?C.accent:C.inkMid,cursor:"pointer",fontFamily:"inherit",marginBottom:"-1px"}}>
            {t.label}
          </button>
        ))}
        <button onClick={fetchAll} style={{marginLeft:"auto",background:"none",border:`1px solid ${C.border}`,borderRadius:8,padding:"6px 14px",fontSize:12,color:C.inkMid,cursor:"pointer",fontFamily:"inherit"}}>↺ Refresh</button>
      </div>

      {/* ── REQUESTS TAB ── */}
      {leaveSection === "requests" && (
        <div>
          {loadingReq ? <div style={{color:C.inkMid,fontSize:13,padding:20}}>Loading...</div> : requests.length === 0 ? (
            <div style={{color:C.inkMid,fontSize:13,padding:20,textAlign:"center"}}>No leave requests yet.</div>
          ) : (
            <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                <thead>
                  <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                    {["Employee","Type","Dates","Days","Status","Reason","Action"].map(h=>(
                      <th key={h} style={{textAlign:"left",padding:"11px 14px",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {requests.map(r => (
                    <tr key={r.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                      <td style={{padding:"12px 14px",fontWeight:600,color:C.ink}}>{r.employee_name}</td>
                      <td style={{padding:"12px 14px",textTransform:"capitalize"}}>{r.leave_type}</td>
                      <td style={{padding:"12px 14px",color:C.inkMid,whiteSpace:"nowrap"}}>{r.start_date} → {r.end_date}</td>
                      <td style={{padding:"12px 14px",fontWeight:700}}>{r.days_requested}</td>
                      <td style={{padding:"12px 14px"}}>
                        <span style={{background:statusBg(r.status),color:statusColor(r.status),borderRadius:6,padding:"3px 10px",fontSize:11,fontWeight:700,textTransform:"capitalize"}}>
                          {r.auto_approved ? "Auto-approved" : r.status}
                        </span>
                      </td>
                      <td style={{padding:"12px 14px",color:C.inkMid,maxWidth:160,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{r.reason||"—"}</td>
                      <td style={{padding:"12px 14px"}}>
                        {r.status === "pending" ? (
                          <div style={{display:"flex",gap:6}}>
                            <button onClick={()=>handleReview(r.id,"approved")} style={{background:C.greenLt,color:C.green,border:"none",borderRadius:6,padding:"5px 10px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:700}}>Approve</button>
                            <button onClick={()=>handleReview(r.id,"rejected")} style={{background:C.redLt,color:C.red,border:"none",borderRadius:6,padding:"5px 10px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:700}}>Reject</button>
                          </div>
                        ) : <span style={{color:C.inkMid,fontSize:11}}>{r.reviewed_by||"—"}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── BALANCES TAB ── */}
      {leaveSection === "balances" && (
        <div>
          {loadingBal ? <div style={{color:C.inkMid,fontSize:13,padding:20}}>Loading...</div> : balances.length === 0 ? (
            <div style={{color:C.inkMid,fontSize:13,padding:20,textAlign:"center"}}>No active employees found.</div>
          ) : (
            <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                <thead>
                  <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                    {["Employee","Position","Annual Balance","Annual Taken","Sick Balance","Sick Taken","Family Balance","Last Accrual"].map(h=>(
                      <th key={h} style={{textAlign:"left",padding:"11px 14px",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {balances.map(b => (
                    <tr key={b.employee_id} style={{borderBottom:`1px solid ${C.border}30`}}>
                      <td style={{padding:"12px 14px",fontWeight:600,color:C.ink}}>{b.employee_name}</td>
                      <td style={{padding:"12px 14px",color:C.inkMid}}>{b.position||"—"}</td>
                      <td style={{padding:"12px 14px"}}>
                        <span style={{fontWeight:700,color:b.annual_balance<3?C.red:C.green}}>{b.annual_balance} days</span>
                      </td>
                      <td style={{padding:"12px 14px",color:C.inkMid}}>{b.annual_taken_ytd} days</td>
                      <td style={{padding:"12px 14px"}}>
                        <span style={{fontWeight:700,color:b.sick_balance<5?C.gold:C.ink}}>{b.sick_balance} days</span>
                      </td>
                      <td style={{padding:"12px 14px",color:C.inkMid}}>{b.sick_taken_ytd} days</td>
                      <td style={{padding:"12px 14px",fontWeight:600}}>{b.family_balance} days</td>
                      <td style={{padding:"12px 14px",color:C.inkMid,fontSize:11}}>{b.last_accrual_date||"Never"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div style={{marginTop:12,padding:"12px 16px",background:C.accentLt,border:`1px solid ${C.accent}30`,borderRadius:10,fontSize:12,color:C.inkMid}}>
            <strong style={{color:C.accent}}>Accrual note:</strong> Annual leave accrues at +1.25 days/month automatically when payroll is run. Maximum carry-over: 30 days.
          </div>
        </div>
      )}

      {/* ── SUBMIT LEAVE TAB ── */}
      {leaveSection === "submit" && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:28,maxWidth:560}}>
          <h3 style={{fontFamily:"serif",fontSize:20,margin:"0 0 20px",color:C.ink}}>Submit Leave Request</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:14}}>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Employee</label>
              <select value={submitForm.employee_id} onChange={e=>setSubmitForm(v=>({...v,employee_id:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                <option value="">-- Select Employee --</option>
                {employees.map(emp=><option key={emp.id||emp.employee_id} value={emp.id||emp.employee_id}>{emp.name||emp.first_name+" "+emp.last_name}</option>)}
              </select>
            </div>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Leave Type</label>
              <select value={submitForm.leave_type} onChange={e=>setSubmitForm(v=>({...v,leave_type:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                <option value="annual">Annual Leave</option>
                <option value="sick">Sick Leave</option>
                <option value="family">Family Responsibility</option>
                <option value="maternity">Maternity Leave</option>
                <option value="unpaid">Unpaid Leave</option>
              </select>
            </div>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Start Date</label>
              <input type="date" value={submitForm.start_date} onChange={e=>setSubmitForm(v=>({...v,start_date:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
            </div>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>End Date</label>
              <input type="date" value={submitForm.end_date} onChange={e=>setSubmitForm(v=>({...v,end_date:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
            </div>
            <div style={{gridColumn:"1 / -1"}}>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Reason (optional)</label>
              <input placeholder="e.g. Scheduled medical appointment" value={submitForm.reason} onChange={e=>setSubmitForm(v=>({...v,reason:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
            </div>
          </div>
          {submitMsg && (
            <div style={{background:submitMsg.type==="ok"?C.greenLt:C.redLt,border:`1px solid ${submitMsg.type==="ok"?C.green:C.red}40`,borderRadius:8,padding:"10px 14px",marginBottom:12,fontSize:13,color:submitMsg.type==="ok"?C.green:C.red}}>
              {submitMsg.text}
            </div>
          )}
          <div style={{display:"flex",gap:8}}>
            <button onClick={handleSubmit} disabled={submitting} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 24px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:submitting?0.6:1}}>
              {submitting ? "Submitting..." : "Submit Request"}
            </button>
            <button onClick={()=>setLeaveSection("requests")} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>View Requests</button>
          </div>
          <div style={{marginTop:16,fontSize:11,color:C.inkMid,lineHeight:1.8}}>
            <strong style={{color:C.ink}}>Approval flow:</strong> Requests go to manager for review. If no action is taken within 48 hours, the request is <em>automatically approved</em> and leave is deducted from the employee's balance.
          </div>
        </div>
      )}
    </div>
  );
}

function Payroll({live = {}, user = {}}) {
  const liveEmployees = live.employees;
  const [employees, setEmployees] = useState(MOCK_EMPLOYEES);
  const [taxYear, setTaxYear] = useState(CURRENT_TAX_YEAR);

  // ── Payroll PIN gate ──────────────────────────────────────────────────────
  const [pinOk,     setPinOk]     = useState(false);
  const [pinInput,  setPinInput]  = useState("");
  const [pinSet,    setPinSet]    = useState(null);  // null=loading, true/false
  const [pinError,  setPinError]  = useState("");
  const [pinBusy,   setPinBusy]   = useState(false);
  const [payrollSection, setPayrollSection] = useState("payroll"); // payroll | leave | emp201
  const [emp201Data,    setEmp201Data]    = useState(null);
  const [emp201Loading, setEmp201Loading] = useState(false);
  const [emp201Period,  setEmp201Period]  = useState(new Date().toISOString().slice(0,7));

  useEffect(() => {
    const token = localStorage.getItem("zuzan_token");
    if (!token || token.startsWith("demo_")) { setPinSet(false); return; }
    fetch("https://zuzan-backend.onrender.com/companies/payroll-pin-status", {
      headers: {"Authorization": "Bearer " + token}
    }).then(r => r.json()).then(d => setPinSet(d.pin_set)).catch(() => setPinSet(false));
  }, []);

  const handlePinVerify = async () => {
    if (!pinInput) { setPinError("Enter your PIN."); return; }
    setPinBusy(true); setPinError("");
    try {
      const token = localStorage.getItem("zuzan_token");
      const res = await fetch("https://zuzan-backend.onrender.com/companies/verify-payroll-pin", {
        method: "POST", headers: {"Content-Type":"application/json","Authorization":"Bearer "+token},
        body: JSON.stringify({pin: pinInput})
      });
      const d = await res.json();
      if (d.valid) { setPinOk(true); }
      else { setPinError("Incorrect PIN. Try again."); setPinInput(""); }
    } catch { setPinError("Could not verify PIN. Please try again."); }
    setPinBusy(false);
  };
  // ─────────────────────────────────────────────────────────────────────────

  useEffect(() => { if (liveEmployees && liveEmployees.length > 0) setEmployees(liveEmployees.map(e => ({...e, name: `${e.first_name} ${e.last_name}`, salary: e.gross_salary, dept: e.department || "General"}))); }, [liveEmployees]);
  const [showNew, setShowNew] = useState(false);
  const [payrollRun, setPayrollRun] = useState(false);
  const [showOtModal, setShowOtModal] = useState(false);
  const [otData, setOtData] = useState({});  // {employeeId: {otHours, sunHours, phHours}}
  const [form, setForm] = useState({name:"",position:"",salary:"",dept:"",empNo:"",grade:"",employmentType:"salaried",hourlyRate:"",idNumber:"",taxNumber:"",dob:"",appointmentDate:"",address:"",bankName:"",accountNumber:"",branchCode:"",accountType:"Cheque"});
  const [viewPayslip, setViewPayslip] = useState(null);
  const [showBatch,   setShowBatch]   = useState(false);
  const totalGross = employees.reduce((s,e) => s + e.salary, 0);
  const totalPAYE = employees.reduce((s,e) => s + calcPayroll(e.salary, taxYear).paye, 0);
  const totalNet = employees.reduce((s,e) => s + calcPayroll(e.salary, taxYear).netPay, 0);
  const totalCost = employees.reduce((s,e) => s + calcPayroll(e.salary, taxYear).totalCost, 0);
  const totalUIF = employees.reduce((s,e) => s + calcPayroll(e.salary, taxYear).uifEmployer, 0);
  const totalSDL = employees.reduce((s,e) => s + calcPayroll(e.salary, taxYear).sdl, 0);
  const zuZanFee = Math.max(99, employees.length * 17.50);
  const handleAdd = async () => {
    const nameParts = form.name.trim().split(" ");
    const firstName = nameParts[0] || form.name;
    const lastName  = nameParts.slice(1).join(" ") || "";
    const newEmp = {
      id: form.empNo || `EMP-${String(employees.length+1).padStart(3,"0")}`,
      name:form.name, position:form.position, salary:+form.salary, dept:form.dept,
      idNumber:form.idNumber, taxNumber:form.taxNumber, dob:form.dob,
      appointmentDate:form.appointmentDate, address:form.address,
      bankName:form.bankName, accountNumber:form.accountNumber,
      branchCode:form.branchCode, accountType:form.accountType,
    };
    setEmployees([...employees, newEmp]);
    setShowNew(false);
    setForm({name:"",position:"",salary:"",dept:"",empNo:"",grade:"",employmentType:"salaried",hourlyRate:"",idNumber:"",taxNumber:"",dob:"",appointmentDate:"",address:"",bankName:"",accountNumber:"",branchCode:"",accountType:"Cheque"});
    try {
      const token = localStorage.getItem("zuzan_token");
      if (token && !token.startsWith("demo_")) {
        try { await api("/companies/me", {method:"PUT",body:JSON.stringify({payroll_enabled:true})}); } catch(e) {}
      }
      await api("/employees/", {
        method: "POST",
        body: JSON.stringify({
          first_name:       firstName,
          last_name:        lastName,
          position:         form.position,
          department:       form.dept,
          grade:            form.grade || null,
          employment_type:  form.employmentType || "salaried",
          hourly_rate:      form.hourlyRate ? +form.hourlyRate : null,
          gross_salary:     +form.salary,
          employee_number:  form.empNo,
          id_number:        form.idNumber,
          tax_number:       form.taxNumber,
          date_of_birth:    form.dob || null,
          appointment_date: form.appointmentDate || null,
          address:          form.address,
          bank_name:        form.bankName,
          account_number:   form.accountNumber,
          branch_code:      form.branchCode,
          account_type:     form.accountType,
        }),
      });
      if (live && live.reload) live.reload();
    } catch(err) {
      console.warn("Employee save failed:", err.message);
    }
  };
  // Show PIN gate if not yet verified
  if (!pinOk) {
    return (
      <div style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",minHeight:340,padding:40}}>
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:20,padding:40,width:"100%",maxWidth:380,textAlign:"center",boxShadow:"0 4px 24px #0000000a"}}>
          <div style={{fontSize:36,marginBottom:12}}>🔒</div>
          <h2 style={{fontFamily:"serif",fontSize:24,color:C.ink,margin:"0 0 8px"}}>Payroll is Protected</h2>
          {pinSet === null && <p style={{color:C.inkMid,fontSize:13}}>Checking security settings...</p>}
          {pinSet === false && (
            <div>
              <div style={{background:C.redLt,border:`1px solid ${C.red}40`,borderRadius:10,padding:"12px 16px",marginBottom:16}}>
                <p style={{color:C.red,fontSize:13,margin:0,fontWeight:600}}>No Payroll PIN is set.</p>
                <p style={{color:C.inkMid,fontSize:12,margin:"6px 0 0"}}>A PIN must be configured before payroll data can be accessed. Go to <strong>Settings → Payroll PIN</strong> to set one.</p>
              </div>
            </div>
          )}
          {pinSet === true && (
            <div>
              <p style={{color:C.inkMid,fontSize:13,marginBottom:20}}>Enter your payroll PIN to access salary data.</p>
              <input
                type="password" inputMode="numeric" maxLength={8} placeholder="Enter PIN"
                value={pinInput} onChange={e=>setPinInput(e.target.value.replace(/\D/g,""))}
                onKeyDown={e=>e.key==="Enter"&&handlePinVerify()}
                style={{width:"100%",padding:"12px",border:`1px solid ${pinError?C.red:C.border}`,borderRadius:10,fontSize:20,textAlign:"center",letterSpacing:8,fontFamily:"inherit",outline:"none",boxSizing:"border-box",marginBottom:8}}
                autoFocus
              />
              {pinError && <div style={{color:C.red,fontSize:12,marginBottom:8}}>{pinError}</div>}
              <button onClick={handlePinVerify} disabled={pinBusy} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"11px",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit",width:"100%",opacity:pinBusy?0.6:1}}>
                {pinBusy ? "Verifying..." : "Unlock Payroll"}
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  const SECTION_LABELS = {payroll:"Payroll", leave:"Leave Management", emp201:"EMP201 / IRP5"};
  const SectionTabs = () => (
    <div style={{display:"flex",alignItems:"center",gap:0,marginBottom:24,borderBottom:"1px solid "+C.border}}>
      {["payroll","leave","emp201"].map(s => (
        <button key={s} onClick={()=>setPayrollSection(s)}
          style={{background:"none",border:"none",borderBottom:payrollSection===s?`2px solid ${C.accent}`:"2px solid transparent",padding:"10px 18px",fontSize:13,fontWeight:payrollSection===s?700:400,color:payrollSection===s?C.accent:C.inkMid,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
          {SECTION_LABELS[s]}
        </button>
      ))}
    </div>
  );

  // Leave management sub-tab (accessible after PIN gate)
  if (payrollSection === "leave") {
    return (
      <div>
        <SectionTabs/>
        <LeaveManagement employees={employees} />
      </div>
    );
  }

  // EMP201 / IRP5 sub-tab — confidential, behind PIN gate
  if (payrollSection === "emp201") {
    const loadEmp201 = async () => {
      setEmp201Loading(true);
      try {
        const data = await api(`/reports/emp201?date_from=${emp201Period}-01&date_to=${emp201Period}-28`);
        setEmp201Data(data);
      } catch(err) { setEmp201Data(null); }
      setEmp201Loading(false);
    };
    const e         = emp201Data;
    const nowD      = new Date();
    const totalPaye = e ? e.total_paye : employees.reduce((s,emp)=>s+calcPayroll(emp.salary||emp.gross_salary, taxYear).paye,0);
    const totalUif  = e ? e.total_uif  : employees.reduce((s,emp)=>s+(calcPayroll(emp.salary||emp.gross_salary, taxYear).uifEmployee+calcPayroll(emp.salary||emp.gross_salary, taxYear).uifEmployer),0);
    const totalSdl  = e ? e.total_sdl  : employees.reduce((s,emp)=>s+calcPayroll(emp.salary||emp.gross_salary, taxYear).sdl,0);
    const totalDue  = e ? e.total_due_sars : totalPaye+totalUif+totalSdl;
    const dueDate   = e ? e.due_date : "7 "+new Date(nowD.getFullYear(),nowD.getMonth()+1).toLocaleDateString("en-ZA",{month:"long",year:"numeric"});
    const empList   = e ? e.employees : employees.map(emp=>{const p=calcPayroll(emp.salary||emp.gross_salary, taxYear);return {employee_name:emp.name,employee_number:emp.id,gross_salary:p.gross,paye:p.paye,uif_employee:p.uifEmployee,uif_employer:p.uifEmployer,sdl:p.sdl,net_pay:p.netPay};});
    return (
      <div>
        <SectionTabs/>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:20}}>
          <div>
            <h2 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:0}}>EMP201 Monthly Employer Return</h2>
            <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>Period: {e?e.period:emp201Period} — Due: <strong style={{color:C.red}}>{dueDate}</strong></p>
          </div>
          <div style={{display:"flex",gap:8,alignItems:"center"}}>
            <input type="month" value={emp201Period} onChange={ev=>{ setEmp201Period(ev.target.value); setEmp201Data(null); }}
              style={{padding:"7px 12px",border:"1px solid "+C.border,borderRadius:8,fontSize:12,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
            <button onClick={loadEmp201} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"8px 16px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>
              {emp201Loading?"Loading…":"Load"}
            </button>
            <ExcelBtn filename="emp201.csv" data={empList.map(emp=>({Name:emp.employee_name,Number:emp.employee_number,Gross:emp.gross_salary,PAYE:emp.paye,UIF_Emp:emp.uif_employee,UIF_Empr:emp.uif_employer,SDL:emp.sdl,Net_Pay:emp.net_pay}))}/>
            <PrintBtn onClick={()=>{const el=document.getElementById("emp201-print");if(!el)return;const w=window.open("","_blank");w.document.write("<html><body>"+el.innerHTML+"</body></html>");w.document.close();w.print();}}/>
          </div>
        </div>
        <div id="emp201-print">
          <div style={{display:"flex",gap:12,marginBottom:20,flexWrap:"wrap"}}>
            <KPI label="PAYE Due"       value={fmt(totalPaye)} color={C.red}    icon="💼" sub="Income tax withheld"/>
            <KPI label="UIF Due"        value={fmt(totalUif)}  color={C.gold}   icon="🛡️" sub="Emp + employer 1%"/>
            <KPI label="SDL Due"        value={fmt(totalSdl)}  color={C.blue}   icon="📚" sub="Skills levy 1%"/>
            <KPI label="Total Due SARS" value={fmt(totalDue)}  color={C.accent} icon="🏛️" sub={"By "+dueDate}/>
          </div>
          <div style={{background:C.redLt,border:"1px solid "+C.red+"30",borderRadius:12,padding:"12px 18px",marginBottom:20,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <div>
              <div style={{fontSize:13,fontWeight:700,color:C.red}}>SARS eFiling Reminder</div>
              <div style={{fontSize:11,color:C.inkMid,marginTop:3}}>EMP201 due by the 7th. Late submission incurs a 10% penalty.</div>
            </div>
            <a href="https://efiling.sars.gov.za" target="_blank" rel="noreferrer" style={{background:C.red,color:"#fff",padding:"8px 16px",borderRadius:8,fontSize:12,fontWeight:700,textDecoration:"none",whiteSpace:"nowrap"}}>Open eFiling</a>
          </div>
          <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,overflow:"hidden"}}>
            <div style={{padding:"14px 20px",borderBottom:"1px solid "+C.border,fontSize:13,fontWeight:700,color:C.ink}}>Employee Tax Certificates (IRP5)</div>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
              <thead>
                <tr style={{background:C.bg,borderBottom:"1px solid "+C.border}}>
                  {["Employee","Emp #","Gross","PAYE","UIF (Emp)","UIF (Empr)","SDL","Net Pay"].map(h=>(
                    <th key={h} style={{padding:"10px 14px",textAlign:"left",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {empList.map((emp,i)=>(
                  <tr key={i} style={{borderBottom:"1px solid "+C.border+"20"}}>
                    <td style={{padding:"11px 14px",fontWeight:600,color:C.ink}}>{emp.employee_name}</td>
                    <td style={{padding:"11px 14px",color:C.inkMid,fontSize:11}}>{emp.employee_number}</td>
                    <td style={{padding:"11px 14px",fontWeight:600}}>{fmt(emp.gross_salary)}</td>
                    <td style={{padding:"11px 14px",color:C.red}}>{fmt(emp.paye)}</td>
                    <td style={{padding:"11px 14px",color:C.gold}}>{fmt(emp.uif_employee)}</td>
                    <td style={{padding:"11px 14px",color:C.blue}}>{fmt(emp.uif_employer)}</td>
                    <td style={{padding:"11px 14px",color:C.blue}}>{fmt(emp.sdl)}</td>
                    <td style={{padding:"11px 14px",fontWeight:700,color:C.green}}>{fmt(emp.net_pay)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr style={{background:C.bg,borderTop:"2px solid "+C.border}}>
                  <td colSpan={2} style={{padding:"11px 14px",fontWeight:800,color:C.ink}}>TOTALS</td>
                  <td style={{padding:"11px 14px",fontWeight:800}}>{fmt(empList.reduce((s,e)=>s+(e.gross_salary||0),0))}</td>
                  <td style={{padding:"11px 14px",fontWeight:800,color:C.red}}>{fmt(totalPaye)}</td>
                  <td style={{padding:"11px 14px",fontWeight:800,color:C.gold}}>{fmt(empList.reduce((s,e)=>s+(e.uif_employee||0),0))}</td>
                  <td style={{padding:"11px 14px",fontWeight:800,color:C.blue}}>{fmt(empList.reduce((s,e)=>s+(e.uif_employer||0),0))}</td>
                  <td style={{padding:"11px 14px",fontWeight:800,color:C.blue}}>{fmt(totalSdl)}</td>
                  <td style={{padding:"11px 14px",fontWeight:800,color:C.green}}>{fmt(empList.reduce((s,e)=>s+(e.net_pay||0),0))}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20}}>
        <div>
          <div style={{display:"flex",gap:4,marginBottom:0}}>
            {["payroll","leave","emp201"].map(s => (
              <button key={s} onClick={()=>setPayrollSection(s)} style={{background:"none",border:"none",borderBottom:payrollSection===s?`2px solid ${C.accent}`:"2px solid transparent",padding:"4px 14px",fontSize:13,fontWeight:payrollSection===s?700:400,color:payrollSection===s?C.accent:C.inkMid,cursor:"pointer",fontFamily:"inherit"}}>
                {SECTION_LABELS[s]}
              </button>
            ))}
          </div>
          <p style={{fontSize:12,color:C.inkMid,marginTop:4}}>SARS-compliant PAYE, UIF, SDL, EMP201, IRP5</p>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:12}}>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            <span style={{fontSize:12,color:C.inkMid,fontWeight:600}}>Tax Year:</span>
            <select value={taxYear} onChange={e=>setTaxYear(e.target.value)} style={{padding:"7px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:12,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",fontWeight:700}}>
              {Object.keys(TAX_YEARS).reverse().map(y=>(
                <option key={y} value={y}>{y}{y===CURRENT_TAX_YEAR?" (current)":""}</option>
              ))}
            </select>
          </div>
          <button onClick={()=>setShowNew(true)} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>+ Add Employee</button>
        </div>
      </div>
      <div style={{background:C.goldLt,border:`1px solid ${C.gold}40`,borderRadius:12,padding:"12px 18px",marginBottom:20,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div style={{fontSize:12,color:C.inkMid}}>ZuZan Payroll Module - {employees.length} employees x R17.50 = <strong style={{color:C.accent}}>{fmt(zuZanFee)}/month</strong></div>
        <Badge label="Active" color={C.green} bg={C.greenLt}/>
      </div>
      <div style={{display:"flex",gap:12,marginBottom:20,flexWrap:"wrap"}}>
        <KPI label="Gross Payroll" value={fmt(totalGross)} color={C.ink} icon="💼"/>
        <KPI label="PAYE to SARS" value={fmt(totalPAYE)} color={C.red} icon="🏛️"/>
        <KPI label="UIF and SDL" value={fmt(totalUIF+totalSDL)} color={C.gold} icon="🛡️"/>
        <KPI label="Total Cost" value={fmt(totalCost)} color={C.accent} icon="📊"/>
      </div>
      <div style={{background:`linear-gradient(135deg,${C.accentLt},transparent)`,border:`1px solid ${C.accent}40`,borderRadius:16,padding:"16px 24px",marginBottom:20,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div>
          <div style={{fontWeight:700,fontSize:15,color:C.ink}}>{new Date().toLocaleDateString("en-ZA",{month:"long",year:"numeric"})} Payroll</div>
          <div style={{fontSize:12,color:C.inkMid,marginTop:3}}>Net pay: {fmt(totalNet)} - SARS due: 7 {new Date(new Date().getFullYear(),new Date().getMonth()+1,7).toLocaleDateString("en-ZA",{month:"long",year:"numeric"})}</div>
        </div>
        <button onClick={() => {
          // Initialise overtime entries for all employees (default 0)
          const init = {};
          employees.forEach(e => { init[e.id] = {otHours:0, sunHours:0, phHours:0}; });
          setOtData(init);
          setShowOtModal(true);
        }} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Run Payroll</button>
      </div>
      {/* ── BCEA Overtime Entry Modal ────────────────────────────────────── */}
      {showOtModal && (
        <div style={{position:"fixed",inset:0,background:"#00000070",zIndex:200,display:"flex",alignItems:"center",justifyContent:"center",padding:24}}>
          <div style={{background:C.surface,borderRadius:20,padding:32,width:"100%",maxWidth:760,maxHeight:"90vh",overflowY:"auto",boxShadow:"0 8px 40px #00000030"}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:6}}>
              <h3 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:0}}>Run Payroll — Overtime Entry</h3>
              <button onClick={()=>setShowOtModal(false)} style={{background:"none",border:"none",fontSize:22,cursor:"pointer",color:C.inkMid}}>×</button>
            </div>
            <p style={{fontSize:12,color:C.inkMid,marginBottom:16}}>Enter BCEA overtime hours per employee for this pay period. Leave at 0 if none worked. Weekday/Sat OT = 1.5× · Sunday = 2× · Public Holiday = 2×</p>

            {/* ── CSV / Excel upload strip ── */}
            <div style={{background:C.bg,border:`1px solid ${C.border}`,borderRadius:12,padding:"14px 18px",marginBottom:20}}>
              <div style={{display:"flex",alignItems:"center",gap:12,flexWrap:"wrap"}}>
                <span style={{fontSize:12,fontWeight:700,color:C.ink}}>📂 Upload overtime from file</span>
                <button onClick={() => {
                  // Generate and download a template CSV/XLSX with employee list pre-filled
                  const rows = employees.map(e => ({
                    "Employee Number": e.employee_number || e.id,
                    "Employee Name":   e.name,
                    "Weekday_Sat_OT_Hours": 0,
                    "Sunday_Hours":          0,
                    "Public_Holiday_Hours":  0,
                  }));
                  const ws = XLSX.utils.json_to_sheet(rows);
                  ws["!cols"] = [{wch:18},{wch:28},{wch:22},{wch:16},{wch:22}];
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, "Overtime");
                  XLSX.writeFile(wb, `overtime_${new Date().toISOString().slice(0,7)}.xlsx`);
                }} style={{background:C.greenLt,color:C.green,border:`1px solid ${C.green}40`,borderRadius:8,padding:"7px 14px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>
                  ⬇ Download Template
                </button>
                <label style={{background:C.blueLt,color:C.blue,border:`1px solid ${C.blue}40`,borderRadius:8,padding:"7px 14px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>
                  ⬆ Upload CSV / Excel
                  <input type="file" accept=".csv,.xlsx,.xls" style={{display:"none"}} onChange={e => {
                    const file = e.target.files[0];
                    if (!file) return;
                    const reader = new FileReader();
                    reader.onload = ev => {
                      try {
                        const wb = XLSX.read(ev.target.result, {type:"binary"});
                        const ws = wb.Sheets[wb.SheetNames[0]];
                        const rows = XLSX.utils.sheet_to_json(ws, {defval:0});
                        let matched = 0, unmatched = [];
                        const newOt = {...otData};
                        rows.forEach(row => {
                          // Accept employee_number, employee name, or id as lookup key
                          const empNum = String(row["Employee Number"] || row["employee_number"] || row["EmpNo"] || "").trim();
                          const empName = String(row["Employee Name"]   || row["employee_name"]   || row["Name"]  || "").trim().toLowerCase();
                          const emp = employees.find(e =>
                            (empNum && (String(e.employee_number||"").trim() === empNum || String(e.id) === empNum)) ||
                            (empName && e.name.toLowerCase() === empName)
                          );
                          if (!emp) { unmatched.push(empNum || empName || "(unknown)"); return; }
                          matched++;
                          newOt[emp.id] = {
                            otHours:  +(row["Weekday_Sat_OT_Hours"]  || row["overtime_hours"]  || row["OT Hours"]        || 0),
                            sunHours: +(row["Sunday_Hours"]           || row["sunday_hours"]    || row["Sunday OT Hours"] || 0),
                            phHours:  +(row["Public_Holiday_Hours"]   || row["ph_hours"]        || row["PH Hours"]        || 0),
                          };
                        });
                        setOtData(newOt);
                        if (unmatched.length) alert(`Imported ${matched} employees.\n\nCould not match ${unmatched.length} row(s):\n${unmatched.join(", ")}\n\nCheck that Employee Number in your file matches the payroll list.`);
                        else alert(`✅ Imported ${matched} employee${matched!==1?"s":""} from file.`);
                      } catch(err) {
                        alert("Could not read file: " + err.message);
                      }
                    };
                    reader.readAsBinaryString(file);
                    e.target.value = "";   // allow re-upload of same file
                  }}/>
                </label>
                <span style={{fontSize:11,color:C.inkMid}}>Columns: Employee Number · Employee Name · Weekday_Sat_OT_Hours · Sunday_Hours · Public_Holiday_Hours</span>
              </div>
            </div>

            <table style={{width:"100%",borderCollapse:"collapse",fontSize:12,marginBottom:20}}>
              <thead>
                <tr style={{background:C.bg}}>
                  {["Employee","Grade","BCEA Hourly Rate","Weekday/Sat OT hrs","Sunday hrs","PH hrs","OT Pay Preview"].map(h=>(
                    <th key={h} style={{padding:"10px 12px",textAlign:"left",fontSize:10,color:C.inkMid,fontWeight:700,textTransform:"uppercase",letterSpacing:0.4,borderBottom:`1px solid ${C.border}`}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {employees.map(emp => {
                  const ot = otData[emp.id] || {otHours:0,sunHours:0,phHours:0};
                  const hr = bceaHourlyRate(emp.salary, emp.hourly_rate||null);
                  const preview = calcOvertime(emp.salary, +ot.otHours||0, +ot.sunHours||0, +ot.phHours||0, emp.hourly_rate||null);
                  const inpStyle = {width:"60px",padding:"6px 8px",border:`1px solid ${C.border}`,borderRadius:6,fontSize:12,fontFamily:"inherit",textAlign:"center",background:C.bg,color:C.ink,outline:"none"};
                  const setOt = (k,v) => setOtData(prev=>({...prev,[emp.id]:{...prev[emp.id],[k]:v}}));
                  return (
                    <tr key={emp.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                      <td style={{padding:"10px 12px"}}>
                        <div style={{fontWeight:600,color:C.ink}}>{emp.name}</div>
                        <div style={{fontSize:10,color:C.inkMid}}>{emp.employee_number||emp.id}</div>
                      </td>
                      <td style={{padding:"10px 12px"}}>
                        {emp.grade ? <Badge label={emp.grade} color={C.blue} bg={C.blueLt}/> : <span style={{color:C.inkMid}}>—</span>}
                      </td>
                      <td style={{padding:"10px 12px",color:C.inkMid}}>{fmt(hr)}/hr</td>
                      <td style={{padding:"10px 12px"}}>
                        <input style={inpStyle} type="number" min="0" max="10" step="0.5" value={ot.otHours||""} placeholder="0" onChange={e=>setOt("otHours",e.target.value)}/>
                      </td>
                      <td style={{padding:"10px 12px"}}>
                        <input style={inpStyle} type="number" min="0" step="0.5" value={ot.sunHours||""} placeholder="0" onChange={e=>setOt("sunHours",e.target.value)}/>
                      </td>
                      <td style={{padding:"10px 12px"}}>
                        <input style={inpStyle} type="number" min="0" step="0.5" value={ot.phHours||""} placeholder="0" onChange={e=>setOt("phHours",e.target.value)}/>
                      </td>
                      <td style={{padding:"10px 12px",fontWeight:700,color:preview.total>0?C.green:C.inkMid}}>
                        {preview.total > 0 ? `+ ${fmt(preview.total)}` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div style={{display:"flex",gap:10,justifyContent:"flex-end"}}>
              <button onClick={()=>setShowOtModal(false)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
              <button onClick={async () => {
                setShowOtModal(false);
                try {
                  const otPayload = employees.map(emp => {
                    const ot = otData[emp.id] || {};
                    return { employee_id: emp.id, overtime_hours: +ot.otHours||0, sunday_hours: +ot.sunHours||0, ph_hours: +ot.phHours||0 };
                  }).filter(e => e.overtime_hours > 0 || e.sunday_hours > 0 || e.ph_hours > 0);
                  await api("/payroll/run", {method:"POST", body: JSON.stringify({overtime: otPayload})});
                  if (live && live.reload) live.reload();
                } catch(err) { console.warn("Payroll run failed:", err.message); }
                setPayrollRun(true);
              }} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 24px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>
                Confirm &amp; Run Payroll
              </button>
            </div>
          </div>
        </div>
      )}

      {payrollRun && (
        <div style={{background:C.surface,border:`2px solid ${C.green}`,borderRadius:16,padding:20,marginBottom:20}}>
          <div style={{fontSize:16,fontWeight:700,color:C.green,marginBottom:12}}>Payroll Processed - {new Date().toLocaleDateString("en-ZA",{month:"long",year:"numeric"})}</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:12}}>
            {[["Net Disbursed",fmt(totalNet),C.green],["PAYE to SARS",fmt(totalPAYE),C.red],["UIF and SDL",fmt(totalUIF+totalSDL),C.gold],["ZuZan Fee",fmt(zuZanFee),C.accent]].map(([l,v,c]) => (
              <div key={l} style={{background:C.bg,borderRadius:10,padding:14}}>
                <div style={{fontSize:10,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{l}</div>
                <div style={{fontSize:18,fontWeight:700,color:c}}>{v}</div>
              </div>
            ))}
          </div>
          <div style={{marginTop:16,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
            <div style={{fontSize:12,color:C.inkMid}}>EMP201 generated · Payslips ready · SARS eFiling export ready</div>
            <button onClick={()=>setShowBatch(true)} style={{background:C.ink,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>⬇ Download Payment Files</button>
          </div>
        </div>
      )}
      {showBatch && (
        <BatchPaymentModal
          employees={employees}
          payroll={employees.map(e=>calcPayroll(e.salary))}
          period={new Date().toLocaleDateString("en-ZA",{month:"long",year:"numeric"})}
          onClose={()=>setShowBatch(false)}
        />
      )}
      {showNew && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:28,marginBottom:20}}>
          <h3 style={{fontFamily:"serif",fontSize:20,margin:"0 0 20px",color:C.ink}}>New Employee</h3>

          {/* Employment Details */}
          <div style={{fontSize:11,fontWeight:700,color:C.accent,textTransform:"uppercase",letterSpacing:1,marginBottom:10}}>Employment Details</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12,marginBottom:16}}>
            {[
              {l:"Employee #",           k:"empNo",           p:"EMP-001",     t:"text"},
              {l:"Full Name",            k:"name",            p:"Sipho Dlamini",t:"text"},
              {l:"Position / Title",     k:"position",        p:"Developer",   t:"text"},
              {l:"Department",           k:"dept",            p:"Tech",        t:"text"},
              {l:"Monthly Salary (ZAR)", k:"salary",          p:"35000",       t:"number"},
              {l:"Date of Appointment",  k:"appointmentDate", p:"",            t:"date"},
              {l:"Grade / Pay Band",     k:"grade",           p:"e.g. A, B2, Senior", t:"text"},
            ].map(f => (
              <div key={f.k}>
                <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                <input type={f.t} placeholder={f.p} value={form[f.k]} onChange={e=>setForm(v=>({...v,[f.k]:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
              </div>
            ))}
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Employment Type</label>
              <select value={form.employmentType} onChange={e=>setForm(v=>({...v,employmentType:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                <option value="salaried">Salaried (fixed monthly)</option>
                <option value="hourly">Hourly rate</option>
              </select>
            </div>
            {form.employmentType === "hourly" && (
              <div>
                <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Hourly Rate (ZAR)</label>
                <input type="number" placeholder="e.g. 150" value={form.hourlyRate} onChange={e=>setForm(v=>({...v,hourlyRate:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
              </div>
            )}
          </div>
          {form.salary && (
            <div style={{background:C.blueLt,border:`1px solid ${C.blue}30`,borderRadius:8,padding:"10px 14px",marginBottom:16,fontSize:12,color:C.inkMid}}>
              <strong style={{color:C.blue}}>BCEA hourly rate: </strong>
              {fmt(bceaHourlyRate(+form.salary, form.hourlyRate ? +form.hourlyRate : null))}/hr
              <span style={{marginLeft:16}}>Weekday OT: {fmt(bceaHourlyRate(+form.salary, form.hourlyRate ? +form.hourlyRate : null) * 1.5)}/hr · Sunday: {fmt(bceaHourlyRate(+form.salary, form.hourlyRate ? +form.hourlyRate : null) * 2)}/hr</span>
            </div>
          )}

          {/* Personal Details */}
          <div style={{fontSize:11,fontWeight:700,color:C.accent,textTransform:"uppercase",letterSpacing:1,marginBottom:10}}>Personal Details</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12,marginBottom:20}}>
            {[
              {l:"SA ID Number",  k:"idNumber",   p:"8001015009087", t:"text"},
              {l:"Tax Number",    k:"taxNumber",  p:"1234567890",    t:"text"},
              {l:"Date of Birth", k:"dob",        p:"",              t:"date"},
            ].map(f => (
              <div key={f.k}>
                <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                <input type={f.t} placeholder={f.p} value={form[f.k]} onChange={e=>setForm(v=>({...v,[f.k]:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
              </div>
            ))}
            <div style={{gridColumn:"1 / -1"}}>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Residential Address</label>
              <input placeholder="123 Main St, Johannesburg, 2000" value={form.address} onChange={e=>setForm(v=>({...v,address:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
            </div>
          </div>

          {/* Bank Details */}
          <div style={{fontSize:11,fontWeight:700,color:C.accent,textTransform:"uppercase",letterSpacing:1,marginBottom:10}}>Bank Details</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:12,marginBottom:20}}>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Bank Name</label>
              <select value={form.bankName} onChange={e=>setForm(v=>({...v,bankName:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                <option value="">-- Select Bank --</option>
                {["ABSA","Capitec","Discovery Bank","FNB","Investec","Nedbank","Standard Bank","TymeBank","African Bank"].map(b=><option key={b}>{b}</option>)}
              </select>
            </div>
            {[
              {l:"Account Number", k:"accountNumber", p:"62123456789"},
              {l:"Branch Code",    k:"branchCode",    p:"250655"},
            ].map(f=>(
              <div key={f.k}>
                <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                <input placeholder={f.p} value={form[f.k]} onChange={e=>setForm(v=>({...v,[f.k]:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
              </div>
            ))}
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Account Type</label>
              <select value={form.accountType} onChange={e=>setForm(v=>({...v,accountType:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                {["Cheque","Savings","Transmission"].map(t=><option key={t}>{t}</option>)}
              </select>
            </div>
          </div>

          <div style={{display:"flex",gap:8}}>
            <button onClick={handleAdd} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 24px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Add Employee</button>
            <button onClick={() => setShowNew(false)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
          </div>
        </div>
      )}
      <div key={taxYear} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden",marginBottom:16}}>
        <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
          <thead>
            <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
              {["Employee","Grade","Position","Dept","Gross","PAYE","UIF","SDL","Net Pay","Employer Cost",""].map(h => <th key={h} style={{textAlign:"left",padding:"12px 14px",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {employees.map((emp) => {
              const p = calcPayroll(emp.salary, taxYear);
              return (
                <tr key={emp.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                  <td style={{padding:"13px 14px"}}><div style={{fontWeight:600,color:C.ink}}>{emp.name}</div><div style={{fontSize:10,color:C.inkMid}}>{emp.employee_number||emp.id}</div></td>
                  <td style={{padding:"13px 14px"}}>{emp.grade ? <Badge label={emp.grade} color={C.blue} bg={C.blueLt}/> : <span style={{color:C.inkMid,fontSize:11}}>—</span>}</td>
                  <td style={{padding:"13px 14px",color:C.inkMid}}>{emp.position}</td>
                  <td style={{padding:"13px 14px"}}><Badge label={emp.dept||"General"} color={C.blue} bg={C.blueLt}/></td>
                  <td style={{padding:"13px 14px",fontWeight:600}}>{fmt(p.gross)}</td>
                  <td style={{padding:"13px 14px",color:C.red}}>{fmt(p.paye)}</td>
                  <td style={{padding:"13px 14px",color:C.gold}}>{fmt(p.uifEmployee)}</td>
                  <td style={{padding:"13px 14px",color:C.blue}}>{fmt(p.sdl)}</td>
                  <td style={{padding:"13px 14px",fontWeight:700,color:C.green}}>{fmt(p.netPay)}</td>
                  <td style={{padding:"13px 14px",fontWeight:700,color:C.accent}}>{fmt(p.totalCost)}</td>
                  <td style={{padding:"13px 14px"}}>
                    <button onClick={()=>setViewPayslip({employee:emp,payroll:p,taxYear})} style={{background:C.blueLt,color:C.blue,border:"none",borderRadius:6,padding:"5px 10px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Payslip</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr style={{background:C.bg,borderTop:`2px solid ${C.border}`}}>
              <td colSpan={3} style={{padding:"13px 14px",fontWeight:800,color:C.ink}}>TOTALS</td>
              <td style={{padding:"13px 14px",fontWeight:800}}>{fmt(totalGross)}</td>
              <td style={{padding:"13px 14px",fontWeight:800,color:C.red}}>{fmt(totalPAYE)}</td>
              <td style={{padding:"13px 14px",fontWeight:800,color:C.gold}}>{fmt(employees.reduce((s,e)=>s+calcPayroll(e.salary).uifEmployee,0))}</td>
              <td style={{padding:"13px 14px",fontWeight:800,color:C.blue}}>{fmt(totalSDL)}</td>
              <td style={{padding:"13px 14px",fontWeight:800,color:C.green}}>{fmt(totalNet)}</td>
              <td style={{padding:"13px 14px",fontWeight:800,color:C.accent}}>{fmt(totalCost)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div style={{background:C.bg,border:`1px solid ${C.border}`,borderRadius:12,padding:16,fontSize:12,color:C.inkMid,lineHeight:1.8}}>
        <strong style={{color:C.ink}}>SARS &amp; BCEA Compliance Notes {taxYear}</strong><br/>
        PAYE: 2026/2027 tax tables · Primary rebate R17,820/year · Due 7th of each month<br/>
        UIF: 1% employee + 1% employer · Capped at R17,712/month · Overtime excluded from UIF base<br/>
        SDL: 1% of gross payroll · Payable if annual payroll ≥ R500,000<br/>
        <strong style={{color:C.ink}}>BCEA Overtime (s9/s10/s16/s18):</strong> Normal week = 45 hrs · OT max 10 hrs/week · Weekday/Sat OT = 1.5× · Sunday = 2× · Public holiday = 2× · Hourly rate derived from salary ÷ 195 hrs/month
      </div>

      {viewPayslip && (
        <PayslipModal
          employee={viewPayslip.employee}
          payroll={viewPayslip.payroll}
          period={new Date().toLocaleDateString("en-ZA",{month:"long",year:"numeric"})}
          company={user.companyName || "Your Company"}
          logoUrl={user.logoUrl || ""}
          onClose={()=>setViewPayslip(null)}
        />
      )}
    </div>
  );
}
// REPORTS
function ReportRow({label,value,bold,border,large,indent,color}) {
  const isNeg = value < 0;
  const displayVal = isNeg ? "("+fmt(Math.abs(value))+")" : fmt(value);
  return (
    <div style={{display:"flex",justifyContent:"space-between",padding:(large?"14px":"9px")+" 0",borderTop:border?"2px solid "+C.border:"1px solid "+C.border+"20"}}>
      <span style={{fontSize:large?15:13,fontWeight:bold?700:400,color:C.ink,paddingLeft:indent?20:0}}>{label}</span>
      <span style={{fontSize:large?18:14,fontWeight:bold?800:500,color:color||(isNeg?C.red:C.green)}}>{displayVal}</span>
    </div>
  );
}

function PrintBtn({onClick}) {
  return <button onClick={onClick} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"8px 18px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Print PDF</button>;
}

function ExcelBtn({data,filename}) {
  const download = () => {
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Report");
    XLSX.writeFile(wb, filename.replace(".csv",".xlsx"));
  };
  return <button onClick={download} style={{background:C.greenLt,color:C.green,border:"1px solid "+C.green+"40",borderRadius:8,padding:"8px 18px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Export Excel</button>;
}

function Reports({live = {}}) {
  const [activeTab, setActiveTab] = useState("pl");
  const [bsData,  setBsData]  = useState(null);
  const [cfData,  setCfData]  = useState(null);
  // emp201 moved to Payroll component
  const [mgmt,     setMgmt]     = useState(null);
  const [provTax,  setProvTax]  = useState(null);
  const [vat201,   setVat201]   = useState(null);
  const [recon,    setRecon]    = useState(null);
  const [trialBal, setTrialBal] = useState(null);
  const [journal,  setJournal]  = useState(null);
  const [jnlExpanded, setJnlExpanded] = useState(new Set());
  const [jnlAccounts, setJnlAccounts] = useState([]);
  const [jnlForm, setJnlForm] = useState(null); // null = hidden, object = visible
  const JNL_EMPTY_FORM = {date:new Date().toISOString().slice(0,10),description:"",reference:"",auto_reverse:false,reversal_date:"",lines:[{account_id:"",debit:"",credit:"",description:""},{account_id:"",debit:"",credit:"",description:""}]};

  const [vatPeriod,setVatPeriod]= useState(new Date().toISOString().slice(0,7));
  const [loading,  setLoading]  = useState(false);
  const [mgmtDrill, setMgmtDrill] = useState(null); // {type,title,cols,rows,total,color}
  const [mgmtDrillLoading, setMgmtDrillLoading] = useState(false);

  // ── Date range ──────────────────────────────────────────────────
  const now = new Date();
  const firstOfMonth  = new Date(now.getFullYear(), now.getMonth(), 1);
  const firstOfLast   = new Date(now.getFullYear(), now.getMonth()-1, 1);
  const lastOfLast    = new Date(now.getFullYear(), now.getMonth(), 0);
  // SA financial year: 1 Mar – last Feb
  const fyStart = now.getMonth() >= 2
    ? new Date(now.getFullYear(), 2, 1)
    : new Date(now.getFullYear()-1, 2, 1);
  const fyEnd   = new Date(fyStart.getFullYear()+1, 1, 28);
  const toISO   = d => d.toISOString().slice(0,10);
  const PRESETS = [
    {label:"Current Month",  from:toISO(firstOfMonth), to:toISO(now)},
    {label:"Last Month",     from:toISO(firstOfLast),  to:toISO(lastOfLast)},
    {label:"Financial Year", from:toISO(fyStart),      to:toISO(fyEnd)},
    {label:"All Time",       from:"2000-01-01",         to:toISO(now)},
    {label:"Custom",         from:"",                  to:""},
  ];
  const [preset,   setPreset]   = useState("All Time");
  const [dateFrom, setDateFrom] = useState("2000-01-01");
  const [dateTo,   setDateTo]   = useState(toISO(now));
  const handlePreset = (label) => {
    setPreset(label);
    const p = PRESETS.find(p => p.label === label);
    if (label !== "Custom") { setDateFrom(p.from); setDateTo(p.to); }
  };
  const periodLabel = preset === "Custom"
    ? `${dateFrom} to ${dateTo}`
    : preset === "Financial Year"
      ? `FY ${fyStart.getFullYear()}/${fyEnd.getFullYear()}`
      : preset;
  // ────────────────────────────────────────────────────────────────

  const d   = live.dashboard;
  const period = d ? d.period : periodLabel;
  const totalRevenue  = d ? d.total_revenue  : MOCK_INVOICES.filter(i=>i.status==="paid").reduce((s,i)=>s+i.amount,0);
  const totalExpenses = d ? d.total_expenses : MOCK_EXPENSES.reduce((s,e)=>s+e.amount,0);
  const totalPayroll  = d ? d.total_payroll  : MOCK_EMPLOYEES.reduce((s,e)=>s+calcPayroll(e.salary).totalCost,0);
  const grossProfit   = d ? d.gross_profit   : totalRevenue - totalExpenses;
  const netProfit     = d ? d.net_profit     : grossProfit - totalPayroll;
  const taxProvision  = d ? d.tax_provision  : Math.max(0, netProfit * 0.27);
  const netAfterTax   = netProfit - taxProvision;
  const dateParams = `date_from=${dateFrom}&date_to=${dateTo}`;
  const loadTab = async (tab, forceReload=false) => {
    setActiveTab(tab);
    setLoading(true);
    try {
      if (tab==="bs")    setBsData(await api(`/reports/balance-sheet`).catch(()=>null));
      if (tab==="recon") setRecon(await api(`/reports/reconciliation`).catch(()=>null));
      if (tab==="tb")    setTrialBal(await api(`/journal/trial-balance`).catch(()=>null));
      if (tab==="jnl") {
        setJournal(await api(`/journal/?limit=100`).catch(()=>null));
        if (!jnlAccounts.length) api("/journal/accounts").then(setJnlAccounts).catch(()=>null);
      }
      if (tab==="cf")   setCfData(await api(`/reports/cash-flow?${dateParams}`).catch(()=>null));
      // emp201 now lives in Payroll component
      if (tab==="pl")   setMgmt(await api(`/reports/management?${dateParams}`).catch(()=>null));
      if (tab==="mgmt") setMgmt(await api(`/reports/management?${dateParams}`).catch(()=>null));
      if (tab==="prov") setProvTax(await api(`/reports/provisional-tax?${dateParams}`).catch(()=>null));
      if (tab==="vat")  setVat201(await api(`/reports/vat201?period=${vatPeriod}&${dateParams}`).catch(()=>null));
    } finally { setLoading(false); }
  };
  // Reload current tab when date range changes
  useEffect(() => { loadTab(activeTab, true); }, [dateFrom, dateTo]);
  const RTABS = [
    {id:"pl",   label:"Income Statement"},
    {id:"bs",   label:"Balance Sheet"},
    {id:"recon",label:"Reconciliation"},
    {id:"tb",   label:"Trial Balance"},
    {id:"jnl",  label:"Journal"},
    {id:"cf",   label:"Cash Flow"},
    {id:"mgmt", label:"Management Pack"},

    {id:"prov", label:"Provisional Tax"},
    {id:"vat",  label:"VAT201"},
  ];
  const renderBS = () => {
    const bs = bsData;
    if (!bs) return <div style={{color:C.inkMid,fontSize:13,padding:20}}>Loading balance sheet…</div>;
    const balanced = bs.balanced;
    return (
      <div>
        <div style={{display:"flex",justifyContent:"space-between",marginBottom:16}}>
          <div><div style={{fontFamily:"serif",fontSize:20,fontWeight:800,color:C.ink}}>Balance Sheet</div><div style={{fontSize:12,color:C.inkMid,marginTop:4}}>As at {bs.date}</div></div>
          <ExcelBtn filename="balance-sheet.csv" data={[
            {Item:"Cash & Equivalents",Amount:bs.assets.cash_and_equivalents},
            {Item:"Trade Receivables",Amount:bs.assets.trade_receivables},
            {Item:"Inventory at Cost",Amount:bs.assets.inventory_at_cost},
            {Item:"VAT Input Recoverable",Amount:bs.assets.vat_input_recoverable},
            {Item:"Fixed Assets at Cost",Amount:bs.assets.fixed_assets_cost||0},
            {Item:"Accumulated Depreciation",Amount:bs.assets.accum_depreciation||0},
            {Item:"Fixed Assets (Net)",Amount:bs.assets.fixed_assets_net||0},
            {Item:"Total Assets",Amount:bs.assets.total},
            {Item:"Accounts Payable",Amount:bs.liabilities.accounts_payable},
            {Item:"VAT Payable",Amount:bs.liabilities.vat_payable},
            {Item:"PAYE Payable",Amount:bs.liabilities.paye_payable},
            {Item:"UIF Payable",Amount:bs.liabilities.uif_payable},
            {Item:"SDL Payable",Amount:bs.liabilities.sdl_payable},
            {Item:"Total Liabilities",Amount:bs.liabilities.total},
            {Item:"Retained Income",Amount:bs.equity.retained_income},
            {Item:"Total Equity",Amount:bs.equity.total},
            {Item:"Total Liabilities & Equity",Amount:bs.total_liabilities_and_equity},
          ]}/>
        </div>
        {/* Balance check banner */}
        <div style={{background:balanced?C.greenLt:"#FFF3F3",border:`1px solid ${balanced?C.green:C.red}`,borderRadius:10,padding:"10px 16px",marginBottom:20,display:"flex",alignItems:"center",gap:10}}>
          <span style={{fontSize:18}}>{balanced?"✅":"❌"}</span>
          <span style={{fontSize:13,fontWeight:600,color:balanced?C.green:C.red}}>
            {balanced
              ? "Balance sheet is balanced — Assets = Liabilities + Equity"
              : `Balance sheet imbalance of R ${Math.abs(bs.imbalance).toLocaleString("en-ZA",{minimumFractionDigits:2})} — check the Reconciliation tab for details`}
          </span>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:24}}>
          <div>
            <div style={{fontSize:11,fontWeight:700,color:C.blue,textTransform:"uppercase",letterSpacing:1,marginBottom:12}}>Assets</div>
            <ReportRow label="Cash and Cash Equivalents"   value={bs.assets.cash_and_equivalents} color={C.blue}/>
            <ReportRow label="Trade Receivables (Debtors)" value={bs.assets.trade_receivables}    color={C.blue}/>
            <ReportRow label="Inventory at Cost"           value={bs.assets.inventory_at_cost}    color={C.blue}/>
            {bs.assets.vat_input_recoverable > 0 && <ReportRow label="VAT Input Recoverable" value={bs.assets.vat_input_recoverable} color={C.blue}/>}
            {(bs.assets.fixed_assets_cost||0) > 0 && <>
              <ReportRow label="Fixed Assets at Cost"       value={bs.assets.fixed_assets_cost}   color={C.blue} indent/>
              <ReportRow label="Accumulated Depreciation"   value={bs.assets.accum_depreciation}  color={C.red}  indent/>
              <ReportRow label="Fixed Assets (Net)"         value={bs.assets.fixed_assets_net}    color={C.blue}/>
            </>}
            <ReportRow label="Total Assets"                value={bs.assets.total} bold border color={C.blue}/>
          </div>
          <div>
            <div style={{fontSize:11,fontWeight:700,color:C.red,textTransform:"uppercase",letterSpacing:1,marginBottom:12}}>Liabilities</div>
            <ReportRow label="Accounts Payable (Suppliers)" value={bs.liabilities.accounts_payable} indent color={C.red}/>
            <ReportRow label="VAT Payable (SARS)"           value={bs.liabilities.vat_payable}      indent color={C.red}/>
            <ReportRow label="PAYE Payable (SARS)"          value={bs.liabilities.paye_payable}     indent color={C.red}/>
            <ReportRow label="UIF Payable (SARS)"           value={bs.liabilities.uif_payable}      indent color={C.red}/>
            <ReportRow label="SDL Payable (SARS)"           value={bs.liabilities.sdl_payable}      indent color={C.red}/>
            <ReportRow label="Total Liabilities"            value={bs.liabilities.total} bold border color={C.red}/>
            <div style={{height:12}}/>
            <div style={{fontSize:11,fontWeight:700,color:C.green,textTransform:"uppercase",letterSpacing:1,marginBottom:12}}>Equity</div>
            <ReportRow label="Retained Income" value={bs.equity.retained_income} color={C.green}/>
            <ReportRow label="Total Equity"    value={bs.equity.total} bold color={C.green}/>
            <div style={{height:12}}/>
            <ReportRow label="Total Liabilities and Equity" value={bs.total_liabilities_and_equity} bold border large color={balanced?C.ink:C.red}/>
          </div>
        </div>
      </div>
    );
  };

  const renderReconciliation = () => {
    if (!recon) return <div style={{color:C.inkMid,fontSize:13,padding:20}}>Loading reconciliation…</div>;
    const { summary, checks } = recon;
    const statusColor = s => s==="pass"?C.green:s==="warn"?C.gold:C.red;
    const statusBg    = s => s==="pass"?C.greenLt:s==="warn"?"#FFFBEB":"#FFF3F3";
    const statusIcon  = s => s==="pass"?"✅":s==="warn"?"⚠️":"❌";
    return (
      <div>
        <div style={{fontFamily:"serif",fontSize:20,fontWeight:800,color:C.ink,marginBottom:4}}>Reconciliation Report</div>
        <div style={{fontSize:12,color:C.inkMid,marginBottom:20}}>As at {recon.date}</div>

        {/* Summary pills */}
        <div style={{display:"flex",gap:12,marginBottom:24}}>
          <div style={{background:C.greenLt,borderRadius:10,padding:"10px 18px",textAlign:"center"}}>
            <div style={{fontSize:22,fontWeight:800,color:C.green}}>{summary.passed}</div>
            <div style={{fontSize:11,color:C.green,fontWeight:600}}>PASSED</div>
          </div>
          <div style={{background:"#FFFBEB",borderRadius:10,padding:"10px 18px",textAlign:"center"}}>
            <div style={{fontSize:22,fontWeight:800,color:C.gold}}>{summary.warned}</div>
            <div style={{fontSize:11,color:C.gold,fontWeight:600}}>WARNINGS</div>
          </div>
          <div style={{background:"#FFF3F3",borderRadius:10,padding:"10px 18px",textAlign:"center"}}>
            <div style={{fontSize:22,fontWeight:800,color:C.red}}>{summary.failed}</div>
            <div style={{fontSize:11,color:C.red,fontWeight:600}}>FAILED</div>
          </div>
          <div style={{background:C.surface,borderRadius:10,padding:"10px 18px",textAlign:"center",border:`1px solid ${C.border}`}}>
            <div style={{fontSize:22,fontWeight:800,color:C.ink}}>{summary.total}</div>
            <div style={{fontSize:11,color:C.inkMid,fontWeight:600}}>TOTAL CHECKS</div>
          </div>
        </div>

        {/* Per-check cards */}
        {checks.map((check, i) => (
          <div key={i} style={{background:statusBg(check.status),border:`1px solid ${statusColor(check.status)}40`,borderLeft:`4px solid ${statusColor(check.status)}`,borderRadius:10,padding:"14px 16px",marginBottom:12}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:12}}>
              <div style={{flex:1}}>
                <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:6}}>
                  <span style={{fontSize:16}}>{statusIcon(check.status)}</span>
                  <span style={{fontSize:14,fontWeight:700,color:C.ink}}>{check.rule}</span>
                  <span style={{fontSize:11,fontWeight:700,color:statusColor(check.status),background:`${statusColor(check.status)}20`,padding:"2px 8px",borderRadius:20,textTransform:"uppercase"}}>
                    {check.status}
                  </span>
                </div>
                <div style={{fontSize:13,color:C.inkMid,lineHeight:1.5}}>{check.detail}</div>
              </div>
              {check.amount !== null && check.amount !== undefined &&
                <div style={{textAlign:"right",flexShrink:0}}>
                  <div style={{fontSize:16,fontWeight:700,color:statusColor(check.status)}}>
                    R {Math.abs(check.amount).toLocaleString("en-ZA",{minimumFractionDigits:2})}
                  </div>
                </div>}
            </div>
            {/* Drill-down items */}
            {check.items && check.items.length > 0 && (
              <div style={{marginTop:10,borderTop:`1px solid ${statusColor(check.status)}30`,paddingTop:10}}>
                {check.items.slice(0,5).map((item,j)=>(
                  <div key={j} style={{display:"flex",justifyContent:"space-between",fontSize:12,color:C.inkMid,padding:"3px 0",borderBottom:`1px solid ${C.border}`}}>
                    <span style={{fontWeight:500}}>{item.id || item.sku || item.name} {item.client?"— "+item.client:""}{item.supplier?"— "+item.supplier:""}</span>
                    <span>{item.amount!=null?"R "+Number(item.amount).toLocaleString("en-ZA",{minimumFractionDigits:2}):""} {item.days?"("+item.days+" days)":""}{item.qty!=null?" qty: "+item.qty:""}</span>
                  </div>
                ))}
                {check.items.length > 5 && <div style={{fontSize:11,color:C.inkMid,marginTop:6}}>…and {check.items.length-5} more</div>}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };
  const renderTrialBalance = () => {
    if (!trialBal) return <div style={{color:C.inkMid,fontSize:13,padding:20}}>Loading trial balance…</div>;
    const TYPE_COLOR = {asset:C.blue,liability:C.red,equity:C.green,revenue:C.green,expense:"#c17d00"};
    const TYPE_ORDER = ["asset","liability","equity","revenue","expense"];
    const grouped = TYPE_ORDER.reduce((acc,t)=>({...acc,[t]:trialBal.accounts.filter(a=>a.type===t)}),[]);
    return (
      <div>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:16}}>
          <div>
            <div style={{fontFamily:"serif",fontSize:20,fontWeight:800,color:C.ink}}>Trial Balance</div>
            <div style={{fontSize:12,color:C.inkMid,marginTop:4}}>All accounts — debits must equal credits</div>
          </div>
          <div style={{textAlign:"right"}}>
            <div style={{fontSize:11,color:C.inkMid}}>Check</div>
            <div style={{fontSize:15,fontWeight:700,color:trialBal.balanced?C.green:C.red}}>
              {trialBal.balanced ? "✅ Balanced" : `❌ Off by R ${Math.abs(trialBal.imbalance).toLocaleString("en-ZA",{minimumFractionDigits:2})}`}
            </div>
          </div>
        </div>
        <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
          <thead>
            <tr style={{background:C.surface}}>
              <th style={{padding:"8px 12px",textAlign:"left",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Code</th>
              <th style={{padding:"8px 12px",textAlign:"left",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Account Name</th>
              <th style={{padding:"8px 12px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Debits</th>
              <th style={{padding:"8px 12px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Credits</th>
              <th style={{padding:"8px 12px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Balance</th>
            </tr>
          </thead>
          <tbody>
            {TYPE_ORDER.map(type => {
              const rows = trialBal.accounts.filter(a=>a.type===type);
              if (!rows.length) return null;
              return [
                <tr key={`hdr-${type}`}>
                  <td colSpan={5} style={{padding:"8px 12px",fontWeight:700,fontSize:11,color:TYPE_COLOR[type]||C.ink,background:`${TYPE_COLOR[type]}15`,textTransform:"uppercase",letterSpacing:0.5,border:`1px solid ${C.border}`}}>
                    {type.charAt(0).toUpperCase()+type.slice(1)}s
                  </td>
                </tr>,
                ...rows.map(row=>(
                  <tr key={row.code}>
                    <td style={{padding:"8px 12px",border:`1px solid ${C.border}`,color:C.inkMid,fontFamily:"monospace",fontSize:12}}>{row.code}</td>
                    <td style={{padding:"8px 12px",border:`1px solid ${C.border}`,color:C.ink}}>{row.name}</td>
                    <td style={{padding:"8px 12px",border:`1px solid ${C.border}`,textAlign:"right",color:C.ink}}>{row.total_debits?`R ${row.total_debits.toLocaleString("en-ZA",{minimumFractionDigits:2})}`:"—"}</td>
                    <td style={{padding:"8px 12px",border:`1px solid ${C.border}`,textAlign:"right",color:C.ink}}>{row.total_credits?`R ${row.total_credits.toLocaleString("en-ZA",{minimumFractionDigits:2})}`:"—"}</td>
                    <td style={{padding:"8px 12px",border:`1px solid ${C.border}`,textAlign:"right",fontWeight:600,color:row.balance>=0?C.ink:C.red}}>R {Math.abs(row.balance).toLocaleString("en-ZA",{minimumFractionDigits:2})}</td>
                  </tr>
                )),
              ];
            })}
            <tr style={{background:C.surface,fontWeight:700}}>
              <td colSpan={2} style={{padding:"10px 12px",border:`1px solid ${C.border}`}}>TOTALS</td>
              <td style={{padding:"10px 12px",border:`1px solid ${C.border}`,textAlign:"right",color:C.blue}}>R {trialBal.total_debits.toLocaleString("en-ZA",{minimumFractionDigits:2})}</td>
              <td style={{padding:"10px 12px",border:`1px solid ${C.border}`,textAlign:"right",color:C.red}}>R {trialBal.total_credits.toLocaleString("en-ZA",{minimumFractionDigits:2})}</td>
              <td style={{padding:"10px 12px",border:`1px solid ${C.border}`,textAlign:"right",color:trialBal.balanced?C.green:C.red}}>{trialBal.balanced?"✅ Balanced":`Off by R ${Math.abs(trialBal.imbalance).toLocaleString("en-ZA",{minimumFractionDigits:2})}`}</td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  };

  const renderJournal = () => {
    if (!journal) return <div style={{color:C.inkMid,fontSize:13,padding:20}}>Loading journal…</div>;
    const SOURCE_ICON = {invoice:"🧾",invoice_payment:"💰",invoice_reversal:"↩️",expense:"💳",expense_reversal:"↩️",payroll:"👥",purchase_order:"📦",po_payment:"🏭",purchase_order_reversal:"↩️",po_payment_reversal:"↩️",manual:"✏️",manual_reversal:"↩️"};
    const toggle = id => setJnlExpanded(prev=>{const n=new Set(prev);n.has(id)?n.delete(id):n.add(id);return n;});

    // ── Manual entry form helpers ─────────────────────────────────────────────
    const addLine = () => setJnlForm(f=>({...f,lines:[...f.lines,{account_id:"",debit:"",credit:"",description:""}]}));
    const removeLine = i => setJnlForm(f=>({...f,lines:f.lines.filter((_,j)=>j!==i)}));
    const updateLine = (i,field,val) => setJnlForm(f=>{const ls=[...f.lines];ls[i]={...ls[i],[field]:val};return{...f,lines:ls};});

    const submitManual = async () => {
      const lines = jnlForm.lines
        .filter(l=>l.account_id)
        .map(l=>({account_id:parseInt(l.account_id),debit:parseFloat(l.debit)||0,credit:parseFloat(l.credit)||0,description:l.description||undefined}));
      const dr = lines.reduce((s,l)=>s+l.debit,0);
      const cr = lines.reduce((s,l)=>s+l.credit,0);
      if (Math.abs(dr-cr)>0.01) { alert(`Entry is unbalanced: DR R${dr.toFixed(2)} ≠ CR R${cr.toFixed(2)}`); return; }
      if (!jnlForm.description) { alert("Description is required."); return; }
      if (jnlForm.auto_reverse && !jnlForm.reversal_date) { alert("Reversal date is required when auto-reverse is on."); return; }
      try {
        await api("/journal/manual",{method:"POST",body:JSON.stringify({
          date:jnlForm.date, description:jnlForm.description, reference:jnlForm.reference||undefined, lines,
          auto_reverse:jnlForm.auto_reverse, reversal_date:jnlForm.auto_reverse?jnlForm.reversal_date:undefined,
        })});
        setJnlForm(null);
        setJournal(await api("/journal/?limit=100"));
      } catch(e) { alert("Failed to save: "+(e.message||e)); }
    };

    return (
      <div>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:16}}>
          <div>
            <div style={{fontFamily:"serif",fontSize:20,fontWeight:800,color:C.ink}}>General Journal</div>
            <div style={{fontSize:12,color:C.inkMid,marginTop:4}}>Every transaction as debit/credit pairs — click any entry to expand</div>
          </div>
          <div style={{display:"flex",gap:8}}>
            <button onClick={()=>setJnlForm(jnlForm?null:{...JNL_EMPTY_FORM,date:new Date().toISOString().slice(0,10)})}
              style={{background:jnlForm?C.surface:C.accent,color:jnlForm?C.inkMid:"#fff",border:`1px solid ${jnlForm?C.border:C.accent}`,borderRadius:8,padding:"7px 14px",fontSize:12,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>
              {jnlForm ? "✕ Cancel" : "+ New Entry"}
            </button>
            <button onClick={async()=>{setLoading(true);try{await api("/journal/backfill",{method:"POST"});setJournal(await api("/journal/?limit=100"));}catch(e){alert("Backfill failed");}finally{setLoading(false);}}}
              style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:8,padding:"7px 14px",fontSize:12,cursor:"pointer",fontFamily:"inherit",color:C.inkMid}}>
              ↻ Re-run backfill
            </button>
          </div>
        </div>

        {/* ── Manual entry form ──────────────────────────────────────────────── */}
        {jnlForm && (
          <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:14,padding:24,marginBottom:20}}>
            <div style={{fontWeight:700,fontSize:15,color:C.ink,marginBottom:16}}>New Manual Journal Entry</div>

            {/* Header fields */}
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12,marginBottom:16}}>
              <div>
                <div style={{fontSize:11,color:C.inkMid,marginBottom:4,fontWeight:600}}>DATE *</div>
                <input type="date" value={jnlForm.date} onChange={e=>setJnlForm(f=>({...f,date:e.target.value}))}
                  style={{width:"100%",border:`1px solid ${C.border}`,borderRadius:8,padding:"8px 10px",fontSize:13,fontFamily:"inherit"}}/>
              </div>
              <div>
                <div style={{fontSize:11,color:C.inkMid,marginBottom:4,fontWeight:600}}>DESCRIPTION *</div>
                <input placeholder="e.g. Month-end accrual" value={jnlForm.description} onChange={e=>setJnlForm(f=>({...f,description:e.target.value}))}
                  style={{width:"100%",border:`1px solid ${C.border}`,borderRadius:8,padding:"8px 10px",fontSize:13,fontFamily:"inherit"}}/>
              </div>
              <div>
                <div style={{fontSize:11,color:C.inkMid,marginBottom:4,fontWeight:600}}>REFERENCE</div>
                <input placeholder="e.g. JNL-001" value={jnlForm.reference} onChange={e=>setJnlForm(f=>({...f,reference:e.target.value}))}
                  style={{width:"100%",border:`1px solid ${C.border}`,borderRadius:8,padding:"8px 10px",fontSize:13,fontFamily:"inherit"}}/>
              </div>
            </div>

            {/* Auto-reverse toggle */}
            <div style={{background:jnlForm.auto_reverse?"#EEF6FF":"#f9f9f9",border:`1px solid ${jnlForm.auto_reverse?C.blue:C.border}`,borderRadius:10,padding:"12px 16px",marginBottom:16,display:"flex",alignItems:"center",gap:16,flexWrap:"wrap"}}>
              <label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer",userSelect:"none"}}>
                <input type="checkbox" checked={jnlForm.auto_reverse} onChange={e=>setJnlForm(f=>({...f,auto_reverse:e.target.checked,reversal_date:""}))}
                  style={{width:16,height:16,accentColor:C.blue}}/>
                <span style={{fontSize:13,fontWeight:600,color:jnlForm.auto_reverse?C.blue:C.inkMid}}>
                  🔄 Auto-reverse this entry
                </span>
              </label>
              {jnlForm.auto_reverse && (
                <div style={{display:"flex",alignItems:"center",gap:8}}>
                  <span style={{fontSize:12,color:C.inkMid}}>Reverse on:</span>
                  <input type="date" value={jnlForm.reversal_date} onChange={e=>setJnlForm(f=>({...f,reversal_date:e.target.value}))}
                    style={{border:`1px solid ${C.blue}`,borderRadius:6,padding:"5px 8px",fontSize:12,fontFamily:"inherit",color:C.ink}}/>
                  <span style={{fontSize:11,color:C.inkMid}}>The mirror entry will be posted automatically on this date.</span>
                </div>
              )}
              {!jnlForm.auto_reverse && (
                <span style={{fontSize:11,color:C.inkMid}}>Use for accruals or prepayments that need to unwind in a future period.</span>
              )}
            </div>

            {/* Line items */}
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:13,marginBottom:12}}>
              <thead>
                <tr style={{background:"#f5f5f5"}}>
                  {["Account","Debit (R)","Credit (R)","Memo",""].map(h=>(
                    <th key={h} style={{padding:"7px 10px",textAlign:"left",fontSize:10,color:C.inkMid,fontWeight:700,letterSpacing:0.5,textTransform:"uppercase",borderBottom:`1px solid ${C.border}`}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {jnlForm.lines.map((line,i)=>(
                  <tr key={i}>
                    <td style={{padding:"5px 6px",width:"40%"}}>
                      <select value={line.account_id} onChange={e=>updateLine(i,"account_id",e.target.value)}
                        style={{width:"100%",border:`1px solid ${C.border}`,borderRadius:6,padding:"6px 8px",fontSize:12,fontFamily:"inherit"}}>
                        <option value="">— select account —</option>
                        {jnlAccounts.map(a=>(
                          <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{padding:"5px 6px",width:"15%"}}>
                      <input type="number" min="0" step="0.01" placeholder="0.00" value={line.debit}
                        onChange={e=>updateLine(i,"debit",e.target.value)}
                        style={{width:"100%",border:`1px solid ${C.border}`,borderRadius:6,padding:"6px 8px",fontSize:12,fontFamily:"inherit",textAlign:"right"}}/>
                    </td>
                    <td style={{padding:"5px 6px",width:"15%"}}>
                      <input type="number" min="0" step="0.01" placeholder="0.00" value={line.credit}
                        onChange={e=>updateLine(i,"credit",e.target.value)}
                        style={{width:"100%",border:`1px solid ${C.border}`,borderRadius:6,padding:"6px 8px",fontSize:12,fontFamily:"inherit",textAlign:"right"}}/>
                    </td>
                    <td style={{padding:"5px 6px",width:"25%"}}>
                      <input placeholder="Optional memo" value={line.description}
                        onChange={e=>updateLine(i,"description",e.target.value)}
                        style={{width:"100%",border:`1px solid ${C.border}`,borderRadius:6,padding:"6px 8px",fontSize:12,fontFamily:"inherit"}}/>
                    </td>
                    <td style={{padding:"5px 6px",textAlign:"center"}}>
                      {jnlForm.lines.length > 2 &&
                        <button onClick={()=>removeLine(i)} style={{background:"none",border:"none",color:C.red,cursor:"pointer",fontSize:16,padding:"0 4px"}}>✕</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Running totals + actions */}
            {(()=>{
              const dr=jnlForm.lines.reduce((s,l)=>s+(parseFloat(l.debit)||0),0);
              const cr=jnlForm.lines.reduce((s,l)=>s+(parseFloat(l.credit)||0),0);
              const balanced=Math.abs(dr-cr)<0.01;
              return (
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",flexWrap:"wrap",gap:12}}>
                  <button onClick={addLine}
                    style={{background:"none",border:`1px dashed ${C.border}`,borderRadius:8,padding:"6px 14px",fontSize:12,cursor:"pointer",color:C.inkMid,fontFamily:"inherit"}}>
                    + Add line
                  </button>
                  <div style={{display:"flex",alignItems:"center",gap:16}}>
                    <span style={{fontSize:12,color:balanced?C.green:C.red,fontWeight:600}}>
                      {balanced?"✅ Balanced":`DR R${dr.toFixed(2)} ≠ CR R${cr.toFixed(2)}`}
                    </span>
                    <button onClick={submitManual} disabled={!balanced}
                      style={{background:balanced?C.accent:"#ccc",color:"#fff",border:"none",borderRadius:8,padding:"8px 20px",fontSize:13,cursor:balanced?"pointer":"not-allowed",fontFamily:"inherit",fontWeight:700}}>
                      Post Entry{jnlForm.auto_reverse?" + Schedule Reversal":""}
                    </button>
                  </div>
                </div>
              );
            })()}
          </div>
        )}

        {journal.length === 0 && !jnlForm && (
          <div style={{textAlign:"center",padding:"40px 20px",color:C.inkMid}}>
            <div style={{fontSize:32,marginBottom:12}}>📒</div>
            <div style={{fontSize:15,fontWeight:600,marginBottom:6}}>No journal entries yet</div>
            <div style={{fontSize:13}}>Journal entries are created automatically when you add invoices, expenses or process payroll.</div>
          </div>
        )}

        {journal.map(entry => {
          const isReversal = entry.source && entry.source.endsWith("_reversal");
          const hasScheduledReversal = entry.auto_reverse && entry.reversal_date;
          const alreadyReversed = journal.some(e=>e.is_reversal_of===entry.id);
          return (
            <div key={entry.id} style={{border:`1px solid ${isReversal?"#FFC107":entry.is_reversal_of?C.border:C.border}`,borderLeft:`3px solid ${isReversal?C.gold:hasScheduledReversal?C.blue:C.border}`,borderRadius:10,marginBottom:8,overflow:"hidden",opacity:isReversal?0.85:1}}>
              <div onClick={()=>toggle(entry.id)} style={{display:"flex",alignItems:"center",gap:12,padding:"10px 14px",cursor:"pointer",background:jnlExpanded.has(entry.id)?C.accentLt:C.surface}}>
                <span style={{fontSize:18}}>{SOURCE_ICON[entry.source]||"📝"}</span>
                <div style={{flex:1}}>
                  <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
                    <span style={{fontSize:13,fontWeight:600,color:C.ink}}>{entry.description}</span>
                    {isReversal && <span style={{fontSize:10,background:"#FFF3CD",color:"#856404",borderRadius:20,padding:"2px 8px",fontWeight:700}}>REVERSAL</span>}
                    {hasScheduledReversal && !alreadyReversed && <span style={{fontSize:10,background:"#EEF6FF",color:C.blue,borderRadius:20,padding:"2px 8px",fontWeight:700}}>🔄 Reverses {entry.reversal_date}</span>}
                    {hasScheduledReversal && alreadyReversed && <span style={{fontSize:10,background:C.greenLt,color:C.green,borderRadius:20,padding:"2px 8px",fontWeight:700}}>✓ Reversed</span>}
                    {entry.is_reversal_of && <span style={{fontSize:10,background:"#f5f5f5",color:C.inkMid,borderRadius:20,padding:"2px 8px"}}>reversal of #{entry.is_reversal_of}</span>}
                  </div>
                  <div style={{fontSize:11,color:C.inkMid,marginTop:2}}>{entry.date} · {entry.reference||"—"} · {entry.source}</div>
                </div>
                <div style={{fontSize:11,color:C.inkMid}}>{jnlExpanded.has(entry.id)?"▲":"▼"}</div>
              </div>
              {jnlExpanded.has(entry.id) && (
                <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                  <thead>
                    <tr style={{background:"#f8f8f8"}}>
                      <th style={{padding:"6px 14px",textAlign:"left",color:C.inkMid,fontWeight:600,borderTop:`1px solid ${C.border}`}}>Account</th>
                      <th style={{padding:"6px 14px",textAlign:"right",color:C.inkMid,fontWeight:600,borderTop:`1px solid ${C.border}`}}>Debit</th>
                      <th style={{padding:"6px 14px",textAlign:"right",color:C.inkMid,fontWeight:600,borderTop:`1px solid ${C.border}`}}>Credit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entry.lines.map((line,i)=>(
                      <tr key={i} style={{borderTop:`1px solid ${C.border}`}}>
                        <td style={{padding:"6px 14px",color:C.ink}}><span style={{fontFamily:"monospace",color:C.inkMid,marginRight:8}}>{line.account_code}</span>{line.account_name}{line.description?<span style={{color:C.inkMid}}> — {line.description}</span>:""}</td>
                        <td style={{padding:"6px 14px",textAlign:"right",color:C.blue,fontWeight:line.debit?600:400}}>{line.debit?`R ${line.debit.toLocaleString("en-ZA",{minimumFractionDigits:2})}`:"—"}</td>
                        <td style={{padding:"6px 14px",textAlign:"right",color:C.red,fontWeight:line.credit?600:400}}>{line.credit?`R ${line.credit.toLocaleString("en-ZA",{minimumFractionDigits:2})}`:"—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const renderCF = () => {
    const cf = cfData || {period,operating:{cash_receipts_from_customers:0,cash_paid_to_suppliers:0,payroll_net_pay:0,sars_paye_uif_sdl:0,net_cash_from_operations:0},investing:{net_cash_from_investing:0},financing:{net_cash_from_financing:0},net_increase_in_cash:0};
    const op = cf.operating;
    return (
      <div>
        <div style={{display:"flex",justifyContent:"space-between",marginBottom:24}}>
          <div><div style={{fontFamily:"serif",fontSize:20,fontWeight:800,color:C.ink}}>Cash Flow Statement</div><div style={{fontSize:12,color:C.inkMid,marginTop:4}}>For the month ended {cf.period}</div></div>
          <ExcelBtn filename="cash-flow.csv" data={[{Item:"Cash Receipts",Amount:op.cash_receipts_from_customers},{Item:"Cash Paid",Amount:op.cash_paid_to_suppliers},{Item:"Payroll",Amount:op.payroll_net_pay},{Item:"SARS",Amount:op.sars_paye_uif_sdl},{Item:"Net Operating",Amount:op.net_cash_from_operations},{Item:"Net Investing",Amount:cf.investing.net_cash_from_investing},{Item:"Net Financing",Amount:cf.financing.net_cash_from_financing},{Item:"Net Change",Amount:cf.net_increase_in_cash}]}/>
        </div>
        <div style={{fontSize:12,fontWeight:700,color:C.ink,marginBottom:8}}>Operating Activities</div>
        <ReportRow label="Cash receipts from customers"       value={op.cash_receipts_from_customers}  color={C.green} indent/>
        <ReportRow label="Cash paid to suppliers"             value={op.cash_paid_to_suppliers}        indent/>
        <ReportRow label="Payroll net pay"                    value={op.payroll_net_pay}               indent/>
        <ReportRow label="SARS PAYE, UIF and SDL"             value={op.sars_paye_uif_sdl}            indent/>
        <ReportRow label="Net cash from operating activities" value={op.net_cash_from_operations} bold border color={op.net_cash_from_operations>=0?C.green:C.red}/>
        <div style={{fontSize:12,fontWeight:700,color:C.ink,marginTop:16,marginBottom:8}}>Investing Activities</div>
        <ReportRow label="Net cash from investing" value={cf.investing.net_cash_from_investing} bold color={C.inkMid}/>
        <div style={{fontSize:12,fontWeight:700,color:C.ink,marginTop:16,marginBottom:8}}>Financing Activities</div>
        <ReportRow label="Net cash from financing" value={cf.financing.net_cash_from_financing} bold color={C.inkMid}/>
        <ReportRow label="Net increase in cash"    value={cf.net_increase_in_cash} bold border large color={cf.net_increase_in_cash>=0?C.accent:C.red}/>
      </div>
    );
  };
  const openMgmtDrill = async (type) => {
    if (mgmtDrill && mgmtDrill.type === type) { setMgmtDrill(null); return; } // toggle off
    setMgmtDrillLoading(true);
    setMgmtDrill({type, title:"", cols:[], rows:[], total:0, color:C.ink});
    const toZarD = i => (i.currency && i.currency !== "ZAR")
      ? (i.paid_amount_zar || (i.total_amount||i.amount||0)*(i.exchange_rate||1))
      : (i.total_amount||i.amount||0);
    try {
      const m = mgmt;
      const pl = m ? m.pl : null;
      if (type === "revenue") {
        const invs = await api("/invoices");
        const dfrom = new Date(dateFrom); const dto = new Date(dateTo);
        const rows = invs.filter(i => {
          if (i.status !== "paid") return false;
          const d = new Date(i.paid_date || i.created_at || 0);
          return d >= dfrom && d <= dto;
        }).sort((a,b)=>new Date(b.paid_date||0)-new Date(a.paid_date||0));
        setMgmtDrill({type, title:"Revenue — Paid Invoices (period)", color:C.green,
          total: rows.reduce((s,i)=>s+toZarD(i),0),
          cols:["Invoice","Client","Currency","Amount (ZAR)","Paid Date"],
          rows: rows.map(i=>[i.invoice_number||i.id, i.client_name||i.client,
            i.currency||"ZAR", fmt(toZarD(i)),
            i.paid_date ? new Date(i.paid_date).toLocaleDateString("en-ZA") : "—"])});
      } else if (type === "profit") {
        // Use management accounts P&L breakdown
        const bd = pl ? (pl.expense_breakdown || {}) : {};
        const cogs = pl ? (pl.po_cogs||0) : 0;
        const rows = [
          ["Revenue", fmt(pl ? pl.revenue : 0), ""],
          ["Cost of Sales (POs)", fmt(cogs), "deduct"],
          ["Gross Profit", fmt(pl ? pl.revenue - cogs : 0), "subtotal"],
          ...Object.entries(bd).filter(([k])=>k!=="Cost of Sales (POs)").sort((a,b)=>b[1]-a[1])
            .map(([k,v])=>[k, fmt(v), "deduct"]),
          ["Total Operating Expenses", fmt(Object.entries(bd).filter(([k])=>k!=="Cost of Sales (POs)").reduce((s,[,v])=>s+v,0)), "subtotal"],
          ["Payroll Cost", fmt(pl ? pl.payroll_cost : 0), "deduct"],
          ["Net Profit Before Tax", fmt(pl ? pl.net_profit + (pl.tax_provision||0) : 0), "subtotal"],
          ["Tax Provision (27%)", fmt(pl ? pl.tax_provision : 0), "deduct"],
          ["Net Profit After Tax", fmt(pl ? pl.net_profit : 0), "total"],
        ];
        setMgmtDrill({type, title:"Net Profit — P&L Breakdown (period)", color:pl&&pl.net_profit>=0?C.accent:C.red,
          total: pl ? pl.net_profit : 0,
          cols:["Line Item","Amount",""],
          rows});
      } else if (type === "outstanding") {
        const invs = await api("/invoices");
        const today = new Date();
        const rows = invs.filter(i=>["pending","sent","overdue"].includes(i.status))
          .sort((a,b)=>new Date(a.due_date||0)-new Date(b.due_date||0));
        setMgmtDrill({type, title:"Outstanding — Pending & Overdue Invoices", color:C.gold,
          total: rows.reduce((s,i)=>s+toZarD(i),0),
          cols:["Invoice","Client","Amount (ZAR)","Due Date","Status"],
          rows: rows.map(i=>{
            const due = i.due_date ? new Date(i.due_date) : null;
            const overdue = due ? Math.max(0,Math.floor((today-due)/(1000*60*60*24))) : 0;
            return [i.invoice_number||i.id, i.client_name||i.client, fmt(toZarD(i)),
              due ? due.toLocaleDateString("en-ZA") : "—",
              overdue > 0 ? `${overdue}d overdue` : i.status];
          })});
      } else if (type === "payroll") {
        const emps = await api("/employees");
        const active = emps.filter(e=>e.is_active!==false);
        setMgmtDrill({type, title:"Payroll — Active Employees", color:C.blue,
          total: pl ? pl.payroll_cost : active.reduce((s,e)=>s+calcPayroll(e.gross_salary).totalCost,0),
          cols:["Employee","Position","Gross Salary","Net Pay","Total Cost"],
          rows: active.map(e=>{
            const p = calcPayroll(e.gross_salary);
            return [e.name, e.position||"—", fmt(e.gross_salary), fmt(p.netPay), fmt(p.totalCost)];
          })});
      }
    } catch(err) { setMgmtDrill(null); }
    setMgmtDrillLoading(false);
  };

  const renderMgmt = () => {
    const m    = mgmt;
    const pl   = m ? m.pl : {revenue:totalRevenue,total_expenses:totalExpenses,gross_profit:grossProfit,payroll_cost:totalPayroll,ebit:netProfit,tax_provision:taxProvision,net_profit:netAfterTax,gross_margin_pct:totalRevenue?Math.round(grossProfit/totalRevenue*100):0,net_margin_pct:totalRevenue?Math.round(netAfterTax/totalRevenue*100):0,expense_breakdown:{}};
    const kpis = m ? m.kpis : {revenue:totalRevenue,net_profit:netAfterTax,outstanding:0,overdue_count:0,employee_count:MOCK_EMPLOYEES.length,payroll_cost:totalPayroll,gross_margin_pct:0,net_margin_pct:0};
    const trend = m ? m.trend : live.trend || REVENUE_DATA;
    const expBreakdown = pl.expense_breakdown || {};
    return (
      <div>
        {m && <div style={{fontSize:11,color:C.inkMid,marginBottom:10,fontWeight:500}}>Period: {m.period}</div>}
        <div style={{display:"flex",gap:12,marginBottom:mgmtDrill?12:20,flexWrap:"wrap"}}>
          <KPI label="Revenue"     value={fmt(kpis.revenue)}      color={C.green}                           icon="💰" active={mgmtDrill?.type==="revenue"}     onClick={()=>openMgmtDrill("revenue")}     sub={"Gross margin "+kpis.gross_margin_pct+"%"}/>
          <KPI label="Net Profit"  value={fmt(kpis.net_profit)}   color={kpis.net_profit>=0?C.accent:C.red} icon="📊" active={mgmtDrill?.type==="profit"}      onClick={()=>openMgmtDrill("profit")}      sub={"Net margin "+kpis.net_margin_pct+"%"}/>
          <KPI label="Outstanding" value={fmt(kpis.outstanding)}  color={C.gold}                            icon="⏳" active={mgmtDrill?.type==="outstanding"} onClick={()=>openMgmtDrill("outstanding")} sub={kpis.overdue_count+" overdue"}/>
          <KPI label="Payroll"     value={fmt(kpis.payroll_cost)} color={C.blue}                            icon="👥" active={mgmtDrill?.type==="payroll"}     onClick={()=>openMgmtDrill("payroll")}     sub={kpis.employee_count+" employees"}/>
        </div>

        {/* Drill-down panel */}
        {(mgmtDrill || mgmtDrillLoading) && (
          <div style={{background:C.surface,border:"2px solid "+(mgmtDrill?.color||C.accent)+"40",borderRadius:16,padding:20,marginBottom:20}}>
            {mgmtDrillLoading ? (
              <div style={{textAlign:"center",padding:24,color:C.inkMid,fontSize:13}}>Loading…</div>
            ) : mgmtDrill && (
              <>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
                  <div style={{fontSize:13,fontWeight:700,color:mgmtDrill.color}}>{mgmtDrill.title}</div>
                  <div style={{display:"flex",alignItems:"center",gap:12}}>
                    {mgmtDrill.total !== undefined && mgmtDrill.type !== "profit" && (
                      <div style={{fontSize:15,fontWeight:800,color:mgmtDrill.color}}>{fmt(mgmtDrill.total)}</div>
                    )}
                    <button onClick={()=>setMgmtDrill(null)} style={{background:"none",border:"none",fontSize:18,cursor:"pointer",color:C.inkMid,lineHeight:1}}>✕</button>
                  </div>
                </div>
                <div style={{overflowX:"auto"}}>
                  <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                    <thead>
                      <tr style={{background:C.bg}}>
                        {mgmtDrill.cols.map((c,i)=>(
                          <th key={i} style={{padding:"8px 12px",textAlign:"left",fontSize:10,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase",whiteSpace:"nowrap",borderBottom:"1px solid "+C.border}}>{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {mgmtDrill.rows.length === 0
                        ? <tr><td colSpan={mgmtDrill.cols.length} style={{padding:"20px 12px",textAlign:"center",color:C.inkMid}}>No data for this period</td></tr>
                        : mgmtDrill.rows.map((row,ri)=>{
                            const tag = Array.isArray(row) ? row[row.length-1] : "";
                            const isCols = !["deduct","subtotal","total",""].includes(tag) || mgmtDrill.type !== "profit";
                            const displayRow = mgmtDrill.type === "profit" ? row.slice(0,-1) : row;
                            const bg = tag==="total" ? C.accentLt : tag==="subtotal" ? C.bg : "transparent";
                            const fw = (tag==="total"||tag==="subtotal") ? 700 : 400;
                            return (
                              <tr key={ri} style={{borderBottom:"1px solid "+C.border+"20",background:bg}}>
                                {displayRow.map((cell,ci)=>(
                                  <td key={ci} style={{padding:"10px 12px",color:ci===1&&tag==="deduct"?C.red:C.ink,fontWeight:ci===0?fw:ci===1?fw:400}}>{cell}</td>
                                ))}
                              </tr>
                            );
                          })
                      }
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}

        <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:20,marginBottom:20}}>
          <div style={{fontSize:13,fontWeight:700,color:C.ink,marginBottom:16}}>6-Month Revenue vs Expenses</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={trend} barGap={4}>
              <CartesianGrid stroke={C.border} strokeDasharray="3 3" vertical={false}/>
              <XAxis dataKey="month" tick={{fontSize:10,fill:C.inkMid}} tickLine={false} axisLine={false}/>
              <YAxis tick={{fontSize:10,fill:C.inkMid}} tickLine={false} axisLine={false} width={45}/>
              <Tooltip content={<Tooltip2/>}/>
              <Bar dataKey="revenue"  name="Revenue"  fill={C.green}  radius={[4,4,0,0]}/>
              <Bar dataKey="expenses" name="Expenses" fill={C.accent} radius={[4,4,0,0]}/>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
          <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:20}}>
            <div style={{fontSize:13,fontWeight:700,color:C.ink,marginBottom:16}}>Profit and Loss</div>
            <ReportRow label="Revenue"              value={pl.revenue}         bold color={C.green}/>
            <ReportRow label="Operating Expenses"  value={-pl.total_expenses} indent/>
            <ReportRow label="Operating Profit"    value={pl.gross_profit}    bold border/>
            <ReportRow label="Payroll Cost"        value={-pl.payroll_cost}   indent/>
            <ReportRow label="Net Profit Before Tax" value={pl.ebit}          bold border color={pl.ebit>=0?C.ink:C.red}/>
            <ReportRow label="Tax Provision 27%"   value={-pl.tax_provision}  indent/>
            <ReportRow label="Net Profit After Tax" value={pl.net_profit}     bold border large color={pl.net_profit>=0?C.accent:C.red}/>
          </div>
          <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:20}}>
            <div style={{fontSize:13,fontWeight:700,color:C.ink,marginBottom:16}}>Expense Breakdown</div>
            {Object.keys(expBreakdown).length > 0
              ? Object.entries(expBreakdown).sort((a,b)=>b[1]-a[1]).map(([cat,amt])=>(
                  <div key={cat} style={{display:"flex",justifyContent:"space-between",padding:"8px 0",borderBottom:"1px solid "+C.border+"20"}}>
                    <span style={{fontSize:12,color:C.ink}}>{cat}</span>
                    <span style={{fontSize:12,fontWeight:700,color:C.red}}>{fmt(amt)}</span>
                  </div>
                ))
              : <div style={{fontSize:12,color:C.inkDim,padding:"20px 0",textAlign:"center"}}>No expense data for this period</div>
            }
          </div>
        </div>
      </div>
    );
  };
  const renderVat201 = () => {
    const v = vat201;
    const now = new Date();
    const out  = v ? v.output : {field_1a_standard_supplies_excl_vat:totalRevenue*100/115,field_4a_output_vat:totalRevenue*15/115,invoice_count:0,total_invoiced_incl_vat:totalRevenue,vat_recorded_on_invoices:0,field_1b_zero_rated_supplies:0};
    const inp  = v ? v.input  : {field_14_input_vat:totalExpenses*15/115,total_expenses_incl_vat:totalExpenses,total_expenses_excl_vat:totalExpenses*100/115,expense_count:0,expense_breakdown:{},note:""};
    const net  = v ? v.net    : {field_15_net_vat:(totalRevenue-totalExpenses)*15/115,status:(totalRevenue>totalExpenses?"payable":"refundable"),amount:Math.abs((totalRevenue-totalExpenses)*15/115)};
    const periodLabel = v ? v.period : now.toLocaleDateString("en-ZA",{month:"long",year:"numeric"});
    const dueDate     = v ? v.due_date : "";
    const isPayable   = net.status === "payable";
    return (
      <div>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:20}}>
          <div>
            <h2 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:0}}>VAT201 Return</h2>
            <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>VAT @ 15% — Period: {periodLabel}{dueDate?" — Due: ":""}<strong style={{color:C.red}}>{dueDate}</strong></p>
          </div>
          <div style={{display:"flex",alignItems:"center",gap:10}}>
            <div style={{display:"flex",alignItems:"center",gap:8}}>
              <span style={{fontSize:12,color:C.inkMid,fontWeight:600}}>Period:</span>
              <input type="month" value={vatPeriod} onChange={e=>{setVatPeriod(e.target.value);setVat201(null);}} style={{padding:"7px 12px",border:"1px solid "+C.border,borderRadius:8,fontSize:12,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
              <button onClick={()=>api("/reports/vat201?period="+vatPeriod).then(setVat201).catch(()=>null)} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"8px 16px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Load</button>
            </div>
            <a href="https://efiling.sars.gov.za" target="_blank" rel="noreferrer" style={{background:C.blue,color:"#fff",padding:"8px 14px",borderRadius:8,fontSize:12,fontWeight:700,textDecoration:"none"}}>Submit on eFiling</a>
          </div>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12,marginBottom:24}}>
          <div style={{background:C.greenLt,border:"1px solid "+C.green+"30",borderRadius:14,padding:20}}>
            <div style={{fontSize:10,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:8}}>Output VAT (Field 4A)</div>
            <div style={{fontFamily:"serif",fontSize:28,fontWeight:800,color:C.green}}>{fmt(out.field_4a_output_vat)}</div>
            <div style={{fontSize:11,color:C.inkMid,marginTop:4}}>VAT collected on {out.invoice_count} invoice{out.invoice_count!==1?"s":""}</div>
          </div>
          <div style={{background:C.accentLt,border:"1px solid "+C.accent+"30",borderRadius:14,padding:20}}>
            <div style={{fontSize:10,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:8}}>Input VAT (Field 14)</div>
            <div style={{fontFamily:"serif",fontSize:28,fontWeight:800,color:C.accent}}>{fmt(inp.field_14_input_vat)}</div>
            <div style={{fontSize:11,color:C.inkMid,marginTop:4}}>VAT on {inp.expense_count} expense{inp.expense_count!==1?"s":""} (est.)</div>
          </div>
          <div style={{background:isPayable?C.redLt:C.greenLt,border:"1px solid "+(isPayable?C.red:C.green)+"30",borderRadius:14,padding:20}}>
            <div style={{fontSize:10,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:8}}>Net VAT (Field 15)</div>
            <div style={{fontFamily:"serif",fontSize:28,fontWeight:800,color:isPayable?C.red:C.green}}>{fmt(net.amount)}</div>
            <div style={{fontSize:11,color:isPayable?C.red:C.green,marginTop:4,fontWeight:700}}>{isPayable?"Payable to SARS":"Refund due from SARS"}</div>
          </div>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,marginBottom:20}}>
          <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:24}}>
            <div style={{fontSize:13,fontWeight:700,color:C.green,marginBottom:16}}>Section A — Output Tax</div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:"1px solid "+C.border+"20",fontSize:13}}>
              <span style={{color:C.inkMid}}>Field 1(a) Standard rated supplies (excl. VAT)</span>
              <span style={{fontWeight:700}}>{fmt(out.field_1a_standard_supplies_excl_vat)}</span>
            </div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:"1px solid "+C.border+"20",fontSize:13}}>
              <span style={{color:C.inkMid}}>Field 1(b) Zero-rated supplies</span>
              <span style={{fontWeight:700}}>{fmt(out.field_1b_zero_rated_supplies)}</span>
            </div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:"2px solid "+C.border,fontSize:13}}>
              <span style={{color:C.inkMid}}>Total invoiced (incl. VAT)</span>
              <span style={{fontWeight:700}}>{fmt(out.total_invoiced_incl_vat)}</span>
            </div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"12px 0",fontSize:14,fontWeight:800}}>
              <span style={{color:C.green}}>Field 4(a) Output VAT</span>
              <span style={{color:C.green}}>{fmt(out.field_4a_output_vat)}</span>
            </div>
          </div>
          <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:24}}>
            <div style={{fontSize:13,fontWeight:700,color:C.accent,marginBottom:16}}>Section B — Input Tax</div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:"1px solid "+C.border+"20",fontSize:13}}>
              <span style={{color:C.inkMid}}>Total expenses (incl. VAT)</span>
              <span style={{fontWeight:700}}>{fmt(inp.total_expenses_incl_vat)}</span>
            </div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:"1px solid "+C.border+"20",fontSize:13}}>
              <span style={{color:C.inkMid}}>Total expenses (excl. VAT)</span>
              <span style={{fontWeight:700}}>{fmt(inp.total_expenses_excl_vat)}</span>
            </div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:"2px solid "+C.border,fontSize:13}}>
              <span style={{color:C.inkMid}}>Estimated input VAT (15/115)</span>
              <span style={{fontWeight:700}}>{fmt(inp.field_14_input_vat)}</span>
            </div>
            <div style={{display:"flex",justifyContent:"space-between",padding:"12px 0",fontSize:14,fontWeight:800}}>
              <span style={{color:C.accent}}>Field 14 Input VAT claimed</span>
              <span style={{color:C.accent}}>{fmt(inp.field_14_input_vat)}</span>
            </div>
          </div>
        </div>
        <div style={{background:isPayable?C.redLt:C.greenLt,border:"2px solid "+(isPayable?C.red:C.green),borderRadius:16,padding:24,marginBottom:20}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <div>
              <div style={{fontSize:14,fontWeight:700,color:isPayable?C.red:C.green,marginBottom:4}}>Field 15 — Net VAT {isPayable?"Payable":"Refundable"}</div>
              <div style={{fontSize:12,color:C.inkMid}}>Output VAT {fmt(out.field_4a_output_vat)} {isPayable?"minus":"minus"} Input VAT {fmt(inp.field_14_input_vat)}</div>
              {dueDate && <div style={{fontSize:12,fontWeight:700,color:isPayable?C.red:C.green,marginTop:8}}>Due date: {dueDate}</div>}
            </div>
            <div style={{fontFamily:"serif",fontSize:36,fontWeight:800,color:isPayable?C.red:C.green}}>{fmt(net.amount)}</div>
          </div>
        </div>
        {Object.keys(inp.expense_breakdown||{}).length > 0 && (
          <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:24,marginBottom:20}}>
            <div style={{fontSize:13,fontWeight:700,color:C.ink,marginBottom:16}}>Expense Breakdown (for VAT audit trail)</div>
            {Object.entries(inp.expense_breakdown).sort((a,b)=>b[1]-a[1]).map(([cat,amt])=>(
              <div key={cat} style={{display:"flex",justifyContent:"space-between",padding:"8px 0",borderBottom:"1px solid "+C.border+"20",fontSize:13}}>
                <span style={{color:C.ink}}>{cat}</span>
                <div style={{textAlign:"right"}}>
                  <span style={{fontWeight:600}}>{fmt(amt)}</span>
                  <span style={{color:C.inkDim,fontSize:11,marginLeft:12}}>VAT est. {fmt(amt*15/115)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
        <div style={{background:C.goldLt,border:"1px solid "+C.gold+"40",borderRadius:12,padding:16,fontSize:12,color:C.inkMid,lineHeight:1.8}}>
          <strong style={{color:C.ink}}>VAT201 Notes</strong><br/>
          Input VAT is estimated at 15/115 of total expenses assuming all are VAT-inclusive. Exclude zero-rated and exempt purchases before submitting.<br/>
          VAT is due by the 25th of the month following the tax period. Late submission incurs a 10% penalty plus interest.<br/>
          Ensure your VAT registration number appears on all tax invoices issued and received.
        </div>
      </div>
    );
  };

  const renderProvTax = () => {
    const p = provTax;
    const now = new Date();
    const ytd   = p ? p.ytd   : {revenue:totalRevenue, expenses:totalExpenses, payroll_cost:totalPayroll, taxable_income:totalRevenue-totalExpenses-totalPayroll};
    const ann   = p ? p.annualised : {taxable_income:Math.max(0,(totalRevenue-totalExpenses-totalPayroll)/now.getMonth()*12), estimated_tax:0};
    const irp6  = p ? p.irp6  : {first_payment:0, first_due:"31 August "+now.getFullYear(), second_payment:0, second_due:"28 February "+(now.getFullYear()+1)};
    const notes = p ? p.notes : [];
    const taxable = ytd.taxable_income;
    const estTax  = ann.estimated_tax || Math.max(0, ann.taxable_income * 0.27);
    return (
      <div>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:20}}>
          <div>
            <h2 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:0}}>Provisional Tax (IRP6)</h2>
            <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>Corporate tax @ 27% — Tax year {p?p.tax_year:now.getFullYear()+"/"+(now.getFullYear()+1)}</p>
          </div>
          <a href="https://efiling.sars.gov.za" target="_blank" rel="noreferrer" style={{background:C.accent,color:"#fff",padding:"8px 16px",borderRadius:8,fontSize:12,fontWeight:700,textDecoration:"none"}}>Submit IRP6 on eFiling</a>
        </div>
        <div style={{display:"flex",gap:12,marginBottom:20,flexWrap:"wrap"}}>
          <KPI label="YTD Revenue"         value={fmt(ytd.revenue)}          color={C.green}  icon="Revenue" sub="Year to date"/>
          <KPI label="YTD Expenses"        value={fmt(ytd.expenses+ytd.payroll_cost)} color={C.red} icon="Expenses" sub="Incl. payroll"/>
          <KPI label="Taxable Income"      value={fmt(Math.max(0,taxable))}  color={taxable>=0?C.ink:C.red} icon="Tax" sub="Est. annual basis"/>
          <KPI label="Estimated Tax (27%)" value={fmt(estTax)}               color={C.accent} icon="SARS" sub="Before deductions"/>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,marginBottom:20}}>
          <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:24}}>
            <div style={{fontSize:13,fontWeight:700,color:C.ink,marginBottom:16}}>YTD Income Statement</div>
            <ReportRow label="Revenue (invoiced + paid)"  value={ytd.revenue}       bold color={C.green}/>
            <ReportRow label="Less: Operating Expenses"   value={-ytd.expenses}     indent/>
            <ReportRow label="Less: Payroll Cost"         value={-ytd.payroll_cost} indent/>
            <ReportRow label="YTD Taxable Income"         value={taxable} bold border color={taxable>=0?C.ink:C.red}/>
            <ReportRow label="Annualised Taxable Income"  value={ann.taxable_income} bold color={C.inkMid}/>
            <ReportRow label="Estimated Annual Tax (27%)" value={estTax} bold border large color={C.accent}/>
          </div>
          <div>
            <div style={{background:C.surface,border:"2px solid "+C.accent,borderRadius:16,padding:24,marginBottom:12}}>
              <div style={{fontSize:11,fontWeight:700,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:12}}>First IRP6 Payment</div>
              <div style={{fontFamily:"serif",fontSize:28,fontWeight:800,color:C.accent,marginBottom:6}}>{fmt(irp6.first_payment)}</div>
              <div style={{fontSize:12,color:C.inkMid}}>50% of estimated annual tax</div>
              <div style={{marginTop:12,padding:"8px 12px",background:C.redLt,borderRadius:8,fontSize:12,fontWeight:700,color:C.red}}>Due: {irp6.first_due}</div>
            </div>
            <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:24}}>
              <div style={{fontSize:11,fontWeight:700,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:12}}>Second IRP6 Payment</div>
              <div style={{fontFamily:"serif",fontSize:28,fontWeight:800,color:C.ink,marginBottom:6}}>{fmt(irp6.second_payment)}</div>
              <div style={{fontSize:12,color:C.inkMid}}>Balance of estimated annual tax</div>
              <div style={{marginTop:12,padding:"8px 12px",background:C.goldLt,borderRadius:8,fontSize:12,fontWeight:700,color:C.gold}}>Due: {irp6.second_due}</div>
            </div>
          </div>
        </div>
        {notes.length > 0 && (
          <div style={{background:C.bg,border:"1px solid "+C.border,borderRadius:12,padding:16}}>
            <div style={{fontSize:12,fontWeight:700,color:C.ink,marginBottom:10}}>Important Notes</div>
            {notes.map((n,i)=>(
              <div key={i} style={{fontSize:12,color:C.inkMid,marginBottom:6,display:"flex",gap:8}}>
                <span style={{color:C.gold}}>•</span>{n}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-end",marginBottom:20}}>
        <div>
          <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:0}}>Reports</h2>
          <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>SARS-ready financial statements — {periodLabel}</p>
        </div>
        <PrintBtn onClick={()=>{const el=document.getElementById("report-print-area");if(!el)return;const w=window.open("","_blank");w.document.write("<html><body>"+el.innerHTML+"</body></html>");w.document.close();w.print();}}/>
      </div>

      {/* Date range selector */}
      <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:12,padding:"14px 18px",marginBottom:20,display:"flex",gap:12,alignItems:"center",flexWrap:"wrap"}}>
        <span style={{fontSize:11,fontWeight:700,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5}}>Period</span>
        <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
          {PRESETS.map(p => (
            <button key={p.label} onClick={()=>handlePreset(p.label)}
              style={{padding:"6px 14px",borderRadius:20,border:"1px solid "+(preset===p.label?C.accent:C.border),background:preset===p.label?C.accentLt:"transparent",color:preset===p.label?C.accent:C.inkMid,fontSize:12,fontWeight:preset===p.label?700:400,cursor:"pointer",fontFamily:"inherit"}}>
              {p.label}
            </button>
          ))}
        </div>
        {preset === "Custom" && (
          <div style={{display:"flex",gap:8,alignItems:"center",marginLeft:4}}>
            <input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}
              style={{padding:"6px 10px",border:"1px solid "+C.border,borderRadius:8,fontSize:12,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
            <span style={{fontSize:12,color:C.inkMid}}>to</span>
            <input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}
              style={{padding:"6px 10px",border:"1px solid "+C.border,borderRadius:8,fontSize:12,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
          </div>
        )}
        <div style={{marginLeft:"auto",fontSize:12,color:C.inkMid,fontStyle:"italic"}}>{periodLabel}</div>
      </div>

      <div style={{display:"flex",gap:4,marginBottom:24,background:C.surface,border:"1px solid "+C.border,borderRadius:12,padding:5,width:"fit-content",flexWrap:"wrap"}}>
        {RTABS.map(t => (
          <button key={t.id} onClick={()=>loadTab(t.id)} style={{padding:"8px 16px",borderRadius:8,border:"none",cursor:"pointer",fontSize:12,fontWeight:activeTab===t.id?700:400,background:activeTab===t.id?C.accent:"transparent",color:activeTab===t.id?"#fff":C.inkMid,fontFamily:"inherit",whiteSpace:"nowrap"}}>
            {t.label}
          </button>
        ))}
      </div>
      <div id="report-print-area">
        {activeTab==="pl" && (
          <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:28}}>
            {loading ? <div style={{textAlign:"center",padding:40,color:C.inkMid}}>Loading...</div> : (() => {
              // Use management accounts data (loaded alongside this tab) for full breakdown
              const pl = mgmt ? mgmt.pl : null;
              const plRev     = pl ? pl.revenue          : totalRevenue;
              const plCogs    = pl ? (pl.po_cogs || 0)   : 0;
              // True gross profit = revenue minus cost of sales only
              const plTrueGP  = Math.round((plRev - plCogs)*100)/100;
              // Operating expenses = all non-COGS expenses (incl. depreciation)
              const breakdown = pl ? pl.expense_breakdown : {};
              const opExEntries = Object.entries(breakdown)
                .filter(([k]) => k !== "Cost of Sales (POs)")
                .sort(([a],[b]) => a.localeCompare(b));
              const plTotalOpEx = opExEntries.reduce((s,[,v])=>s+v, 0);
              const plEbit      = Math.round((plTrueGP - plTotalOpEx)*100)/100;
              const plPayroll   = pl ? pl.payroll_cost    : totalPayroll;
              const plNBT       = Math.round((plEbit - plPayroll)*100)/100;
              const plTax       = Math.round(Math.max(0, plNBT * 0.27)*100)/100;
              const plNAT       = Math.round((plNBT - plTax)*100)/100;
              const plGM        = plRev ? Math.round(plTrueGP/plRev*100) : 0;
              const plNM        = plRev ? Math.round(plNAT/plRev*100)   : 0;
              return (
                <>
                  <div style={{display:"flex",justifyContent:"space-between",marginBottom:24}}>
                    <div>
                      <div style={{fontFamily:"serif",fontSize:20,fontWeight:800,color:C.ink}}>Income Statement</div>
                      <div style={{fontSize:12,color:C.inkMid,marginTop:4}}>{pl ? `For the period: ${mgmt.period}` : `As at ${period}`}</div>
                    </div>
                    <ExcelBtn filename="income-statement.csv" data={[
                      {Item:"Revenue",Amount:plRev},
                      {Item:"Cost of Sales",Amount:-plCogs},
                      {Item:"Gross Profit",Amount:plTrueGP},
                      ...opExEntries.map(([k,v])=>({Item:k,Amount:-v})),
                      {Item:"Total Operating Expenses",Amount:-plTotalOpEx},
                      {Item:"EBIT",Amount:plEbit},
                      {Item:"Payroll",Amount:-plPayroll},
                      {Item:"Net Profit Before Tax",Amount:plNBT},
                      {Item:"Tax 27%",Amount:-plTax},
                      {Item:"Net Profit After Tax",Amount:plNAT},
                    ]}/>
                  </div>

                  {/* Revenue */}
                  <ReportRow label="Revenue" value={plRev} bold color={C.green}/>

                  {/* Cost of Sales — separate section above gross profit */}
                  {plCogs > 0 && (
                    <>
                      <div style={{fontSize:11,fontWeight:700,color:C.inkMid,letterSpacing:0.5,textTransform:"uppercase",padding:"12px 0 4px",borderTop:"1px solid "+C.border+"50"}}>Cost of Sales</div>
                      <ReportRow label="Purchase Orders (received)" value={-plCogs} indent color={C.red}/>
                      <ReportRow label="Total Cost of Sales" value={-plCogs} bold/>
                    </>
                  )}

                  {/* True Gross Profit = Revenue − COGS */}
                  <ReportRow label="Gross Profit" value={plTrueGP} bold border color={plTrueGP>=0?C.ink:C.red}/>

                  {/* Operating Expenses (incl. depreciation as its own line) */}
                  {opExEntries.length > 0 ? (
                    <>
                      <div style={{fontSize:11,fontWeight:700,color:C.inkMid,letterSpacing:0.5,textTransform:"uppercase",padding:"12px 0 4px",borderTop:"1px solid "+C.border+"50"}}>Operating Expenses</div>
                      {opExEntries.map(([account, amount]) => (
                        <ReportRow key={account} label={account} value={-amount} indent color={C.red}/>
                      ))}
                      <ReportRow label="Total Operating Expenses" value={-plTotalOpEx} bold/>
                    </>
                  ) : (
                    plTotalOpEx > 0 && <ReportRow label="Less: Operating Expenses" value={-plTotalOpEx} indent/>
                  )}

                  {/* EBIT */}
                  <ReportRow label="Earnings Before Interest & Tax (EBIT)" value={plEbit} bold border color={plEbit>=0?C.ink:C.red}/>

                  {/* Payroll & Net Profit */}
                  <ReportRow label="Less: Payroll Costs" value={-plPayroll} indent/>
                  <ReportRow label="Net Profit Before Tax" value={plNBT} bold border color={plNBT>=0?C.ink:C.red}/>
                  <ReportRow label="Less: Tax Provision (27%)" value={-plTax} indent/>
                  <ReportRow label="Net Profit After Tax" value={plNAT} bold border large color={plNAT>=0?C.accent:C.red}/>

                  {/* KPI pills */}
                  <div style={{marginTop:24,display:"flex",gap:12}}>
                    {[["Gross Margin",plGM,C.green,C.greenLt],["Net Margin",plNM,C.accent,C.accentLt],["Tax Rate",27,C.gold,C.goldLt]].map(([l,v,c,bg])=>(
                      <div key={l} style={{flex:1,background:bg,border:"1px solid "+c+"30",borderRadius:12,padding:16,textAlign:"center"}}>
                        <div style={{fontSize:10,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:6}}>{l}</div>
                        <div style={{fontSize:22,fontWeight:800,color:c}}>{v}%</div>
                      </div>
                    ))}
                  </div>
                </>
              );
            })()}
          </div>
        )}
        {activeTab==="bs"   && <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:28}}>{loading ? <div style={{textAlign:"center",padding:40,color:C.inkMid}}>Loading...</div> : renderBS()}</div>}
        {activeTab==="recon"&& <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:28}}>{loading ? <div style={{textAlign:"center",padding:40,color:C.inkMid}}>Loading...</div> : renderReconciliation()}</div>}
        {activeTab==="tb"   && <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:28}}>{loading ? <div style={{textAlign:"center",padding:40,color:C.inkMid}}>Loading...</div> : renderTrialBalance()}</div>}
        {activeTab==="jnl"  && <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:28}}>{loading ? <div style={{textAlign:"center",padding:40,color:C.inkMid}}>Loading...</div> : renderJournal()}</div>}
        {activeTab==="cf"   && <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:28}}>{loading ? <div style={{textAlign:"center",padding:40,color:C.inkMid}}>Loading...</div> : renderCF()}</div>}
        {activeTab==="mgmt" && <div>{loading ? <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:40,textAlign:"center",color:C.inkMid}}>Loading...</div> : renderMgmt()}</div>}
        {/* EMP201/IRP5 moved to Payroll component */}
        {activeTab==="prov" && <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:28}}>{loading ? <div style={{textAlign:"center",padding:40,color:C.inkMid}}>Loading...</div> : renderProvTax()}</div>}
        {activeTab==="vat"  && <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:16,padding:28}}>{renderVat201()}</div>}
      </div>
    </div>
  );
}


// ── BUDGETING ─────────────────────────────────────────────────────────────────
function Budgeting({live = {}}) {
  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const EXPENSE_CATS = ["Cost of Sales","Utilities","Telecoms","Office","Banking","Insurance","Tax","Equipment","Travel","Salaries","Rent","Marketing","Professional Fees","Other"];
  const INCOME_CATS  = ["Revenue"];
  const ALL_CATS     = [...INCOME_CATS, ...EXPENSE_CATS];
  const DEPTS        = ["General","Sales","Operations","Finance","HR","IT","Marketing","Admin"];

  const [view,    setView]    = useState("monthly");   // monthly | annual | cashflow | departments
  const [year,    setYear]    = useState(new Date().getFullYear());
  const [month,   setMonth]   = useState(new Date().getMonth() + 1);
  const [budgets, setBudgets] = useState([]);
  const [actuals, setActuals] = useState([]);
  const [summary, setSummary] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving,  setSaving]  = useState(false);
  const [editCell, setEditCell] = useState(null); // {cat, month, type, dept}
  const [editVal,  setEditVal]  = useState("");
  const [dept,     setDept]     = useState("General");
  const [csvPreview, setCsvPreview] = useState(null); // parsed rows awaiting confirm
  const [csvError,   setCsvError]   = useState(null);
  const csvInputRef = useRef(null);

  const load = async () => {
    setLoading(true);
    try {
      const [b, a, s] = await Promise.all([
        api(`/budgets/?year=${year}`),
        api(`/budgets/actuals?year=${year}`),
        api(`/budgets/summary?year=${year}`),
      ]);
      setBudgets(b); setActuals(a); setSummary(s);
    } catch(e) { console.warn("Budget load error", e); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [year]);

  const getBudget = (cat, m, type="expense", d=null) => {
    const b = budgets.find(b => b.category===cat && b.month===m && b.type===type && (d ? b.department===d : true));
    return b ? b.amount : 0;
  };

  const getActual = (cat, m, type="expense") => {
    const a = actuals.find(a => a.category===cat && a.month===m && a.type===type);
    return a ? a.actual : 0;
  };

  const saveCell = async (cat, m, type, amount, d=null) => {
    setSaving(true);
    try {
      await api("/budgets/", {method:"POST", body: JSON.stringify({
        year, month: m, category: cat, amount: parseFloat(amount)||0, type, department: d||null,
      })});
      await load();
    } catch(e) { alert("Save failed: "+(e.message||"")); }
    finally { setSaving(false); setEditCell(null); }
  };

  const fmtR = (n) => `R ${Number(n||0).toLocaleString("en-ZA",{minimumFractionDigits:0,maximumFractionDigits:0})}`;
  const pct  = (actual, budget) => budget > 0 ? Math.min(Math.round((actual/budget)*100), 200) : 0;
  const over = (actual, budget) => budget > 0 && actual > budget;

  // ── CSV IMPORT ──────────────────────────────────────────────────────────────
  const MONTH_NAMES = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

  const downloadTemplate = () => {
    const header = "category,type,department,jan,feb,mar,apr,may,jun,jul,aug,sep,oct,nov,dec";
    const rows = [
      "Revenue,income,,100000,100000,110000,110000,120000,120000,130000,130000,140000,140000,150000,150000",
      "Salaries,expense,,50000,50000,50000,50000,50000,50000,50000,50000,50000,50000,50000,50000",
      "Rent,expense,,12000,12000,12000,12000,12000,12000,12000,12000,12000,12000,12000,12000",
      "Marketing,expense,Sales,5000,5000,6000,6000,7000,7000,8000,8000,9000,9000,10000,10000",
    ];
    const csv = [header, ...rows].join("\n");
    const blob = new Blob([csv], {type:"text/csv"});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `zuzan-budget-template-${year}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  const parseCsv = (text) => {
    const lines = text.trim().split(/\r?\n/).filter(l => l.trim());
    if (lines.length < 2) throw new Error("CSV must have a header row and at least one data row.");
    const headers = lines[0].split(",").map(h => h.trim().toLowerCase());
    const catIdx  = headers.indexOf("category");
    const typeIdx = headers.indexOf("type");
    const deptIdx = headers.indexOf("department");
    if (catIdx === -1) throw new Error("Missing required column: category");

    // Detect format: monthly columns (jan…dec) or explicit month column
    const monthCols = MONTH_NAMES.map(m => headers.indexOf(m));
    const hasMonthCols = monthCols.some(i => i !== -1);
    const monthIdx  = headers.indexOf("month");
    const amountIdx = headers.indexOf("amount");
    const yearIdx   = headers.indexOf("year");

    const entries = [];
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(",").map(c => c.trim());
      if (cols.every(c => !c)) continue; // skip blank rows
      const category   = cols[catIdx] || "";
      const type       = typeIdx !== -1 ? (cols[typeIdx]||"expense").toLowerCase() : (category==="Revenue"?"income":"expense");
      const department = deptIdx !== -1 ? (cols[deptIdx]||null) : null;
      const rowYear    = yearIdx !== -1 ? parseInt(cols[yearIdx]) : year;
      if (!category) continue;

      if (hasMonthCols) {
        // Wide format: one row per category, one column per month
        MONTH_NAMES.forEach((m, idx) => {
          const colIdx = monthCols[idx];
          if (colIdx === -1) return;
          const amount = parseFloat((cols[colIdx]||"0").replace(/[^0-9.\-]/g,"")) || 0;
          if (amount !== 0) entries.push({year: rowYear, month: idx+1, category, amount, type, department: department||null});
        });
      } else {
        // Long format: explicit year/month/amount columns
        if (monthIdx === -1 || amountIdx === -1) throw new Error("Long format requires columns: year, month, category, amount, type");
        const month  = parseInt(cols[monthIdx]);
        const amount = parseFloat((cols[amountIdx]||"0").replace(/[^0-9.\-]/g,"")) || 0;
        if (month >= 1 && month <= 12 && amount !== 0)
          entries.push({year: rowYear, month, category, amount, type, department: department||null});
      }
    }
    if (!entries.length) throw new Error("No valid budget entries found in CSV.");
    return entries;
  };

  const handleCsvFile = (e) => {
    setCsvError(null); setCsvPreview(null);
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const entries = parseCsv(ev.target.result);
        setCsvPreview(entries);
      } catch(err) {
        setCsvError(err.message);
      }
    };
    reader.readAsText(file);
    e.target.value = ""; // allow re-upload of same file
  };

  const confirmImport = async () => {
    if (!csvPreview) return;
    setSaving(true);
    try {
      await api("/budgets/bulk", {method:"POST", body: JSON.stringify({entries: csvPreview})});
      setCsvPreview(null);
      await load();
    } catch(e) {
      setCsvError("Import failed: "+(e.message||""));
    } finally { setSaving(false); }
  };

  const CellInput = ({cat, m, type, dept: d}) => {
    const key = `${cat}-${m}-${type}`;
    const cur = getBudget(cat, m, type, d);
    return editCell === key
      ? <input autoFocus type="number" value={editVal}
          onChange={e=>setEditVal(e.target.value)}
          onBlur={()=>saveCell(cat,m,type,editVal,d)}
          onKeyDown={e=>{if(e.key==="Enter")saveCell(cat,m,type,editVal,d);if(e.key==="Escape")setEditCell(null);}}
          style={{width:80,padding:"2px 4px",border:`1px solid ${C.accent}`,borderRadius:4,fontSize:12,textAlign:"right",fontFamily:"inherit"}}/>
      : <span onClick={()=>{setEditCell(key);setEditVal(cur||"");}}
          style={{cursor:"text",fontSize:12,color:cur?C.ink:C.inkDim,display:"block",textAlign:"right",minWidth:60,padding:"2px 4px",borderRadius:4,border:`1px dashed ${C.border}`}}>
          {cur ? fmtR(cur) : "Set…"}
        </span>;
  };

  // ── MONTHLY VIEW ────────────────────────────────────────────────────────────
  const MonthlyView = () => {
    const [catFilter, setCatFilter] = useState("all"); // all | over | on_track | no_budget
    const totalBudget = ALL_CATS.reduce((s,c)=>s+getBudget(c,month,c==="Revenue"?"income":"expense"),0);
    const totalActual = actuals.filter(a=>a.month===month).reduce((s,a)=>s+a.actual,0);
    const remaining   = totalBudget - totalActual;
    const overBudgetCount = ALL_CATS.filter(c=>{
      const t=c==="Revenue"?"income":"expense";
      return over(getActual(c,month,t), getBudget(c,month,t));
    }).length;

    const FILTERS = [
      {id:"all",       label:"All",          color:C.ink},
      {id:"over",      label:`Over Budget (${overBudgetCount})`, color:C.red},
      {id:"on_track",  label:"On Track",     color:C.green},
      {id:"no_budget", label:"No Budget Set",color:C.gold},
    ];

    return (
      <div>
        <div style={{display:"flex",gap:8,marginBottom:20,alignItems:"center"}}>
          <select value={month} onChange={e=>setMonth(+e.target.value)} style={{padding:"8px 12px",borderRadius:8,border:`1px solid ${C.border}`,fontSize:13,background:C.bg,color:C.ink,fontFamily:"inherit"}}>
            {MONTHS.map((m,i)=><option key={i} value={i+1}>{m}</option>)}
          </select>
          <span style={{fontSize:12,color:C.inkMid}}>vs actual spend</span>
        </div>

        {/* Summary KPIs — clickable to filter categories below */}
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12,marginBottom:12}}>
          {[
            {id:"all",      label:"Total Budgeted", value:fmtR(totalBudget), color:C.ink,   active:catFilter==="all"},
            {id:"over",     label:"Actual Spend",   value:fmtR(totalActual), color:totalActual>totalBudget?C.red:C.ink, active:catFilter==="over"},
            {id:"on_track", label:"Remaining",      value:fmtR(Math.abs(remaining)), color:remaining>=0?C.green:C.red, active:catFilter==="on_track"},
          ].map(card=>(
            <div key={card.id} onClick={()=>setCatFilter(f=>f===card.id?"all":card.id)}
              style={{background:card.active?card.color:C.surface,borderRadius:12,padding:"14px 16px",border:`2px solid ${card.active?card.color:C.border}`,cursor:"pointer",transition:"all 0.15s"}}
              onMouseEnter={e=>{if(!card.active)e.currentTarget.style.borderColor=card.color;}}
              onMouseLeave={e=>{if(!card.active)e.currentTarget.style.borderColor=C.border;}}>
              <div style={{fontSize:10,color:card.active?"rgba(255,255,255,0.7)":C.inkMid,fontWeight:600,textTransform:"uppercase",letterSpacing:0.5,marginBottom:4}}>{card.label}</div>
              <div style={{fontSize:18,fontWeight:700,color:card.active?"#fff":card.color}}>{card.value}</div>
              {card.id==="on_track" && <div style={{fontSize:10,color:card.active?"rgba(255,255,255,0.6)":C.inkMid,marginTop:2}}>{remaining<0?"Over budget":"Under budget"}</div>}
              {card.active && <div style={{fontSize:10,color:"rgba(255,255,255,0.6)",marginTop:2}}>▼ Filtering</div>}
            </div>
          ))}
        </div>

        {/* Filter pills */}
        <div style={{display:"flex",gap:8,marginBottom:20,flexWrap:"wrap"}}>
          {FILTERS.map(f=>(
            <button key={f.id} onClick={()=>setCatFilter(f.id)}
              style={{padding:"5px 14px",borderRadius:20,border:`1px solid ${catFilter===f.id?f.color:C.border}`,background:catFilter===f.id?f.color+"18":"transparent",color:catFilter===f.id?f.color:C.inkMid,fontSize:12,cursor:"pointer",fontFamily:"inherit",fontWeight:catFilter===f.id?600:400}}>
              {f.label}
            </button>
          ))}
        </div>

        {/* Per-category rows */}
        {ALL_CATS.map(cat => {
          const type   = cat==="Revenue" ? "income" : "expense";
          const budget = getBudget(cat, month, type);
          const actual = getActual(cat, month, type);
          const p      = pct(actual, budget);
          const isOver = over(actual, budget);
          // Always skip empty rows (no budget AND no actual)
          if (!budget && !actual) {
            if (catFilter !== "no_budget") return null;
            // In no_budget mode, show categories with no budget but don't skip all
          }
          // Apply filter
          if (catFilter === "over"      && !isOver)            return null;
          if (catFilter === "on_track"  && (isOver || !budget)) return null;
          if (catFilter === "no_budget" && budget)              return null;
          if (catFilter === "no_budget" && !budget && !actual)  return null; // genuinely empty, skip
          return (
            <div key={cat} style={{background:C.surface,border:`1px solid ${isOver&&catFilter!=="on_track"?C.red+"60":C.border}`,borderRadius:12,padding:"12px 16px",marginBottom:10}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
                <div style={{fontSize:13,fontWeight:600,color:C.ink}}>{cat}</div>
                <div style={{display:"flex",gap:16,alignItems:"center"}}>
                  <div style={{textAlign:"right"}}>
                    <div style={{fontSize:10,color:C.inkMid}}>Budget</div>
                    <CellInput cat={cat} m={month} type={type}/>
                  </div>
                  <div style={{textAlign:"right"}}>
                    <div style={{fontSize:10,color:C.inkMid}}>Actual</div>
                    <div style={{fontSize:12,fontWeight:600,color:isOver?C.red:C.ink}}>{fmtR(actual)}</div>
                  </div>
                  <div style={{textAlign:"right"}}>
                    <div style={{fontSize:10,color:C.inkMid}}>%</div>
                    <div style={{fontSize:12,fontWeight:700,color:isOver?C.red:C.green}}>{p}%</div>
                  </div>
                </div>
              </div>
              <div style={{height:6,background:C.border,borderRadius:3}}>
                <div style={{height:"100%",width:`${Math.min(p,100)}%`,background:isOver?C.red:p>80?C.gold:C.green,borderRadius:3,transition:"width 0.3s"}}/>
              </div>
              {isOver && <div style={{fontSize:10,color:C.red,marginTop:4}}>⚠ Over budget by {fmtR(actual-budget)}</div>}
            </div>
          );
        })}

        {/* Prompt to set budgets */}
        {ALL_CATS.every(cat=>{const type=cat==="Revenue"?"income":"expense";return !getBudget(cat,month,type)&&!getActual(cat,month,type);}) && catFilter==="all" && (
          <div style={{textAlign:"center",padding:"40px 20px",color:C.inkMid}}>
            <div style={{fontSize:32,marginBottom:12}}>🎯</div>
            <div style={{fontSize:15,fontWeight:600,marginBottom:6}}>No budget set for {MONTHS[month-1]}</div>
            <div style={{fontSize:13}}>Switch to Annual view to plan the full year, or click "Set…" next to any category above after adding some expenses.</div>
          </div>
        )}
      </div>
    );
  };

  // ── ANNUAL VIEW ─────────────────────────────────────────────────────────────
  const AnnualView = () => {
    const [pendingSaves, setPendingSaves] = useState({});
    const setPending = (cat, m, type, val) => setPendingSaves(p=>({...p,[`${cat}-${m}-${type}`]:val}));
    const getCellVal = (cat, m, type) => {
      const key = `${cat}-${m}-${type}`;
      return pendingSaves[key] !== undefined ? pendingSaves[key] : (getBudget(cat,m,type)||"");
    };
    const saveAll = async () => {
      if (!Object.keys(pendingSaves).length) return;
      setSaving(true);
      try {
        const entries = Object.entries(pendingSaves).map(([key,val])=>{
          const [cat,...rest] = key.split("-");
          const type = rest.pop();
          const m = parseInt(rest.join("-"));
          return {year, month:m, category:cat, amount:parseFloat(val)||0, type};
        });
        await api("/budgets/bulk",{method:"POST",body:JSON.stringify({entries})});
        setPendingSaves({});
        await load();
      } catch(e){alert("Save failed");}
      finally{setSaving(false);}
    };

    return (
      <div>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
          <div style={{fontSize:13,color:C.inkMid}}>Click any cell to edit. Save all when done.</div>
          {Object.keys(pendingSaves).length>0 &&
            <button onClick={saveAll} disabled={saving} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"8px 16px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>
              {saving?"Saving…":`Save ${Object.keys(pendingSaves).length} changes`}
            </button>}
        </div>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:12,minWidth:900}}>
            <thead>
              <tr style={{background:C.surface}}>
                <th style={{padding:"8px 12px",textAlign:"left",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`,position:"sticky",left:0,background:C.surface,zIndex:1}}>Category</th>
                {MONTHS.map((m,i)=><th key={i} style={{padding:"8px 8px",textAlign:"center",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`,minWidth:80}}>{m}</th>)}
                <th style={{padding:"8px 8px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Total</th>
              </tr>
            </thead>
            <tbody>
              {/* Income section */}
              <tr><td colSpan={14} style={{background:C.greenLt,padding:"6px 12px",fontSize:11,fontWeight:700,color:C.green,letterSpacing:0.5,textTransform:"uppercase"}}>Income</td></tr>
              {INCOME_CATS.map(cat=>(
                <tr key={cat}>
                  <td style={{padding:"6px 12px",border:`1px solid ${C.border}`,fontWeight:500,color:C.ink,position:"sticky",left:0,background:"#fff",zIndex:1}}>{cat}</td>
                  {MONTHS.map((_,i)=>{
                    const m=i+1; const key=`${cat}-${m}-income`;
                    const cur=getCellVal(cat,m,"income");
                    return <td key={m} style={{border:`1px solid ${C.border}`,padding:"2px 4px",textAlign:"right"}}>
                      <input type="number" value={cur} placeholder="0"
                        onChange={e=>setPending(cat,m,"income",e.target.value)}
                        style={{width:"100%",border:"none",background:"transparent",textAlign:"right",fontSize:12,fontFamily:"inherit",color:cur?C.ink:C.inkDim,outline:"none",padding:"4px 2px"}}/>
                    </td>;
                  })}
                  <td style={{border:`1px solid ${C.border}`,padding:"6px 8px",textAlign:"right",fontWeight:600,color:C.green}}>
                    {fmtR(MONTHS.reduce((s,_,i)=>s+(parseFloat(getCellVal(cat,i+1,"income"))||0),0))}
                  </td>
                </tr>
              ))}
              {/* Expense section */}
              <tr><td colSpan={14} style={{background:"#FFF3F3",padding:"6px 12px",fontSize:11,fontWeight:700,color:C.red,letterSpacing:0.5,textTransform:"uppercase"}}>Expenses</td></tr>
              {EXPENSE_CATS.map(cat=>(
                <tr key={cat}>
                  <td style={{padding:"6px 12px",border:`1px solid ${C.border}`,fontWeight:500,color:C.ink,position:"sticky",left:0,background:"#fff",zIndex:1}}>{cat}</td>
                  {MONTHS.map((_,i)=>{
                    const m=i+1; const key=`${cat}-${m}-expense`;
                    const cur=getCellVal(cat,m,"expense");
                    return <td key={m} style={{border:`1px solid ${C.border}`,padding:"2px 4px",textAlign:"right"}}>
                      <input type="number" value={cur} placeholder="0"
                        onChange={e=>setPending(cat,m,"expense",e.target.value)}
                        style={{width:"100%",border:"none",background:"transparent",textAlign:"right",fontSize:12,fontFamily:"inherit",color:cur?C.ink:C.inkDim,outline:"none",padding:"4px 2px"}}/>
                    </td>;
                  })}
                  <td style={{border:`1px solid ${C.border}`,padding:"6px 8px",textAlign:"right",fontWeight:600,color:C.red}}>
                    {fmtR(MONTHS.reduce((s,_,i)=>s+(parseFloat(getCellVal(cat,i+1,"expense"))||0),0))}
                  </td>
                </tr>
              ))}
              {/* Net row */}
              <tr style={{background:C.surface,fontWeight:700}}>
                <td style={{padding:"8px 12px",border:`1px solid ${C.border}`,position:"sticky",left:0,background:C.surface,zIndex:1}}>Net (Income − Expenses)</td>
                {MONTHS.map((_,i)=>{
                  const m=i+1;
                  const inc=(parseFloat(getCellVal("Revenue",m,"income"))||0);
                  const exp=EXPENSE_CATS.reduce((s,c)=>s+(parseFloat(getCellVal(c,m,"expense"))||0),0);
                  const net=inc-exp;
                  return <td key={m} style={{border:`1px solid ${C.border}`,padding:"6px 8px",textAlign:"right",color:net>=0?C.green:C.red}}>{net?fmtR(net):""}</td>;
                })}
                <td style={{border:`1px solid ${C.border}`,padding:"6px 8px",textAlign:"right",color:C.ink}}>
                  {fmtR(MONTHS.reduce((s,_,i)=>{
                    const m=i+1;
                    const inc=(parseFloat(getCellVal("Revenue",m,"income"))||0);
                    const exp=EXPENSE_CATS.reduce((s2,c)=>s2+(parseFloat(getCellVal(c,m,"expense"))||0),0);
                    return s+(inc-exp);
                  },0))}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  // ── CASH FLOW VIEW ──────────────────────────────────────────────────────────
  const CashFlowView = () => {
    return (
      <div>
        <p style={{fontSize:13,color:C.inkMid,marginBottom:16}}>Budgeted vs actual net cash position per month for {year}.</p>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
            <thead>
              <tr style={{background:C.surface}}>
                <th style={{padding:"10px 14px",textAlign:"left",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Month</th>
                <th style={{padding:"10px 14px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Budgeted Income</th>
                <th style={{padding:"10px 14px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Budgeted Expense</th>
                <th style={{padding:"10px 14px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Budgeted Net</th>
                <th style={{padding:"10px 14px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Actual Income</th>
                <th style={{padding:"10px 14px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Actual Expense</th>
                <th style={{padding:"10px 14px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Actual Net</th>
                <th style={{padding:"10px 14px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Variance</th>
              </tr>
            </thead>
            <tbody>
              {summary.map(row=>{
                const variance = row.actual_net - row.budgeted_net;
                const now = new Date(); const isFuture = row.month > now.getMonth()+1 && year >= now.getFullYear();
                return (
                  <tr key={row.month} style={{background:isFuture?"#fafafa":"#fff"}}>
                    <td style={{padding:"10px 14px",border:`1px solid ${C.border}`,fontWeight:600,color:C.ink}}>{MONTHS[row.month-1]}{isFuture?" (forecast)":""}</td>
                    <td style={{padding:"10px 14px",border:`1px solid ${C.border}`,textAlign:"right",color:C.green}}>{row.budgeted_income?fmtR(row.budgeted_income):"—"}</td>
                    <td style={{padding:"10px 14px",border:`1px solid ${C.border}`,textAlign:"right",color:C.red}}>{row.budgeted_expense?fmtR(row.budgeted_expense):"—"}</td>
                    <td style={{padding:"10px 14px",border:`1px solid ${C.border}`,textAlign:"right",fontWeight:600,color:row.budgeted_net>=0?C.green:C.red}}>{row.budgeted_net?fmtR(row.budgeted_net):"—"}</td>
                    <td style={{padding:"10px 14px",border:`1px solid ${C.border}`,textAlign:"right",color:C.green,opacity:isFuture?0.3:1}}>{row.actual_income?fmtR(row.actual_income):"—"}</td>
                    <td style={{padding:"10px 14px",border:`1px solid ${C.border}`,textAlign:"right",color:C.red,opacity:isFuture?0.3:1}}>{row.actual_expense?fmtR(row.actual_expense):"—"}</td>
                    <td style={{padding:"10px 14px",border:`1px solid ${C.border}`,textAlign:"right",fontWeight:600,color:row.actual_net>=0?C.green:C.red,opacity:isFuture?0.3:1}}>{row.actual_net?fmtR(row.actual_net):"—"}</td>
                    <td style={{padding:"10px 14px",border:`1px solid ${C.border}`,textAlign:"right",fontWeight:600,color:variance>=0?C.green:C.red,opacity:isFuture?0.3:1}}>{!isFuture&&row.actual_net?`${variance>=0?"+":""}${fmtR(variance)}`:"—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  // ── DEPARTMENTS VIEW ─────────────────────────────────────────────────────────
  const DepartmentsView = () => {
    const [pendingSaves, setPendingSaves] = useState({});
    const setPending = (cat, m, val) => setPendingSaves(p=>({...p,[`${cat}-${m}`]:val}));
    const getCellVal = (cat, m) => {
      const key=`${cat}-${m}`;
      if(pendingSaves[key]!==undefined) return pendingSaves[key];
      const b=budgets.find(b=>b.category===cat&&b.month===m&&b.department===dept);
      return b?b.amount:"";
    };
    const saveAll = async () => {
      if(!Object.keys(pendingSaves).length) return;
      setSaving(true);
      try {
        const entries=Object.entries(pendingSaves).map(([key,val])=>{
          const [cat,m]=key.split("-");
          return {year,month:parseInt(m),category:cat,amount:parseFloat(val)||0,type:"expense",department:dept};
        });
        await api("/budgets/bulk",{method:"POST",body:JSON.stringify({entries})});
        setPendingSaves({});
        await load();
      } catch(e){alert("Save failed");}
      finally{setSaving(false);}
    };

    return (
      <div>
        <div style={{display:"flex",gap:12,alignItems:"center",marginBottom:16,flexWrap:"wrap"}}>
          <select value={dept} onChange={e=>setDept(e.target.value)} style={{padding:"8px 12px",borderRadius:8,border:`1px solid ${C.border}`,fontSize:13,background:C.bg,color:C.ink,fontFamily:"inherit"}}>
            {DEPTS.map(d=><option key={d} value={d}>{d}</option>)}
          </select>
          <span style={{fontSize:12,color:C.inkMid}}>department budget for {year}</span>
          {Object.keys(pendingSaves).length>0 &&
            <button onClick={saveAll} disabled={saving} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"8px 16px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>
              {saving?"Saving…":`Save ${Object.keys(pendingSaves).length} changes`}
            </button>}
        </div>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:12,minWidth:900}}>
            <thead>
              <tr style={{background:C.surface}}>
                <th style={{padding:"8px 12px",textAlign:"left",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`,position:"sticky",left:0,background:C.surface}}>Category</th>
                {MONTHS.map((m,i)=><th key={i} style={{padding:"8px 8px",textAlign:"center",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`,minWidth:80}}>{m}</th>)}
                <th style={{padding:"8px 8px",textAlign:"right",fontWeight:600,color:C.inkMid,border:`1px solid ${C.border}`}}>Total</th>
              </tr>
            </thead>
            <tbody>
              {EXPENSE_CATS.map(cat=>(
                <tr key={cat}>
                  <td style={{padding:"6px 12px",border:`1px solid ${C.border}`,fontWeight:500,color:C.ink,position:"sticky",left:0,background:"#fff"}}>{cat}</td>
                  {MONTHS.map((_,i)=>{
                    const m=i+1; const cur=getCellVal(cat,m);
                    return <td key={m} style={{border:`1px solid ${C.border}`,padding:"2px 4px",textAlign:"right"}}>
                      <input type="number" value={cur} placeholder="0"
                        onChange={e=>setPending(cat,m,e.target.value)}
                        style={{width:"100%",border:"none",background:"transparent",textAlign:"right",fontSize:12,fontFamily:"inherit",outline:"none",padding:"4px 2px"}}/>
                    </td>;
                  })}
                  <td style={{border:`1px solid ${C.border}`,padding:"6px 8px",textAlign:"right",fontWeight:600,color:C.red}}>
                    {fmtR(MONTHS.reduce((s,_,i)=>s+(parseFloat(getCellVal(cat,i+1))||0),0))}
                  </td>
                </tr>
              ))}
              <tr style={{background:C.surface,fontWeight:700}}>
                <td style={{padding:"8px 12px",border:`1px solid ${C.border}`,position:"sticky",left:0,background:C.surface}}>Total — {dept}</td>
                {MONTHS.map((_,i)=>{
                  const m=i+1;
                  const total=EXPENSE_CATS.reduce((s,c)=>s+(parseFloat(getCellVal(c,m))||0),0);
                  return <td key={m} style={{border:`1px solid ${C.border}`,padding:"6px 8px",textAlign:"right",color:C.accent,fontWeight:700}}>{total?fmtR(total):""}</td>;
                })}
                <td style={{border:`1px solid ${C.border}`,padding:"6px 8px",textAlign:"right",color:C.accent,fontWeight:700}}>
                  {fmtR(EXPENSE_CATS.reduce((s,c)=>s+MONTHS.reduce((s2,_,i)=>s2+(parseFloat(getCellVal(c,i+1))||0),0),0))}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div>
      <SectionHeader title="Budgeting" sub="Plan, track and forecast your finances"/>

      {/* Year selector + view tabs */}
      <div style={{display:"flex",gap:12,alignItems:"center",marginBottom:20,flexWrap:"wrap"}}>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <button onClick={()=>setYear(y=>y-1)} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:6,padding:"5px 10px",cursor:"pointer",fontSize:13,fontFamily:"inherit"}}>◀</button>
          <span style={{fontSize:15,fontWeight:700,color:C.ink,minWidth:48,textAlign:"center"}}>{year}</span>
          <button onClick={()=>setYear(y=>y+1)} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:6,padding:"5px 10px",cursor:"pointer",fontSize:13,fontFamily:"inherit"}}>▶</button>
        </div>
        {[
          {id:"monthly",     label:"Monthly"},
          {id:"annual",      label:"Annual Plan"},
          {id:"cashflow",    label:"Cash Flow"},
          {id:"departments", label:"Departments"},
        ].map(v=>(
          <button key={v.id} onClick={()=>setView(v.id)} style={{
            padding:"7px 14px",borderRadius:8,border:`1px solid ${view===v.id?C.accent:C.border}`,
            background:view===v.id?C.accentLt:"transparent",color:view===v.id?C.accent:C.inkMid,
            fontSize:13,fontWeight:view===v.id?700:400,cursor:"pointer",fontFamily:"inherit",
          }}>{v.label}</button>
        ))}
        {loading && <span style={{fontSize:12,color:C.inkMid}}>Loading…</span>}
        <div style={{marginLeft:"auto",display:"flex",gap:8}}>
          <button onClick={downloadTemplate} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:8,padding:"7px 14px",fontSize:12,cursor:"pointer",fontFamily:"inherit",color:C.inkMid}}>
            ⬇ Template
          </button>
          <button onClick={()=>csvInputRef.current?.click()} style={{background:C.accent,border:"none",borderRadius:8,padding:"7px 16px",fontSize:12,cursor:"pointer",fontFamily:"inherit",color:"#fff",fontWeight:600}}>
            📂 Import CSV
          </button>
          <input ref={csvInputRef} type="file" accept=".csv,text/csv" style={{display:"none"}} onChange={handleCsvFile}/>
        </div>
      </div>

      {/* CSV error banner */}
      {csvError && (
        <div style={{background:"#fff0ee",border:`1px solid ${C.red}`,borderRadius:10,padding:"12px 16px",marginBottom:16,display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
          <div>
            <div style={{fontWeight:700,color:C.red,fontSize:13,marginBottom:4}}>⚠ CSV Import Error</div>
            <div style={{fontSize:12,color:C.red}}>{csvError}</div>
          </div>
          <button onClick={()=>setCsvError(null)} style={{background:"none",border:"none",fontSize:16,cursor:"pointer",color:C.red,padding:0}}>✕</button>
        </div>
      )}

      {/* CSV preview modal */}
      {csvPreview && (
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:20,marginBottom:20}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:14}}>
            <div>
              <div style={{fontWeight:700,fontSize:15,color:C.ink}}>📋 Preview — {csvPreview.length} budget entries</div>
              <div style={{fontSize:12,color:C.inkMid,marginTop:2}}>Review before importing. Existing entries for the same category/month will be overwritten.</div>
            </div>
            <div style={{display:"flex",gap:8}}>
              <button onClick={()=>setCsvPreview(null)} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:8,padding:"7px 14px",fontSize:12,cursor:"pointer",fontFamily:"inherit",color:C.inkMid}}>Cancel</button>
              <button onClick={confirmImport} disabled={saving} style={{background:C.green,border:"none",borderRadius:8,padding:"7px 18px",fontSize:12,cursor:"pointer",fontFamily:"inherit",color:"#fff",fontWeight:700}}>
                {saving ? "Importing…" : `✓ Import ${csvPreview.length} entries`}
              </button>
            </div>
          </div>
          <div style={{maxHeight:260,overflowY:"auto"}}>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
              <thead>
                <tr style={{background:"#f5f5f5",position:"sticky",top:0}}>
                  {["Year","Month","Category","Type","Amount","Department"].map(h=>(
                    <th key={h} style={{padding:"6px 10px",textAlign:"left",color:C.inkMid,fontWeight:600,borderBottom:`1px solid ${C.border}`}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {csvPreview.slice(0,100).map((r,i)=>(
                  <tr key={i} style={{borderBottom:`1px solid ${C.border}40`}}>
                    <td style={{padding:"5px 10px",color:C.ink}}>{r.year}</td>
                    <td style={{padding:"5px 10px",color:C.ink}}>
                      {["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][r.month-1]}
                    </td>
                    <td style={{padding:"5px 10px",color:C.ink,fontWeight:500}}>{r.category}</td>
                    <td style={{padding:"5px 10px",color:r.type==="income"?C.green:C.inkMid}}>{r.type}</td>
                    <td style={{padding:"5px 10px",color:C.ink,textAlign:"right"}}>R {r.amount.toLocaleString("en-ZA")}</td>
                    <td style={{padding:"5px 10px",color:C.inkMid}}>{r.department||"—"}</td>
                  </tr>
                ))}
                {csvPreview.length > 100 && (
                  <tr><td colSpan={6} style={{padding:"8px 10px",color:C.inkMid,fontSize:11,textAlign:"center"}}>…and {csvPreview.length - 100} more rows</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {view==="monthly"     && <MonthlyView/>}
      {view==="annual"      && <AnnualView/>}
      {view==="cashflow"    && <CashFlowView/>}
      {view==="departments" && <DepartmentsView/>}
    </div>
  );
}

// ── DEBTORS ───────────────────────────────────────────────────────────────────
function Debtors({live = {}}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    api("/reports/debtors-aging").then(setData).catch(()=>null).finally(()=>setLoading(false));
  }, []);

  // Refresh when an invoice payment is recorded
  useEffect(() => {
    if (live.invoices) {
      api("/reports/debtors-aging").then(setData).catch(()=>null);
    }
  }, [live.invoices]); // eslint-disable-line

  const BUCKETS = [
    {key:"not_due", label:"Not Yet Due",  color:C.blue},
    {key:"current", label:"0 – 30 Days",  color:C.green},
    {key:"31_60",   label:"31 – 60 Days", color:C.gold},
    {key:"61_90",   label:"61 – 90 Days", color:C.accent},
    {key:"over_90", label:"90+ Days",     color:C.red},
  ];

  // Mock debtors for demo mode
  const mockBuckets = {
    not_due: [{id:"INV-003",client:"SA Retail Group",amount:67200,due_date:"2025-06-15",days_overdue:0,status:"sent"}],
    current: [{id:"INV-002",client:"BuildRight CC",amount:28500,due_date:"2025-05-10",days_overdue:20,status:"sent"}],
    "31_60": [{id:"INV-004",client:"Cape Town Motors",amount:15800,due_date:"2025-04-20",days_overdue:40,status:"overdue"}],
    "61_90": [],
    over_90: [],
  };
  const mockTotals = {not_due:67200,current:28500,"31_60":15800,"61_90":0,over_90:0,grand:111500};

  const buckets = data ? data.buckets : mockBuckets;
  const totals  = data ? data.totals  : mockTotals;
  const asAt    = data ? data.as_at   : new Date().toLocaleDateString("en-ZA",{day:"2-digit",month:"long",year:"numeric"});

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-end",marginBottom:20}}>
        <div>
          <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:0}}>Debtors Book</h2>
          <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>Accounts receivable — as at {asAt}</p>
        </div>
        <div style={{display:"flex",gap:8}}>
          {!data && <Badge label="Demo Mode" color={C.gold} bg={C.goldLt}/>}
          <KPI label="Total Outstanding" value={fmt(totals.grand)} color={C.accent} icon="Total"/>
        </div>
      </div>
      {loading && <div style={{textAlign:"center",padding:40,color:C.inkMid}}>Loading debtors...</div>}
      {!loading && (
        <div>
          <div style={{display:"flex",gap:12,marginBottom:24,flexWrap:"wrap"}}>
            {BUCKETS.map(b => (
              <div key={b.key} onClick={()=>setExpanded(expanded===b.key?null:b.key)}
                style={{flex:1,minWidth:140,background:C.surface,border:`2px solid ${expanded===b.key?b.color:C.border}`,borderRadius:14,padding:16,cursor:"pointer"}}>
                <div style={{fontSize:10,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:8}}>{b.label}</div>
                <div style={{fontSize:20,fontWeight:800,color:b.color,marginBottom:4}}>{fmt(totals[b.key])}</div>
                <div style={{fontSize:11,color:C.inkDim}}>{(buckets[b.key]||[]).length} invoice{(buckets[b.key]||[]).length!==1?"s":""}</div>
              </div>
            ))}
          </div>
          {BUCKETS.map(b => expanded===b.key && (buckets[b.key]||[]).length>0 && (
            <div key={b.key} style={{background:C.surface,border:`1px solid ${b.color}40`,borderRadius:16,overflow:"hidden",marginBottom:16}}>
              <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.border}`,fontSize:13,fontWeight:700,color:b.color}}>{b.label} — {fmt(totals[b.key])}</div>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
                <thead>
                  <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                    {["Invoice","Client","Amount","Due Date","Days Overdue","Status"].map(h=>(
                      <th key={h} style={{padding:"10px 16px",textAlign:"left",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(buckets[b.key]||[]).map((inv,i)=>(
                    <tr key={i} style={{borderBottom:`1px solid ${C.border}20`}}>
                      <td style={{padding:"12px 16px",fontWeight:700,color:C.accent}}>{inv.id}</td>
                      <td style={{padding:"12px 16px",fontWeight:500}}>{inv.client}</td>
                      <td style={{padding:"12px 16px",fontWeight:700}}>{fmt(inv.amount)}</td>
                      <td style={{padding:"12px 16px",color:C.inkMid}}>{inv.due_date ? new Date(inv.due_date).toLocaleDateString("en-ZA",{day:"2-digit",month:"short",year:"numeric"}) : "—"}</td>
                      <td style={{padding:"12px 16px"}}>
                        <Badge label={inv.days_overdue===0?"Current":inv.days_overdue+" days"} color={b.color} bg={b.color+"15"}/>
                      </td>
                      <td style={{padding:"12px 16px"}}><StatusBadge status={inv.status}/></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
            <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.border}`,fontSize:13,fontWeight:700,color:C.ink}}>Aging Summary</div>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
              <thead>
                <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                  {["Age Bucket","Invoices","Amount","% of Total"].map(h=>(
                    <th key={h} style={{padding:"10px 16px",textAlign:"left",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {BUCKETS.map(b=>(
                  <tr key={b.key} style={{borderBottom:`1px solid ${C.border}20`}}>
                    <td style={{padding:"12px 16px"}}><Badge label={b.label} color={b.color} bg={b.color+"15"}/></td>
                    <td style={{padding:"12px 16px",color:C.inkMid}}>{(buckets[b.key]||[]).length}</td>
                    <td style={{padding:"12px 16px",fontWeight:700,color:b.color}}>{fmt(totals[b.key])}</td>
                    <td style={{padding:"12px 16px",color:C.inkMid}}>{totals.grand?Math.round(totals[b.key]/totals.grand*100):0}%</td>
                  </tr>
                ))}
                <tr style={{background:C.bg,borderTop:`2px solid ${C.border}`}}>
                  <td style={{padding:"12px 16px",fontWeight:800}}>TOTAL</td>
                  <td style={{padding:"12px 16px",fontWeight:800}}>{Object.values(buckets).reduce((s,b)=>s+(b||[]).length,0)}</td>
                  <td style={{padding:"12px 16px",fontWeight:800,color:C.accent}}>{fmt(totals.grand)}</td>
                  <td style={{padding:"12px 16px",fontWeight:800}}>100%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── CREDITORS ─────────────────────────────────────────────────────────────────
function Creditors({live = {}}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const [bucketFilter, setBucketFilter] = useState("all");

  useEffect(() => {
    api("/reports/creditors-aging").then(setData).catch(()=>null).finally(()=>setLoading(false));
  }, []);

  // Refresh when a PO is received or paid
  useEffect(() => {
    if (live.purchaseOrders) {
      api("/reports/creditors-aging").then(setData).catch(()=>null);
    }
  }, [live.purchaseOrders]); // eslint-disable-line

  const BUCKETS = [
    {key:"not_due",  label:"Not Yet Due",   color:C.blue},
    {key:"current",  label:"0 – 30 Days",   color:C.green},
    {key:"31_60",    label:"31 – 60 Days",  color:C.gold},
    {key:"61_90",    label:"61 – 90 Days",  color:C.accent},
    {key:"over_90",  label:"90+ Days",      color:C.red},
  ];

  const mockVendors = [
    {vendor:"Eskom",     total:3200, invoices:[{id:"PO-001",description:"Electricity",amount:3200,received_date:"2026-05-20",due_date:"2026-06-19",days_overdue:0, bucket:"not_due"}]},
    {vendor:"Telkom",    total:1850, invoices:[{id:"PO-002",description:"Fibre + phone",amount:1850,received_date:"2026-04-15",due_date:"2026-05-15",days_overdue:32,bucket:"31_60"}]},
    {vendor:"Discovery", total:4200, invoices:[{id:"PO-003",description:"Business insurance",amount:4200,received_date:"2026-04-22",due_date:"2026-05-22",days_overdue:25,bucket:"current"}]},
  ];
  const mockTotals = {not_due:3200,current:4200,"31_60":1850,"61_90":0,over_90:0,grand:9250};

  const allVendors = data ? data.vendors : mockVendors;
  const totals     = data ? data.totals  : mockTotals;
  const asAt       = data ? data.as_at   : new Date().toLocaleDateString("en-ZA",{day:"2-digit",month:"long",year:"numeric"});

  // Filter vendors by selected bucket — only show vendors that have items in that bucket
  const vendors = bucketFilter === "all"
    ? allVendors
    : allVendors
        .map(v => ({...v, invoices: v.invoices.filter(i => i.bucket === bucketFilter)}))
        .filter(v => v.invoices.length > 0)
        .map(v => ({...v, total: v.invoices.reduce((s,i) => s+i.amount, 0)}));

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-end",marginBottom:20}}>
        <div>
          <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:0}}>Creditors Book</h2>
          <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>Accounts payable by vendor — as at {asAt}</p>
        </div>
        {!data && <Badge label="Demo Mode" color={C.gold} bg={C.goldLt}/>}
      </div>
      {loading && <div style={{textAlign:"center",padding:40,color:C.inkMid}}>Loading creditors...</div>}
      {!loading && (
        <div>
          {/* Summary cards — click to filter table */}
          <div style={{display:"flex",gap:12,marginBottom:24,flexWrap:"wrap"}}>
            {BUCKETS.map(b=>{
              const active = bucketFilter === b.key;
              return (
                <div key={b.key} onClick={()=>setBucketFilter(active?"all":b.key)}
                  style={{flex:1,minWidth:130,background:active?b.color:C.surface,border:`2px solid ${active?b.color:C.border}`,borderRadius:14,padding:16,cursor:"pointer",transition:"all 0.15s"}}
                  onMouseEnter={e=>{if(!active)e.currentTarget.style.borderColor=b.color;}}
                  onMouseLeave={e=>{if(!active)e.currentTarget.style.borderColor=C.border;}}>
                  <div style={{fontSize:10,color:active?"rgba(255,255,255,0.75)":C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:8}}>{b.label}</div>
                  <div style={{fontSize:20,fontWeight:800,color:active?"#fff":b.color,marginBottom:4}}>{fmt(totals[b.key]||0)}</div>
                  {active && <div style={{fontSize:10,color:"rgba(255,255,255,0.75)",marginTop:2}}>▼ Filtering</div>}
                </div>
              );
            })}
            <div onClick={()=>setBucketFilter("all")}
              style={{flex:1,minWidth:130,background:bucketFilter==="all"?C.ink:C.surface,border:`2px solid ${bucketFilter==="all"?C.ink:C.border}`,borderRadius:14,padding:16,cursor:"pointer",transition:"all 0.15s"}}>
              <div style={{fontSize:10,color:bucketFilter==="all"?"rgba(255,255,255,0.5)":C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:8}}>Total Creditors</div>
              <div style={{fontSize:20,fontWeight:800,color:bucketFilter==="all"?"#fff":C.ink,marginBottom:4}}>{fmt(totals.grand||0)}</div>
              {bucketFilter==="all" && <div style={{fontSize:10,color:"rgba(255,255,255,0.5)",marginTop:2}}>All shown</div>}
            </div>
          </div>

          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
            <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.border}`,fontSize:13,fontWeight:700,color:C.ink,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <span>Creditor Ledger by Vendor</span>
              {bucketFilter !== "all" && (
                <span style={{fontSize:12,fontWeight:400,color:C.inkMid}}>
                  Showing: <strong style={{color:BUCKETS.find(b=>b.key===bucketFilter)?.color}}>{BUCKETS.find(b=>b.key===bucketFilter)?.label}</strong>
                  {" "}<button onClick={()=>setBucketFilter("all")} style={{marginLeft:8,fontSize:11,color:C.accent,background:"none",border:"none",cursor:"pointer",padding:0,fontFamily:"inherit"}}>✕ Clear</button>
                </span>
              )}
            </div>
            {vendors.length === 0 ? (
              <div style={{textAlign:"center",padding:"40px 0",color:C.inkDim}}>
                <div style={{fontSize:32,marginBottom:8}}>✅</div>
                <div style={{fontSize:14,fontWeight:600}}>No creditors in this bucket</div>
              </div>
            ) : vendors.map((v,vi)=>(
              <div key={vi}>
                <div onClick={()=>setExpanded(expanded===vi?null:vi)}
                  style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"12px 20px",borderBottom:`1px solid ${C.border}20`,cursor:"pointer",background:expanded===vi?C.accentLt:"transparent"}}>
                  <div style={{display:"flex",alignItems:"center",gap:12}}>
                    <span style={{fontSize:14,fontWeight:700,color:C.ink}}>{v.vendor}</span>
                    <Badge label={v.invoices.length+" PO"+(v.invoices.length!==1?"s":"")} color={C.blue} bg={C.blueLt}/>
                  </div>
                  <div style={{display:"flex",alignItems:"center",gap:16}}>
                    <span style={{fontWeight:700,color:C.red}}>{fmt(v.total)}</span>
                    <span style={{fontSize:12,color:C.inkDim}}>{expanded===vi?"▼":"▶"}</span>
                  </div>
                </div>
                {expanded===vi && (
                  <table style={{width:"100%",borderCollapse:"collapse",fontSize:12,background:C.bg}}>
                    <thead>
                      <tr style={{borderBottom:`1px solid ${C.border}`}}>
                        {["PO Ref","Description","Received","Due Date","Overdue","Amount (incl. VAT)"].map(h=>(
                          <th key={h} style={{padding:"9px 20px",textAlign:"left",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {v.invoices.map((exp,i)=>{
                        const bc = BUCKETS.find(b=>b.key===exp.bucket)||BUCKETS[1];
                        return (
                          <tr key={i} style={{borderBottom:`1px solid ${C.border}20`}}>
                            <td style={{padding:"10px 20px",color:C.inkMid,fontSize:11}}>{exp.id}</td>
                            <td style={{padding:"10px 20px"}}>{exp.description}</td>
                            <td style={{padding:"10px 20px",color:C.inkMid}}>{exp.received_date?new Date(exp.received_date).toLocaleDateString("en-ZA",{day:"2-digit",month:"short",year:"numeric"}):"—"}</td>
                            <td style={{padding:"10px 20px",color:C.inkMid}}>{exp.due_date?new Date(exp.due_date).toLocaleDateString("en-ZA",{day:"2-digit",month:"short",year:"numeric"}):"—"}</td>
                            <td style={{padding:"10px 20px"}}>
                              <Badge
                                label={exp.bucket==="not_due" ? `Due in ${exp.days_until_due} day${exp.days_until_due===1?"":"s"}` : `${exp.days_overdue} days`}
                                color={bc.color} bg={bc.color+"15"}/>
                            </td>
                            <td style={{padding:"10px 20px",fontWeight:700,color:C.red}}>{fmt(exp.amount)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot>
                      <tr style={{borderTop:`1px solid ${C.border}`}}>
                        <td colSpan={5} style={{padding:"10px 20px",fontWeight:700,color:C.ink}}>Vendor Total</td>
                        <td style={{padding:"10px 20px",fontWeight:800,color:C.red}}>{fmt(v.total)}</td>
                      </tr>
                    </tfoot>
                  </table>
                )}
              </div>
            ))}
            <div style={{display:"flex",justifyContent:"space-between",padding:"14px 20px",borderTop:`2px solid ${C.border}`,fontWeight:800,fontSize:14}}>
              <span>{bucketFilter==="all"?"TOTAL CREDITORS":`TOTAL — ${BUCKETS.find(b=>b.key===bucketFilter)?.label||""}`}</span>
              <span style={{color:C.red}}>{fmt(bucketFilter==="all"?totals.grand||0:vendors.reduce((s,v)=>s+v.total,0))}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── CHART OF ACCOUNTS ─────────────────────────────────────────────────────────
function ChartOfAccounts() {
  const [accounts, setAccounts] = useState(DEFAULT_COA);
  const [search, setSearch] = useState("");
  const [groupFilter, setGF] = useState("All");
  const [showNew, setShowNew] = useState(false);
  const [showEdit, setShowEdit] = useState(null);
  const [expanded, setExpanded] = useState(new Set(COA_GROUPS));
  const [form, setForm] = useState({code:"",name:"",type:"Detail",group:"Expenses",normal:"Debit",description:""});

  const filtered = accounts.filter(a => {
    const ms = a.name.toLowerCase().includes(search.toLowerCase()) || a.code.includes(search) || a.description.toLowerCase().includes(search.toLowerCase());
    const mg = groupFilter === "All" || a.group === groupFilter;
    return ms && mg;
  });

  const toggleGroup = g => setExpanded(prev => { const n = new Set(prev); n.has(g) ? n.delete(g) : n.add(g); return n; });

  const handleAdd = () => {
    if (!form.code || !form.name) return;
    if (accounts.find(a => a.code === form.code)) { alert("Account code already exists."); return; }
    setAccounts([...accounts,{...form,custom:true}].sort((a,b) => a.code.localeCompare(b.code)));
    setShowNew(false);
    setForm({code:"",name:"",type:"Detail",group:"Expenses",normal:"Debit",description:""});
  };

  const handleEdit = () => { setAccounts(accounts.map(a => a.code === showEdit.code ? {...showEdit} : a)); setShowEdit(null); };

  const grouped = COA_GROUPS.reduce((acc,g) => { acc[g] = filtered.filter(a => a.group === g); return acc; }, {});

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-end",marginBottom:24}}>
        <div>
          <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:0}}>Chart of Accounts</h2>
          <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>IFRS for SMEs - SA-compliant - {accounts.filter(a => !a.inactive).length} active accounts</p>
        </div>
        <button onClick={() => setShowNew(true)} style={{padding:"9px 18px",border:"none",borderRadius:8,background:C.accent,color:"#fff",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>+ Add Account</button>
      </div>
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:"12px 16px",marginBottom:16,display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
        <input type="text" placeholder="Search by code, name or description..." value={search} onChange={e => setSearch(e.target.value)} style={{flex:1,minWidth:200,padding:"8px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
        <select value={groupFilter} onChange={e => setGF(e.target.value)} style={{padding:"8px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:12,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
          <option value="All">All Groups</option>
          {COA_GROUPS.map(g => <option key={g}>{g}</option>)}
        </select>
        <button onClick={() => setExpanded(new Set(COA_GROUPS))} style={{padding:"7px 12px",border:`1px solid ${C.border}`,borderRadius:8,background:"transparent",color:C.inkMid,fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>Expand All</button>
        <button onClick={() => setExpanded(new Set())} style={{padding:"7px 12px",border:`1px solid ${C.border}`,borderRadius:8,background:"transparent",color:C.inkMid,fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>Collapse All</button>
      </div>
      {showNew && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:24,marginBottom:20}}>
          <h3 style={{fontFamily:"serif",fontSize:20,color:C.ink,marginBottom:18}}>Add New Account</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12,marginBottom:12}}>
            {[{l:"Account Code",k:"code",p:"e.g. 6999"},{l:"Account Name",k:"name",p:"e.g. Staff Welfare"}].map(f => (
              <div key={f.k}>
                <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                <input placeholder={f.p} value={form[f.k]} onChange={e => setForm({...form,[f.k]:e.target.value})} style={{width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
              </div>
            ))}
            <div>
              <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Group</label>
              <select value={form.group} onChange={e => setForm({...form,group:e.target.value})} style={{width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                {COA_GROUPS.map(g => <option key={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Type</label>
              <select value={form.type} onChange={e => setForm({...form,type:e.target.value})} style={{width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                <option value="Header">Header</option>
                <option value="Detail">Detail</option>
              </select>
            </div>
            <div>
              <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Normal Balance</label>
              <select value={form.normal} onChange={e => setForm({...form,normal:e.target.value})} style={{width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                <option value="Debit">Debit</option>
                <option value="Credit">Credit</option>
              </select>
            </div>
          </div>
          <div style={{marginBottom:16}}>
            <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Description</label>
            <input placeholder="Brief description" value={form.description} onChange={e => setForm({...form,description:e.target.value})} style={{width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
          </div>
          <div style={{display:"flex",gap:8}}>
            <button onClick={handleAdd} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Add Account</button>
            <button onClick={() => setShowNew(false)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:8,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
          </div>
        </div>
      )}
      {showEdit && (
        <div style={{position:"fixed",inset:0,background:"#00000050",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center"}} onClick={() => setShowEdit(null)}>
          <div style={{background:C.surface,borderRadius:18,padding:32,width:560}} onClick={e => e.stopPropagation()}>
            <h3 style={{fontFamily:"serif",fontSize:20,color:C.ink,marginBottom:20}}>Edit Account - {showEdit.code}</h3>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
              <div>
                <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Account Name</label>
                <input value={showEdit.name} onChange={e => setShowEdit({...showEdit,name:e.target.value})} style={{width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
              </div>
              <div>
                <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Group</label>
                <select value={showEdit.group} onChange={e => setShowEdit({...showEdit,group:e.target.value})} style={{width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                  {COA_GROUPS.map(g => <option key={g}>{g}</option>)}
                </select>
              </div>
            </div>
            <div style={{marginBottom:16}}>
              <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Description</label>
              <input value={showEdit.description} onChange={e => setShowEdit({...showEdit,description:e.target.value})} style={{width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
            </div>
            <div style={{display:"flex",gap:8}}>
              <button onClick={handleEdit} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Save Changes</button>
              <button onClick={() => setShowEdit(null)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:8,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
            </div>
          </div>
        </div>
      )}
      {COA_GROUPS.map(group => {
        const groupAccounts = grouped[group];
        if (!groupAccounts || !groupAccounts.length) return null;
        const gc = GROUP_COLORS[group];
        const isExpanded = expanded.has(group);
        return (
          <div key={group} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,marginBottom:12,overflow:"hidden"}}>
            <div onClick={() => toggleGroup(group)} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"14px 20px",cursor:"pointer",background:gc.bg,borderBottom:isExpanded ? `1px solid ${C.border}` : "none"}}>
              <div style={{display:"flex",alignItems:"center",gap:10}}>
                <span style={{fontSize:20}}>{gc.icon}</span>
                <span style={{fontFamily:"serif",fontSize:16,fontWeight:700,color:gc.color}}>{group}</span>
                <span style={{fontSize:11,background:gc.color+"20",color:gc.color,padding:"2px 8px",borderRadius:10,fontWeight:600}}>{groupAccounts.length} accounts</span>
              </div>
              <span style={{color:gc.color,fontSize:16}}>{isExpanded ? "v" : ">"}</span>
            </div>
            {isExpanded && (
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                <thead>
                  <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                    {["Code","Account Name","Type","Normal Balance","Description",""].map(h => <th key={h} style={{padding:"10px 16px",textAlign:"left",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {groupAccounts.map((acc) => (
                    <tr key={acc.code} style={{borderBottom:`1px solid ${C.border}20`,background:acc.type === "Header" ? C.bg+"80" : "transparent"}}>
                      <td style={{padding:"10px 16px",fontFamily:"monospace",fontWeight:700,color:gc.color,fontSize:12}}>{acc.code}</td>
                      <td style={{padding:"10px 16px",color:C.ink,fontWeight:acc.type === "Header" ? 700 : 400,paddingLeft:acc.type === "Header" ? 16 : 28}}>
                        {acc.type === "Header" ? acc.name : `- ${acc.name}`}
                        {acc.custom && <span style={{fontSize:9,background:C.accentLt,color:C.accent,padding:"1px 6px",borderRadius:8,marginLeft:6,fontWeight:700}}>CUSTOM</span>}
                      </td>
                      <td style={{padding:"10px 16px"}}><span style={{fontSize:10,background:acc.type === "Header" ? C.inkDim+"20" : C.blueLt,color:acc.type === "Header" ? C.inkMid : C.blue,padding:"2px 8px",borderRadius:8,fontWeight:600}}>{acc.type}</span></td>
                      <td style={{padding:"10px 16px"}}><span style={{fontSize:10,background:acc.normal === "Debit" ? C.accentLt : C.greenLt,color:acc.normal === "Debit" ? C.accent : C.green,padding:"2px 8px",borderRadius:8,fontWeight:600}}>{acc.normal}</span></td>
                      <td style={{padding:"10px 16px",color:C.inkMid,fontSize:11,maxWidth:280}}><div style={{overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{acc.description}</div></td>
                      <td style={{padding:"10px 16px",whiteSpace:"nowrap"}}>
                        <button onClick={() => setShowEdit({...acc})} style={{background:C.blueLt,color:C.blue,border:"none",borderRadius:6,padding:"4px 10px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600,marginRight:4}}>Edit</button>
                        <button onClick={() => setAccounts(accounts.map(a => a.code === acc.code ? {...a,inactive:!a.inactive} : a))} style={{background:acc.inactive ? C.greenLt : C.redLt,color:acc.inactive ? C.green : C.red,border:"none",borderRadius:6,padding:"4px 10px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>{acc.inactive ? "Activate" : "Deactivate"}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        );
      })}
    </div>
  );
}
// ── DIRECT BANK FEEDS ─────────────────────────────────────────────────────────
const SA_BANKS = [
  {id:"fnb",          name:"FNB",           logo:"🟢",color:"#007A39"},
  {id:"absa",         name:"ABSA",          logo:"🔴",color:"#C8102E"},
  {id:"standardbank", name:"Standard Bank", logo:"🔵",color:"#0033A0"},
  {id:"nedbank",      name:"Nedbank",       logo:"🟩",color:"#009A44"},
  {id:"capitec",      name:"Capitec",       logo:"🟦",color:"#1E4A8C"},
  {id:"discovery",    name:"Discovery Bank",logo:"🟣",color:"#6B2A8B"},
  {id:"tymebank",     name:"TymeBank",      logo:"🩵",color:"#00B4D8"},
];

function BankFeeds() {
  const [linked,    setLinked]   = useState([]);
  const [showLink,  setShowLink] = useState(false);
  const [linking,   setLinking]  = useState(null);
  const STITCH_CONFIGURED = false; // Set to true once Stitch API credentials are added

  const handleLink = async (bank) => {
    if (!STITCH_CONFIGURED) {
      alert("Direct bank feeds are coming soon! We are completing our integration with Stitch Money. In the meantime, use the Bank Import tab to upload CSV statements.");
      return;
    }
    setLinking(bank);
    // Stitch OAuth flow will go here
    try {
      const res = await api("/bank/link-initiate", {method:"POST", body:JSON.stringify({bank_id: bank.id})});
      window.location.href = res.auth_url; // Redirect to Stitch OAuth
    } catch(e) { alert("Could not initiate bank link: " + e.message); setLinking(null); }
  };

  const handleUnlink = (id) => {
    if(!window.confirm("Unlink this account?")) return;
    setLinked(l => l.filter(a => a.id !== id));
  };

  return (
    <div style={{marginBottom:24}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
        <div>
          <div style={{fontSize:15,fontWeight:700,color:C.ink}}>Direct Bank Feeds</div>
          <div style={{fontSize:12,color:C.inkMid,marginTop:2}}>Connect your bank for automatic transaction imports</div>
        </div>
        <button onClick={()=>setShowLink(o=>!o)} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"9px 18px",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>+ Link Bank Account</button>
      </div>

      {!STITCH_CONFIGURED && (
        <div style={{background:C.goldLt,border:`1px solid ${C.gold}40`,borderRadius:12,padding:"14px 18px",marginBottom:16,display:"flex",gap:12,alignItems:"flex-start"}}>
          <span style={{fontSize:20}}>⏳</span>
          <div>
            <div style={{fontSize:13,fontWeight:700,color:C.gold,marginBottom:4}}>Coming Soon — Stitch Money Integration</div>
            <div style={{fontSize:12,color:C.inkMid,lineHeight:1.6}}>We're finalising our approval with Stitch Money to enable live bank feeds for all major SA banks. Once approved, you'll be able to connect your bank and transactions will import automatically every few hours. Use the CSV import below in the meantime.</div>
          </div>
        </div>
      )}

      {linked.length === 0 ? (
        <div style={{background:C.surface,border:`1px dashed ${C.border}`,borderRadius:14,padding:32,textAlign:"center",color:C.inkMid,fontSize:13}}>
          No bank accounts linked yet. Click <strong>Link Bank Account</strong> to connect.
        </div>
      ) : (
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          {linked.map(acc=>(
            <div key={acc.id} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:"14px 18px",display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <div style={{display:"flex",gap:12,alignItems:"center"}}>
                <span style={{fontSize:24}}>{acc.logo}</span>
                <div>
                  <div style={{fontSize:13,fontWeight:700,color:C.ink}}>{acc.name}</div>
                  <div style={{fontSize:11,color:C.inkMid}}>{acc.accountNumber} · Last synced: {acc.lastSync}</div>
                </div>
              </div>
              <div style={{display:"flex",gap:8,alignItems:"center"}}>
                <Badge label="Connected" color={C.green} bg={C.greenLt}/>
                <button onClick={()=>handleUnlink(acc.id)} style={{background:C.redLt,color:C.red,border:"none",borderRadius:6,padding:"5px 10px",fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>Unlink</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showLink && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:24,marginTop:16}}>
          <div style={{fontSize:14,fontWeight:700,color:C.ink,marginBottom:16}}>Select your bank to connect</div>
          <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
            {SA_BANKS.map(bank=>(
              <button key={bank.id} onClick={()=>handleLink(bank)} disabled={!!linking}
                style={{display:"flex",alignItems:"center",gap:8,padding:"12px 18px",borderRadius:12,border:`2px solid ${C.border}`,background:C.bg,cursor:"pointer",fontFamily:"inherit",fontSize:13,fontWeight:600,color:C.ink,opacity:linking?0.6:1}}>
                <span style={{fontSize:22}}>{bank.logo}</span>{bank.name}
              </button>
            ))}
          </div>
          <button onClick={()=>setShowLink(false)} style={{marginTop:16,background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:8,padding:"8px 16px",fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
        </div>
      )}
    </div>
  );
}

// ── BANK IMPORT ───────────────────────────────────────────────────────────────
function BankImport({live = {}, onNavigate}) {
  const [step, setStep] = useState("select");
  const [bank, setBank] = useState(null);
  const [txns, setTxns] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState("");
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);
  const [search, setSearch] = useState("");
  const [filterType, setFilter] = useState("all");
  const fileRef = useRef(null);

  const processFile = f => {
    if (!bank) { setError("Please select your bank first."); return; }
    if (!f.name.endsWith(".csv")) { setError("Please upload a CSV file."); return; }
    setError(""); setFileName(f.name);
    const bfmt = BANK_FORMATS[bank];
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const rows = e.target.result.split("\n").filter(l => l.trim()).map(l => parseCSVLine(l));
        const data = rows.slice(bfmt.skipRows);
        const parsed = data
          .filter(r => r.length > Math.max(bfmt.dateCol, bfmt.descCol, bfmt.amtCol))
          .map((r,i) => {
            const amt = parseAmt(r[bfmt.amtCol]);
            const desc = r[bfmt.descCol] || "Unknown";
            return {id:i+1,date:parseDt(r[bfmt.dateCol]),description:desc,amount:Math.abs(amt),type:amt < 0 ? "debit" : "credit",category:autoCategory(desc),hasVat:false,vatAmount:0};
          })
          .filter(t => t.amount > 0);
        if (!parsed.length) { setError("No transactions found. Check you selected the correct bank."); return; }
        setTxns(parsed);
        setSelected(new Set(parsed.filter(t => t.type === "debit").map(t => t.id)));
        setStep("preview");
      } catch(err) { setError("Could not read file. Check it is a valid CSV bank statement."); }
    };
    reader.readAsText(f);
  };

  const toggleRow = id => setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const updateCat = (id,cat) => setTxns(prev => prev.map(t => t.id === id ? {...t,category:cat} : t));
  const filtered = txns.filter(t => t.description.toLowerCase().includes(search.toLowerCase()) && (filterType === "all" || t.type === filterType));
  const selectedTxns = txns.filter(t => selected.has(t.id));
  const totalDebits = selectedTxns.filter(t => t.type === "debit").reduce((s,t) => s + t.amount, 0);

  const handleImport = async () => {
    setImporting(true);
    setError("");
    try {
      const token = localStorage.getItem("zuzan_token");
      const payload = {
        bank,
        transactions: selectedTxns.map(t => ({
          date:        t.date,
          description: t.description,
          amount:      t.amount,
          type:        t.type,
          category:    t.category,
          has_vat:     t.hasVat || false,
          vat_amount:  t.vatAmount || 0,
        }))
      };

      // If no token or demo token, skip backend and save locally
      if (!token || token.startsWith("demo_")) {
        await new Promise(r => setTimeout(r, 1000));
        setResult({
          expenses_created: selectedTxns.filter(t => t.type === "debit").length,
          expenses_skipped: 0,
          credits_recorded: selectedTxns.filter(t => t.type === "credit").length,
          message: "Saved locally (demo mode)",
        });
        setStep("done");
        return;
      }

      const res = await fetch(`${BASE_URL}/bank/import`, {
        method:  "POST",
        headers: {"Content-Type":"application/json", "Authorization":`Bearer ${token}`},
        body:    JSON.stringify(payload),
      });
      const data = await res.json();

      // Session expired — remove token and prompt re-login (do NOT write a demo_ token)
      if (res.status === 401) {
        localStorage.removeItem("zuzan_token");
        throw new Error("Your session has expired. Please log in again.");
      }

      if (!res.ok) throw new Error(data.detail || "Import failed");
      setResult(data);
      setStep("done");
    } catch(err) {
      // Network error — save in demo mode
      if (err.message.includes("fetch") || err.message.includes("network") || err.message.includes("Failed")) {
        setResult({
          expenses_created: selectedTxns.filter(t => t.type === "debit").length,
          expenses_skipped: 0,
          credits_recorded: selectedTxns.filter(t => t.type === "credit").length,
          message: "Saved locally (backend offline)",
        });
        setStep("done");
      } else {
        setError(`Import failed: ${err.message}`);
      }
    } finally {
      setImporting(false);
    }
  };

  const reset = () => { setStep("select"); setTxns([]); setBank(null); setFileName(""); setSelected(new Set()); setResult(null); setError(""); };

  // Reload live data and navigate when import completes
  useEffect(() => {
    if (step === "done") {
      if (live && typeof live.reload === "function") live.reload();
    }
  }, [step]); // eslint-disable-line

  return (
    <div>
      <div style={{marginBottom:24}}>
        <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:0}}>Bank</h2>
        <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>Connect your bank or import a CSV statement</p>
      </div>
      <BankFeeds/>
      <div style={{borderTop:`2px solid ${C.border}`,paddingTop:20,marginBottom:20}}>
        <div style={{fontSize:15,fontWeight:700,color:C.ink,marginBottom:4}}>CSV Statement Import</div>
        <div style={{fontSize:12,color:C.inkMid}}>Upload a bank statement CSV to import transactions manually</div>
      </div>
      <div style={{display:"flex",background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,overflow:"hidden",width:"fit-content",marginBottom:24}}>
        {[["select","1. Select Bank"],["preview","2. Preview"],["categorise","3. Categorise"],["done","4. Done"]].map(([id,label],i) => {
          const steps = ["select","preview","categorise","done"];
          const done = steps.indexOf(id) < steps.indexOf(step);
          const active = id === step;
          return <div key={id} style={{padding:"10px 18px",fontSize:12,fontWeight:active?700:400,color:active?C.accent:done?C.green:C.inkDim,background:active?C.accentLt:"transparent",borderRight:i<3?`1px solid ${C.border}`:"none"}}>{done ? "done " : ""}{label}</div>;
        })}
      </div>
      {step === "select" && (
        <div>
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:24,marginBottom:16}}>
            <div style={{fontSize:14,fontWeight:700,color:C.ink,marginBottom:16}}>Select Your Bank</div>
            <div style={{display:"flex",gap:12,flexWrap:"wrap"}}>
              {Object.entries(BANK_FORMATS).map(([key,b]) => (
                <div key={key} onClick={() => setBank(key)} style={{padding:"16px 20px",border:`2px solid ${bank===key?C.accent:C.border}`,borderRadius:12,cursor:"pointer",textAlign:"center",background:bank===key?C.accentLt:C.bg,minWidth:100}}>
                  <div style={{fontSize:28,marginBottom:6}}>{b.logo}</div>
                  <div style={{fontSize:12,fontWeight:700,color:bank===key?C.accent:C.ink}}>{b.name}</div>
                </div>
              ))}
            </div>
          </div>
          <div style={{background:C.surface,border:`2px dashed ${C.border}`,borderRadius:16,padding:48,textAlign:"center",cursor:"pointer"}}
            onClick={() => fileRef.current && fileRef.current.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); processFile(e.dataTransfer.files[0]); }}>
            <div style={{fontSize:48,marginBottom:12}}>📂</div>
            <div style={{fontSize:15,fontWeight:700,color:C.ink,marginBottom:8}}>Upload Bank Statement</div>
            <div style={{fontSize:13,color:C.inkMid,marginBottom:20}}>Drag and drop your CSV file here or click to browse</div>
            <button style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 24px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Browse Files</button>
            <div style={{fontSize:11,color:C.inkDim,marginTop:14}}>Supported: CSV from FNB, ABSA, Standard Bank, Nedbank, Capitec, Discovery Bank, Investec, TymeBank</div>
            <input ref={fileRef} type="file" accept=".csv" style={{display:"none"}} onChange={e => processFile(e.target.files[0])}/>
          </div>
          {error && <div style={{background:C.redLt,border:`1px solid ${C.red}40`,borderRadius:10,padding:"12px 16px",marginTop:14,fontSize:13,color:C.red}}>Warning: {error}</div>}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:22,marginTop:16}}>
            <div style={{fontSize:13,fontWeight:700,color:C.ink,marginBottom:14}}>How to download your bank statement CSV</div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
              {[
                ["FNB","Online Banking - Accounts - Transaction History - Export - CSV"],
                ["ABSA","Online Banking - Accounts - View Statements - Download - CSV"],
                ["Standard Bank","Online Banking - Accounts - Transaction History - Export CSV"],
                ["Nedbank","Online Banking - Accounts - Account Activity - Export - CSV"],
                ["Capitec","Capitec App or Online - Transactions - Export - CSV format"],
                ["Discovery Bank","Discovery Bank App - Accounts - Statements - Download CSV"],
                ["Investec","Investec Online - Accounts - Transaction History - Export CSV"],
                ["TymeBank","TymeBank App - Accounts - Transactions - Export - CSV"],
              ].map(([b,s]) => (
                <div key={b} style={{background:C.bg,borderRadius:8,padding:"10px 14px"}}>
                  <div style={{fontSize:12,fontWeight:700,color:C.ink,marginBottom:4}}>{b}</div>
                  <div style={{fontSize:11,color:C.inkMid,lineHeight:1.6}}>{s}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {step === "preview" && (
        <div>
          <div style={{display:"flex",gap:12,marginBottom:16}}>
            <KPI label="Transactions" value={txns.length} color={C.ink} icon="📊"/>
            <KPI label="Expenses" value={fmt(totalDebits)} color={C.red} icon="📤" sub={`${selectedTxns.filter(t=>t.type==="debit").length} selected`}/>
            <KPI label="Bank" value={BANK_FORMATS[bank] ? BANK_FORMATS[bank].name : ""} color={C.blue} icon="🏦" sub={fileName}/>
          </div>
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:"12px 16px",marginBottom:14,display:"flex",gap:10,alignItems:"center"}}>
            <input type="text" placeholder="Search..." value={search} onChange={e => setSearch(e.target.value)} style={{flex:1,padding:"8px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
            {["all","debit","credit"].map(f => <button key={f} onClick={() => setFilter(f)} style={{padding:"7px 14px",borderRadius:8,border:`1px solid ${filterType===f?C.accent:C.border}`,background:filterType===f?C.accentLt:"transparent",color:filterType===f?C.accent:C.inkMid,fontSize:12,fontWeight:filterType===f?700:400,cursor:"pointer",fontFamily:"inherit"}}>{f==="all"?"All":f==="debit"?"Expenses":"Income"}</button>)}
            <span style={{fontSize:12,color:C.inkMid}}>{selected.size} selected</span>
          </div>
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,overflow:"hidden",marginBottom:16,maxHeight:400,overflowY:"auto"}}>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
              <thead style={{position:"sticky",top:0}}>
                <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                  <th style={{padding:"11px 14px",textAlign:"left",width:40}}>
                    <input type="checkbox" onChange={() => { if (selected.size === filtered.length) setSelected(new Set()); else setSelected(new Set(filtered.map(t => t.id))); }} checked={selected.size === filtered.length && filtered.length > 0}/>
                  </th>
                  {["Date","Description","Type","Amount","Account","VAT","VAT Amt"].map(h => <th key={h} style={{padding:"11px 14px",textAlign:"left",fontSize:10,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0,100).map(t => (
                  <tr key={t.id} style={{borderBottom:`1px solid ${C.border}20`,opacity:selected.has(t.id)?1:0.4}}>
                    <td style={{padding:"10px 14px"}}><input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleRow(t.id)}/></td>
                    <td style={{padding:"10px 14px",color:C.inkMid,fontSize:11,fontFamily:"monospace"}}>{t.date}</td>
                    <td style={{padding:"10px 14px",color:C.ink,maxWidth:240}}><div style={{overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{t.description}</div></td>
                    <td style={{padding:"10px 14px"}}><Badge label={t.type==="debit"?"Expense":"Income"} color={t.type==="debit"?C.red:C.green} bg={t.type==="debit"?C.redLt:C.greenLt}/></td>
                    <td style={{padding:"10px 14px",fontWeight:700,color:t.type==="debit"?C.red:C.green}}>{t.type==="debit"?"-":"+"}{fmt(t.amount)}</td>
                    <td style={{padding:"10px 14px"}}>
                      <select value={t.category} onChange={e => updateCat(t.id,e.target.value)} style={{padding:"4px 8px",border:`1px solid ${C.border}`,borderRadius:6,fontSize:11,fontFamily:"inherit",background:C.bg,color:C.ink,maxWidth:180}}>
                        <option value="">-- Select Account --</option>
                        {COA_GROUPS.map(group => (
                          <optgroup key={group} label={group}>
                            {DEFAULT_COA.filter(a => a.group === group && a.type === "Detail").map(a => (
                              <option key={a.code} value={`${a.code} - ${a.name}`}>{a.code} - {a.name}</option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    </td>
                    <td style={{padding:"10px 14px",textAlign:"center"}}>
                      <input type="checkbox" checked={t.hasVat} title="This transaction includes VAT (15%)"
                        onChange={e => setTxns(prev => prev.map(tx => tx.id === t.id ? {...tx, hasVat:e.target.checked, vatAmount:e.target.checked ? Math.round((t.amount / 115) * 15 * 100) / 100 : 0} : tx))}
                        style={{cursor:"pointer",width:16,height:16}}/>
                    </td>
                    <td style={{padding:"10px 14px",fontSize:11,color:t.hasVat?C.accent:C.inkDim,fontWeight:t.hasVat?700:400}}>
                      {t.hasVat ? fmt(t.vatAmount) : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{display:"flex",gap:10}}>
            <button onClick={() => setStep("select")} style={{padding:"11px 22px",border:`1px solid ${C.border}`,borderRadius:10,background:"transparent",color:C.inkMid,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Back</button>
            <button onClick={() => setStep("categorise")} style={{flex:1,padding:"11px",border:"none",borderRadius:10,background:C.accent,color:"#fff",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Review Categories ({selected.size} transactions)</button>
          </div>
        </div>
      )}
      {step === "categorise" && (
        <div>
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:24,marginBottom:16}}>
            <div style={{fontSize:14,fontWeight:700,color:C.ink,marginBottom:6}}>Review Categories</div>
            <div style={{fontSize:12,color:C.inkMid,marginBottom:18}}>Adjust any categories before importing into ZuZan.</div>
            <div style={{maxHeight:360,overflowY:"auto"}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                <thead style={{position:"sticky",top:0}}>
                  <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                    {["Date","Description","Amount","Account","VAT","VAT Amt"].map(h => <th key={h} style={{padding:"10px 14px",textAlign:"left",fontSize:10,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {selectedTxns.filter(t => t.type === "debit").map(t => (
                    <tr key={t.id} style={{borderBottom:`1px solid ${C.border}20`}}>
                      <td style={{padding:"10px 14px",color:C.inkMid,fontSize:11,fontFamily:"monospace"}}>{t.date}</td>
                      <td style={{padding:"10px 14px",color:C.ink}}>{t.description}</td>
                      <td style={{padding:"10px 14px",fontWeight:700,color:C.red}}>-{fmt(t.amount)}</td>
                      <td style={{padding:"10px 14px"}}>
                        <select value={t.category} onChange={e => updateCat(t.id,e.target.value)} style={{padding:"5px 8px",border:`1px solid ${C.border}`,borderRadius:6,fontSize:11,fontFamily:"inherit",background:C.bg,color:C.ink,maxWidth:180}}>
                          <option value="">-- Select Account --</option>
                          {COA_GROUPS.map(group => (
                            <optgroup key={group} label={group}>
                              {DEFAULT_COA.filter(a => a.group === group && a.type === "Detail").map(a => (
                                <option key={a.code} value={`${a.code} - ${a.name}`}>{a.code} - {a.name}</option>
                              ))}
                            </optgroup>
                          ))}
                        </select>
                      </td>
                      <td style={{padding:"10px 14px",textAlign:"center"}}>
                        <input type="checkbox" checked={t.hasVat||false} title="Includes VAT at 15%"
                          onChange={e => setTxns(prev => prev.map(tx => tx.id === t.id ? {...tx,hasVat:e.target.checked,vatAmount:e.target.checked?Math.round((t.amount/115)*15*100)/100:0} : tx))}
                          style={{cursor:"pointer",width:16,height:16}}/>
                      </td>
                      <td style={{padding:"10px 14px",fontSize:11,color:t.hasVat?C.accent:C.inkDim,fontWeight:t.hasVat?700:400}}>
                        {t.hasVat ? fmt(t.vatAmount||0) : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {error && <div style={{background:C.redLt,border:`1px solid ${C.red}40`,borderRadius:10,padding:"12px 16px",marginBottom:14,fontSize:13,color:C.red}}>Warning: {error}</div>}
          <div style={{background:C.ink,borderRadius:14,padding:"18px 24px",marginBottom:16,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <div>
              <div style={{fontSize:11,color:"rgba(255,255,255,0.4)",marginBottom:4}}>IMPORT SUMMARY</div>
              <div style={{fontSize:14,color:"#fff",fontWeight:600}}>{selectedTxns.filter(t=>t.type==="debit").length} expenses - {fmt(totalDebits)}</div>
            </div>
            <button onClick={handleImport} disabled={importing} style={{background:importing?C.inkDim:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"12px 24px",fontSize:13,fontWeight:700,cursor:importing?"wait":"pointer",fontFamily:"inherit"}}>{importing ? "Importing..." : "Import to ZuZan"}</button>
          </div>
          <button onClick={() => setStep("preview")} style={{padding:"10px 22px",border:`1px solid ${C.border}`,borderRadius:10,background:"transparent",color:C.inkMid,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Back</button>
        </div>
      )}
      {step === "done" && (
        <div style={{textAlign:"center",maxWidth:520,margin:"40px auto"}}>
          <div style={{fontSize:64,marginBottom:16}}>🎉</div>
          <h2 style={{fontFamily:"serif",fontSize:30,color:C.ink,marginBottom:12}}>Import Complete!</h2>
          <p style={{color:C.inkMid,fontSize:14,lineHeight:1.7,marginBottom:28}}>
            Successfully imported <strong style={{color:C.ink}}>{result ? result.expenses_created : 0} expenses</strong> totalling <strong style={{color:C.red}}>{fmt(totalDebits)}</strong> into ZuZan.
          </p>
          <div style={{display:"flex",gap:10,justifyContent:"center"}}>
            <button onClick={reset} style={{padding:"11px 22px",border:`1px solid ${C.border}`,borderRadius:10,background:"transparent",color:C.inkMid,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Upload Another</button>
            <button onClick={() => { if (typeof onNavigate === "function") onNavigate("expenses"); }} style={{padding:"11px 24px",border:"none",borderRadius:10,background:C.accent,color:"#fff",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>View Expenses</button>
          </div>
        </div>
      )}
    </div>
  );
}
// ── SETTINGS ──────────────────────────────────────────────────────────────────
function AppSettings({user, onLogout, onUserUpdate, docTemplate, onTemplateChange}) {
  const [settingsTab, setSettingsTab] = useState("company"); // company | templates | developer
  const [form, setForm] = useState({
    companyName:          user?.companyName          || "",
    regNumber:            user?.regNumber            || "",
    industry:             user?.industry             || "",
    vatNumber:            user?.vatNumber            || "",
    bankName:             user?.bankName             || "",
    bankAccount:          user?.bankAccount          || "",
    branchCode:           user?.branchCode           || "",
    bankingDetails:       user?.bankingDetails       || "",
    payfastMerchantId:    user?.payfastMerchantId    || "",
    payfastMerchantKey:   user?.payfastMerchantKey   || "",
    logoUrl:              user?.logoUrl              || "",
    cipcRegistrationDate: user?.cipcRegistrationDate || "",
  });
  const [saved, setSaved] = useState(false);
  const [showUpgrade,  setShowUpgrade]  = useState(false);
  const [showBilling,  setShowBilling]  = useState(false);
  const [upgradeBilling, setUpgradeBilling] = useState("monthly");
  const [upgrading,    setUpgrading]    = useState(false);
  const [upgradeMsg,   setUpgradeMsg]   = useState("");

  const handleUpgrade = async (planId) => {
    setUpgrading(true); setUpgradeMsg("");
    try {
      await api("/companies/me", {method:"PUT", body: JSON.stringify({plan: planId})});
      setUpgradeMsg("✓ Plan updated successfully.");
      setTimeout(() => { setShowUpgrade(false); setUpgradeMsg(""); }, 1500);
    } catch(e) { setUpgradeMsg("Failed to update plan. " + (e.message||"")); }
    setUpgrading(false);
  };

  const handleCancelSub = async () => {
    if (!window.confirm("Are you sure you want to cancel your subscription? Your account will revert to the free tier at the end of your billing period.")) return;
    try {
      await api("/companies/me", {method:"PUT", body: JSON.stringify({subscription_status: "cancelled"})});
      alert("Your subscription has been cancelled. You will retain access until the end of your current billing period.");
    } catch(e) { alert("Could not cancel subscription. Please email support@solutha.co.za."); }
  };
  const [pinForm, setPinForm] = useState({newPin:"", confirmPin:""});
  const [pinMsg,  setPinMsg]  = useState("");
  const [pinSaving, setPinSaving] = useState(false);

  const handleSetPin = async () => {
    if (!pinForm.newPin || pinForm.newPin.length < 4) { setPinMsg("PIN must be at least 4 digits."); return; }
    if (pinForm.newPin !== pinForm.confirmPin) { setPinMsg("PINs do not match."); return; }
    setPinSaving(true); setPinMsg("");
    try {
      await api("/companies/payroll-pin", {method:"PUT", body: JSON.stringify({pin: pinForm.newPin})});
      setPinMsg("✓ Payroll PIN updated successfully."); setPinForm({newPin:"", confirmPin:""});
    } catch(e) { setPinMsg("Failed to save PIN. " + (e.message||"")); }
    setPinSaving(false);
  };

  const handleSave = async () => {
    try {
      await api("/companies/me", { method:"PUT", body: JSON.stringify({
        name:                   form.companyName,
        reg_number:             form.regNumber,
        industry:               form.industry,
        vat_number:             form.vatNumber,
        bank_name:              form.bankName,
        bank_account:           form.bankAccount,
        branch_code:            form.branchCode,
        logo_url:               form.logoUrl || null,
        cipc_registration_date: form.cipcRegistrationDate || null,
      })});
    } catch(e) { console.warn("Settings save failed:", e.message); }
    // Update local user context
    if (onUserUpdate) onUserUpdate({
      ...user,
      companyName:    form.companyName,
      regNumber:      form.regNumber,
      industry:       form.industry,
      vatNumber:      form.vatNumber,
      bankName:       form.bankName,
      bankAccount:    form.bankAccount,
      branchCode:     form.branchCode,
      bankingDetails:    `${form.bankName} - Acc: ${form.bankAccount} - Branch: ${form.branchCode}`,
      payfastMerchantId: form.payfastMerchantId,
      payfastMerchantKey:form.payfastMerchantKey,
      logoUrl:           form.logoUrl,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const inputStyle = {width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"};
  const labelStyle = {fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5};

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-end",marginBottom:24}}>
        <div>
          <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:0}}>Settings</h2>
          <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>Manage your ZuZan account</p>
        </div>
        <div style={{display:"flex",gap:4,background:C.bg,border:`1px solid ${C.border}`,borderRadius:10,padding:4}}>
          {[["company","⚙️ General"],["templates","🎨 Templates"],["developer","🔑 Developer API"]].map(([id,label])=>(
            <button key={id} onClick={()=>setSettingsTab(id)} style={{padding:"7px 16px",borderRadius:7,border:"none",cursor:"pointer",fontSize:12,fontWeight:settingsTab===id?700:400,background:settingsTab===id?C.surface:"transparent",color:settingsTab===id?C.ink:C.inkMid,fontFamily:"inherit",boxShadow:settingsTab===id?"0 1px 4px rgba(0,0,0,0.08)":"none"}}>{label}</button>
          ))}
        </div>
      </div>

      {settingsTab === "developer" ? <Developer/> : settingsTab === "templates" ? (
        <div>
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:24,marginBottom:16}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
              <div>
                <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase"}}>Document Templates</div>
                <div style={{fontSize:12,color:C.inkMid,marginTop:4}}>Customise how your invoices and quotes look when printed or shared.</div>
              </div>
              <button onClick={()=>{if(onTemplateChange)onTemplateChange(DEFAULT_DOC_TEMPLATE);}} style={{padding:"7px 14px",background:C.bg,border:`1px solid ${C.border}`,borderRadius:8,fontSize:11,color:C.inkMid,cursor:"pointer",fontFamily:"inherit"}}>Reset to Default</button>
            </div>
            <DocumentTemplateSettings template={docTemplate} onChange={tmpl=>{if(onTemplateChange)onTemplateChange(tmpl);}}/>
          </div>
        </div>
      ) : <>
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:24,marginBottom:16}}>
        <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Subscription</div>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
          <div>
            <div style={{fontSize:16,fontWeight:700,color:C.ink}}>{user?.plan?.name || "Professional"} Plan</div>
            <div style={{fontSize:12,color:C.inkMid,marginTop:3}}>Trial ends in 9 days</div>
          </div>
          <Badge label="Trial Active" color={C.gold} bg={C.goldLt}/>
        </div>
        <div style={{display:"flex",gap:8}}>
          <button onClick={()=>setShowUpgrade(true)} style={{padding:"9px 18px",background:C.accentLt,border:`1px solid ${C.accent}40`,borderRadius:8,color:C.accent,fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Upgrade Plan</button>
          <button onClick={()=>setShowBilling(true)} style={{padding:"9px 18px",background:"transparent",border:`1px solid ${C.border}`,borderRadius:8,color:C.inkMid,fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>Manage Billing</button>
        </div>
      </div>

      {/* Company Logo */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:24,marginBottom:16}}>        <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Company Logo</div>
        <div style={{display:"flex",alignItems:"center",gap:20,marginBottom:12}}>
          {form.logoUrl
            ? <img src={form.logoUrl} alt="Logo" style={{height:64,maxWidth:200,objectFit:"contain",borderRadius:8,border:`1px solid ${C.border}`,background:"#fff",padding:4}}/>
            : <div style={{width:120,height:64,borderRadius:8,border:`2px dashed ${C.border}`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,color:C.inkMid}}>No logo</div>
          }
          <div>
            <input type="file" accept="image/*" id="logo-upload" style={{display:"none"}} onChange={e=>{
              const file=e.target.files[0]; if(!file)return;
              if(file.size>500000){alert("Logo must be under 500KB. Please resize and try again.");return;}
              const reader=new FileReader();
              reader.onload=ev=>setForm(v=>({...v,logoUrl:ev.target.result}));
              reader.readAsDataURL(file);
            }}/>
            <label htmlFor="logo-upload" style={{display:"inline-block",padding:"8px 16px",background:C.accentLt,border:`1px solid ${C.accent}40`,borderRadius:8,color:C.accent,fontSize:12,fontWeight:700,cursor:"pointer"}}>Upload Logo</label>
            {form.logoUrl && <button onClick={()=>setForm(v=>({...v,logoUrl:""}))} style={{marginLeft:8,padding:"8px 14px",background:C.redLt,border:`1px solid ${C.red}30`,borderRadius:8,color:C.red,fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Remove</button>}
            <div style={{fontSize:11,color:C.inkMid,marginTop:6}}>PNG, JPG or SVG · Max 500KB · Shown on invoices & quotes</div>
          </div>
        </div>
      </div>

      {/* Company Details */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:24,marginBottom:16}}>
        <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Company Details</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:16}}>
          {[{l:"Company Name",k:"companyName"},{l:"Registration Number",k:"regNumber"},{l:"Industry",k:"industry"},{l:"VAT Number",k:"vatNumber"},{l:"CIPC Registration Date",k:"cipcRegistrationDate",type:"date",hint:"Used for Annual Return reminders"}].map(f=>(
            <div key={f.k}>
              <label style={labelStyle}>{f.l}{f.hint&&<span style={{fontWeight:400,textTransform:"none",color:C.inkDim,marginLeft:6}}>{f.hint}</span>}</label>
              <input type={f.type||"text"} value={form[f.k]||""} onChange={e=>setForm(v=>({...v,[f.k]:e.target.value}))} style={inputStyle}/>
            </div>
          ))}
        </div>
        <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:12,marginTop:4}}>Banking Details (shown on invoices)</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:14,marginBottom:16}}>
          {[{l:"Bank Name",k:"bankName"},{l:"Account Number",k:"bankAccount"},{l:"Branch Code",k:"branchCode"}].map(f=>(
            <div key={f.k}>
              <label style={labelStyle}>{f.l}</label>
              <input value={form[f.k]} onChange={e=>setForm(v=>({...v,[f.k]:e.target.value}))} style={inputStyle}/>
            </div>
          ))}
        </div>
        <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:12,marginTop:4}}>PayFast Online Payments</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:16}}>
          {[{l:"PayFast Merchant ID",k:"payfastMerchantId",p:"10000100"},{l:"PayFast Merchant Key",k:"payfastMerchantKey",p:"46f0cd694581a"}].map(f=>(
            <div key={f.k}>
              <label style={labelStyle}>{f.l}</label>
              <input placeholder={f.p} value={form[f.k]||""} onChange={e=>setForm(v=>({...v,[f.k]:e.target.value}))} style={inputStyle}/>
            </div>
          ))}
        </div>
        <div style={{background:C.goldLt,borderRadius:8,padding:"10px 14px",marginBottom:16,fontSize:11,color:C.inkMid}}>Get your Merchant ID and Key from <strong>payfast.co.za → Account → Settings → API Credentials</strong></div>
        <div style={{display:"flex",alignItems:"center",gap:12}}>
          <button onClick={handleSave} style={{padding:"9px 22px",background:C.accent,border:"none",borderRadius:8,color:"#fff",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Save Changes</button>
          {saved && <span style={{fontSize:12,color:C.green,fontWeight:600}}>✓ Saved</span>}
        </div>
      </div>

      {/* Payroll PIN Security */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:24,marginBottom:16}}>
        <div style={{fontSize:12,fontWeight:700,color:C.ink,letterSpacing:1,textTransform:"uppercase",marginBottom:4}}>🔒 Payroll PIN</div>
        <p style={{fontSize:12,color:C.inkMid,marginTop:0,marginBottom:16}}>Set a PIN to restrict access to salary and payroll data. Anyone opening Payroll must enter this PIN first.</p>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
          <div>
            <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>New PIN (4–8 digits)</label>
            <input type="password" inputMode="numeric" maxLength={8} placeholder="••••" value={pinForm.newPin}
              onChange={e=>setPinForm(f=>({...f,newPin:e.target.value.replace(/\D/g,"")}))}
              style={{width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:14,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box",letterSpacing:4}}/>
          </div>
          <div>
            <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Confirm PIN</label>
            <input type="password" inputMode="numeric" maxLength={8} placeholder="••••" value={pinForm.confirmPin}
              onChange={e=>setPinForm(f=>({...f,confirmPin:e.target.value.replace(/\D/g,"")}))}
              style={{width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:14,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box",letterSpacing:4}}/>
          </div>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:12}}>
          <button onClick={handleSetPin} disabled={pinSaving} style={{padding:"9px 22px",background:C.accent,border:"none",borderRadius:8,color:"#fff",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:pinSaving?0.6:1}}>{pinSaving?"Saving...":"Set PIN"}</button>
          {pinMsg && <span style={{fontSize:12,color:pinMsg.startsWith("✓")?C.green:C.red,fontWeight:600}}>{pinMsg}</span>}
        </div>
      </div>

      {/* Danger Zone */}
      <div style={{background:C.surface,border:`1px solid ${C.red}40`,borderRadius:16,padding:24}}>
        <div style={{fontSize:12,fontWeight:700,color:C.red,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Danger Zone</div>
        <div style={{display:"flex",gap:8}}>
          <button onClick={onLogout} style={{padding:"9px 18px",background:C.redLt,border:`1px solid ${C.red}40`,borderRadius:8,color:C.red,fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Sign Out</button>
          <button onClick={handleCancelSub} style={{padding:"9px 18px",background:"transparent",border:`1px solid ${C.red}40`,borderRadius:8,color:C.red,fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>Cancel Subscription</button>
        </div>
      </div>
      {/* ── Upgrade Plan Modal ── */}
      {showUpgrade && (
        <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.45)",zIndex:900,display:"flex",alignItems:"center",justifyContent:"center",padding:24}}>
          <div style={{background:C.surface,borderRadius:20,padding:32,width:"100%",maxWidth:520,boxShadow:"0 8px 40px rgba(0,0,0,0.18)"}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:24}}>
              <div style={{fontSize:18,fontWeight:800,color:C.ink}}>Choose a Plan</div>
              <button onClick={()=>{setShowUpgrade(false);setUpgradeMsg("");}} style={{background:"none",border:"none",cursor:"pointer",fontSize:20,color:C.inkMid}}>✕</button>
            </div>
            <div style={{display:"flex",gap:8,marginBottom:24}}>
              {["monthly","annual"].map(t=>(
                <button key={t} onClick={()=>setUpgradeBilling(t)} style={{flex:1,padding:"7px 0",borderRadius:8,border:`1px solid ${C.border}`,background:upgradeBilling===t?C.accent:"transparent",color:upgradeBilling===t?"#fff":C.inkMid,fontWeight:700,fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>
                  {t==="monthly"?"Monthly":"Annual (2 months free)"}
                </button>
              ))}
            </div>
            {PLANS.map(p=>{
              const price = upgradeBilling==="annual" ? Math.round(p.annual/12) : p.monthly;
              const isCurrent = (user?.plan?.id||"professional")===p.id;
              return (
                <div key={p.id} style={{border:`2px solid ${isCurrent?C.accent:C.border}`,borderRadius:12,padding:16,marginBottom:12,background:isCurrent?C.accentLt:"transparent"}}>
                  <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                    <div>
                      <div style={{fontSize:14,fontWeight:800,color:C.ink}}>{p.icon} {p.name}</div>
                      <div style={{fontSize:11,color:C.inkMid,marginTop:3}}>{p.features[0]} · {p.features[1]}</div>
                    </div>
                    <div style={{textAlign:"right"}}>
                      <div style={{fontSize:18,fontWeight:800,color:p.color||C.accent}}>R{price.toLocaleString()}<span style={{fontSize:11,fontWeight:400,color:C.inkMid}}>/mo</span></div>
                      {upgradeBilling==="annual"&&<div style={{fontSize:10,color:C.inkMid}}>billed R{(p.annual).toLocaleString()}/yr</div>}
                    </div>
                  </div>
                  <button
                    onClick={()=>handleUpgrade(p.id)}
                    disabled={upgrading||isCurrent}
                    style={{marginTop:12,width:"100%",padding:"9px 0",borderRadius:8,border:"none",background:isCurrent?C.border:C.accent,color:isCurrent?C.inkMid:"#fff",fontWeight:700,fontSize:12,cursor:isCurrent?"default":"pointer",fontFamily:"inherit",opacity:upgrading?0.6:1}}
                  >{isCurrent?"Current Plan":upgrading?"Updating…":"Select Plan"}</button>
                </div>
              );
            })}
            {upgradeMsg && <div style={{marginTop:12,fontSize:13,color:upgradeMsg.startsWith("✓")?C.green:C.red,fontWeight:600,textAlign:"center"}}>{upgradeMsg}</div>}
          </div>
        </div>
      )}

      {/* ── Manage Billing Modal ── */}
      {showBilling && (
        <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.45)",zIndex:900,display:"flex",alignItems:"center",justifyContent:"center",padding:24}}>
          <div style={{background:C.surface,borderRadius:20,padding:32,width:"100%",maxWidth:440,boxShadow:"0 8px 40px rgba(0,0,0,0.18)"}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:24}}>
              <div style={{fontSize:18,fontWeight:800,color:C.ink}}>Billing</div>
              <button onClick={()=>setShowBilling(false)} style={{background:"none",border:"none",cursor:"pointer",fontSize:20,color:C.inkMid}}>✕</button>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,marginBottom:20}}>
              <div style={{background:C.bg,borderRadius:10,padding:14}}>
                <div style={{fontSize:10,fontWeight:700,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:4}}>Current Plan</div>
                <div style={{fontSize:15,fontWeight:800,color:C.ink}}>{user?.plan?.name||"Professional"}</div>
              </div>
              <div style={{background:C.bg,borderRadius:10,padding:14}}>
                <div style={{fontSize:10,fontWeight:700,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:4}}>Status</div>
                <div style={{fontSize:15,fontWeight:800,color:C.gold}}>Trial Active</div>
              </div>
              <div style={{background:C.bg,borderRadius:10,padding:14}}>
                <div style={{fontSize:10,fontWeight:700,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:4}}>Billing Cycle</div>
                <div style={{fontSize:15,fontWeight:800,color:C.ink}}>Monthly</div>
              </div>
              <div style={{background:C.bg,borderRadius:10,padding:14}}>
                <div style={{fontSize:10,fontWeight:700,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:4}}>Trial Ends</div>
                <div style={{fontSize:15,fontWeight:800,color:C.ink}}>9 days</div>
              </div>
            </div>
            <div style={{background:C.accentLt,border:`1px solid ${C.accent}30`,borderRadius:10,padding:14,marginBottom:20,fontSize:12,color:C.ink,lineHeight:1.6}}>
              Payments are processed securely via <strong>PayFast</strong>. For billing queries, invoice copies, or to update your payment method, email <strong>billing@solutha.co.za</strong>.
            </div>
            <button onClick={()=>setShowBilling(false)} style={{width:"100%",padding:"10px 0",borderRadius:8,border:"none",background:C.accent,color:"#fff",fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Close</button>
          </div>
        </div>
      )}

      </>}
    </div>
  );
}


// ── LOGIN ─────────────────────────────────────────────────────────────────────
function Login({onLogin, onRegister}) {
  const [view,    setView]    = useState("login");   // login | forgot | reset
  const [form,    setForm]    = useState({email:"", password:""});
  const [forgot,  setForgot]  = useState({email:""});
  const [reset,   setReset]   = useState({code:"", password:"", confirm:""});
  const [msg,     setMsg]     = useState("");
  const [resetCode, setResetCode] = useState("");
  const [error,   setError]   = useState("");
  const [loading, setLoading] = useState(false);
  const [serverStatus, setServerStatus] = useState("checking"); // checking | ready | sleeping

  // Ping backend on mount to wake it up before user clicks Sign In
  useEffect(() => {
    const ping = async () => {
      try {
        const res = await fetch("https://zuzan-backend.onrender.com/health", {method:"GET"});
        if (res.ok) { setServerStatus("ready"); return; }
      } catch(e) {}
      setServerStatus("sleeping");
      // Retry every 5s until awake
      const interval = setInterval(async () => {
        try {
          const res = await fetch("https://zuzan-backend.onrender.com/health", {method:"GET"});
          if (res.ok) { setServerStatus("ready"); clearInterval(interval); }
        } catch(e) {}
      }, 5000);
      setTimeout(() => clearInterval(interval), 90000); // give up after 90s
    };
    ping();
  }, []);

  const handleLogin = async () => {
    if (!form.email || !form.password) { setError("Please enter your email and password."); return; }
    setLoading(true); setError("");
    const attempt = async () => {
      const res = await fetch("https://zuzan-backend.onrender.com/auth/login", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({email:form.email, password:form.password}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Invalid email or password.");
      return data;
    };
    try {
      let data;
      try {
        data = await attempt();
      } catch(e) {
        if (e.message.includes("Invalid email") || e.message.includes("password")) throw e;
        // Server likely sleeping — show message and retry once after 8s
        setError("Server is waking up, please wait...");
        await new Promise(r => setTimeout(r, 8000));
        data = await attempt();
      }
      localStorage.setItem("zuzan_token", data.access_token);
      onLogin({firstName:data.user.first_name, lastName:data.user.last_name, email:data.user.email,
        companyName:data.company.name, logoUrl:data.company.logo_url||"", plan:{name:data.company.plan, id:data.company.plan}, access_token:data.access_token, trialEnds:data.company.trial_ends});
    } catch(e) { setError(e.message.includes("fetch") || e.message.includes("network") ? "Could not connect to server. Please try again." : e.message); }
    finally { setLoading(false); }
  };

  const handleForgot = async () => {
    if (!forgot.email) { setError("Please enter your email address."); return; }
    setLoading(true); setError(""); setMsg("");
    try {
      const res = await fetch("https://zuzan-backend.onrender.com/auth/forgot-password", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({email: forgot.email}),
      });
      const data = await res.json();
      setMsg(data.message);
      if (res.ok) { setView("reset"); }
    } catch(e) { setError("Could not connect to server."); }
    finally { setLoading(false); }
  };

  const handleReset = async () => {
    if (!reset.code) { setError("Please enter the reset code."); return; }
    if (!reset.password || reset.password.length < 6) { setError("Password must be at least 6 characters."); return; }
    if (reset.password !== reset.confirm) { setError("Passwords do not match."); return; }
    setLoading(true); setError(""); setMsg("");
    try {
      const res = await fetch("https://zuzan-backend.onrender.com/auth/reset-password", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({token: reset.code, new_password: reset.password}),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Reset failed."); return; }
      setMsg(data.message);
      setTimeout(() => { setView("login"); setMsg(""); setReset({code:"",password:"",confirm:""}); }, 2000);
    } catch(e) { setError("Could not connect to server."); }
    finally { setLoading(false); }
  };

  const inputStyle = {width:"100%",padding:"12px 14px",border:"1.5px solid "+C.border,borderRadius:10,fontSize:14,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"};
  const labelStyle = {display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5};

  return (
    <div style={{minHeight:"100vh",background:C.bg,display:"flex",alignItems:"center",justifyContent:"center",padding:24}}>
      <div style={{width:"100%",maxWidth:420}}>
        <div style={{textAlign:"center",marginBottom:40}}>
          <div style={{fontFamily:"serif",fontSize:40,fontWeight:800,color:C.ink,marginBottom:8}}><span style={{color:C.accent}}>Zu</span>Zan</div>
          <div style={{fontSize:13,color:C.inkMid}}>SA Bookkeeping Platform</div>
        </div>
        <div style={{background:C.surface,border:"1px solid "+C.border,borderRadius:20,padding:36,boxShadow:"0 4px 24px rgba(0,0,0,0.06)"}}>

          {view === "login" && (
            <>
              <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:"0 0 8px"}}>Welcome back</h2>
              <p style={{fontSize:13,color:C.inkMid,marginBottom:16}}>Sign in to your ZuZan account</p>
              {serverStatus === "sleeping" && (
                <div style={{background:C.goldLt,border:`1px solid ${C.gold}40`,borderRadius:8,padding:"10px 14px",marginBottom:16,fontSize:12,color:C.gold,display:"flex",alignItems:"center",gap:8}}>
                  <span>⏳</span> Server is starting up, please wait a moment...
                </div>
              )}
              {serverStatus === "ready" && (
                <div style={{background:C.greenLt,border:`1px solid ${C.green}40`,borderRadius:8,padding:"10px 14px",marginBottom:16,fontSize:12,color:C.green,display:"flex",alignItems:"center",gap:8}}>
                  <span>🟢</span> Server is ready
                </div>
              )}
              <div style={{marginBottom:16}}>
                <label style={labelStyle}>Email Address</label>
                <input type="email" placeholder="you@company.co.za" value={form.email}
                  onChange={e=>setForm({...form,email:e.target.value})}
                  onKeyDown={e=>e.key==="Enter"&&handleLogin()} style={inputStyle}/>
              </div>
              <div style={{marginBottom:8}}>
                <label style={labelStyle}>Password</label>
                <input type="password" placeholder="Your password" value={form.password}
                  onChange={e=>setForm({...form,password:e.target.value})}
                  onKeyDown={e=>e.key==="Enter"&&handleLogin()} style={inputStyle}/>
              </div>
              <div style={{textAlign:"right",marginBottom:20}}>
                <span onClick={()=>{setView("forgot");setError("");setMsg("");}} style={{fontSize:12,color:C.accent,cursor:"pointer",fontWeight:600}}>Forgot password?</span>
              </div>
              {error && <div style={{background:C.redLt,border:"1px solid "+C.red+"30",borderRadius:10,padding:"10px 14px",marginBottom:16,fontSize:13,color:C.red}}>{error}</div>}
              <button onClick={handleLogin} disabled={loading} style={{width:"100%",padding:"13px",border:"none",borderRadius:10,background:loading?C.inkDim:C.accent,color:"#fff",fontSize:15,fontWeight:700,cursor:loading?"wait":"pointer",fontFamily:"inherit",marginBottom:16}}>
                {loading ? "Signing in..." : "Sign In"}
              </button>
              <div style={{textAlign:"center",fontSize:13,color:C.inkMid}}>
                Don't have an account?{" "}
                <span onClick={onRegister} style={{color:C.accent,fontWeight:700,cursor:"pointer"}}>Start free trial</span>
              </div>
            </>
          )}

          {view === "forgot" && (
            <>
              <h2 style={{fontFamily:"serif",fontSize:24,color:C.ink,margin:"0 0 8px"}}>Reset Password</h2>
              <p style={{fontSize:13,color:C.inkMid,marginBottom:28}}>Enter your email address and we'll generate a reset code.</p>
              <div style={{marginBottom:20}}>
                <label style={labelStyle}>Email Address</label>
                <input type="email" placeholder="you@company.co.za" value={forgot.email}
                  onChange={e=>setForgot({...forgot,email:e.target.value})}
                  onKeyDown={e=>e.key==="Enter"&&handleForgot()} style={inputStyle}/>
              </div>
              {error && <div style={{background:C.redLt,border:"1px solid "+C.red+"30",borderRadius:10,padding:"10px 14px",marginBottom:16,fontSize:13,color:C.red}}>{error}</div>}
              {msg && <div style={{background:C.goldLt,border:"1px solid "+C.gold+"30",borderRadius:10,padding:"10px 14px",marginBottom:16,fontSize:13,color:C.gold}}>{msg}</div>}
              <button onClick={handleForgot} disabled={loading} style={{width:"100%",padding:"13px",border:"none",borderRadius:10,background:loading?C.inkDim:C.accent,color:"#fff",fontSize:15,fontWeight:700,cursor:loading?"wait":"pointer",fontFamily:"inherit",marginBottom:16}}>
                {loading ? "Sending..." : "Get Reset Code"}
              </button>
              <div style={{textAlign:"center",fontSize:13,color:C.inkMid}}>
                <span onClick={()=>{setView("login");setError("");setMsg("");}} style={{color:C.accent,fontWeight:700,cursor:"pointer"}}>Back to Sign In</span>
              </div>
            </>
          )}

          {view === "reset" && (
            <>
              <h2 style={{fontFamily:"serif",fontSize:24,color:C.ink,margin:"0 0 8px"}}>Set New Password</h2>
              <p style={{fontSize:13,color:C.inkMid,marginBottom:20}}>Check your email for the reset code, then enter it below with your new password.</p>
              <div style={{marginBottom:14}}>
                <label style={labelStyle}>Reset Code</label>
                <input placeholder="e.g. A3F9B21C" value={reset.code}
                  onChange={e=>setReset({...reset,code:e.target.value.toUpperCase()})}
                  style={{...inputStyle,fontFamily:"monospace",letterSpacing:2,fontSize:16}}/>
              </div>
              <div style={{marginBottom:14}}>
                <label style={labelStyle}>New Password</label>
                <input type="password" placeholder="Min 6 characters" value={reset.password}
                  onChange={e=>setReset({...reset,password:e.target.value})} style={inputStyle}/>
              </div>
              <div style={{marginBottom:20}}>
                <label style={labelStyle}>Confirm New Password</label>
                <input type="password" placeholder="Repeat password" value={reset.confirm}
                  onChange={e=>setReset({...reset,confirm:e.target.value})}
                  onKeyDown={e=>e.key==="Enter"&&handleReset()} style={inputStyle}/>
              </div>
              {error && <div style={{background:C.redLt,border:"1px solid "+C.red+"30",borderRadius:10,padding:"10px 14px",marginBottom:16,fontSize:13,color:C.red}}>{error}</div>}
              {msg   && <div style={{background:C.greenLt,border:"1px solid "+C.green+"30",borderRadius:10,padding:"10px 14px",marginBottom:16,fontSize:13,color:C.green,fontWeight:700}}>{msg}</div>}
              <button onClick={handleReset} disabled={loading} style={{width:"100%",padding:"13px",border:"none",borderRadius:10,background:loading?C.inkDim:C.accent,color:"#fff",fontSize:15,fontWeight:700,cursor:loading?"wait":"pointer",fontFamily:"inherit",marginBottom:16}}>
                {loading ? "Updating..." : "Set New Password"}
              </button>
              <div style={{textAlign:"center",fontSize:13,color:C.inkMid}}>
                <span onClick={()=>{setView("forgot");setError("");setMsg("");setResetCode("");}} style={{color:C.accent,fontWeight:700,cursor:"pointer"}}>Request new code</span>
                {" · "}
                <span onClick={()=>{setView("login");setError("");setMsg("");}} style={{color:C.accent,fontWeight:700,cursor:"pointer"}}>Back to Sign In</span>
              </div>
            </>
          )}

        </div>
        <div style={{textAlign:"center",marginTop:20,fontSize:11,color:C.inkDim}}>
          Secure 256-bit SSL — Powered by PayFast — SARS compliant
        </div>
      </div>
    </div>
  );
}

// ── REGISTRATION ──────────────────────────────────────────────────────────────
function Registration({onComplete, onLogin}) {
  const [step, setStep] = useState(1);
  const [billing, setBilling] = useState("monthly");
  const [selectedPlan, setPlan] = useState(null);
  const [payrollEnabled, setPayroll] = useState(false);
  const [empCount, setEmpCount] = useState(5);
  const [form, setForm] = useState({companyName:"",regNumber:"",industry:"",firstName:"",lastName:"",email:"",phone:"",password:"",confirm:""});
  const [payment, setPayment] = useState({cardNumber:"",expiry:"",cvv:"",cardName:""});
  const [processing, setProcessing] = useState(false);
  const [complete, setComplete] = useState(false);

  const planPrice = selectedPlan ? (billing === "monthly" ? selectedPlan.monthly : Math.round(selectedPlan.annual / 12)) : 0;
  const payrollCost = payrollEnabled ? Math.max(99, Math.round(empCount * 17.50)) : 0;
  const totalMonthly = planPrice + payrollCost;

  const handlePayment = async () => {
    setProcessing(true);
    let token = null;
    let userData = {...form, plan:selectedPlan, billing, payroll:payrollEnabled, employees:empCount};
    try {
      // Register with real backend
      console.log("Registering with backend...", form.email);
      const res = await fetch("https://zuzan-backend.onrender.com/auth/register", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          company_name:    form.companyName || "My Company",
          reg_number:      form.regNumber  || "",
          industry:        form.industry   || "",
          first_name:      form.firstName  || "User",
          last_name:       form.lastName   || "",
          email:           form.email      || `user${Date.now()}@zuzan.co.za`,
          phone:           form.phone      || "",
          password:        (form.password  || "Zuzan2025!").slice(0, 50),
          plan:            selectedPlan ? selectedPlan.id : "starter",
          billing_cycle:   billing || "monthly",
          payroll_enabled: payrollEnabled || false,
          employee_count:  empCount || 0,
        }),
      });
      const data = await res.json();
      console.log("Registration response:", res.status, data);
      if (res.ok && data.access_token) {
        token = data.access_token;
        userData = {...userData, ...data.user, company: data.company};
      } else {
        // Email already registered — try login instead
        if (data.detail && data.detail.includes("already registered")) {
          const loginRes = await fetch("https://zuzan-backend.onrender.com/auth/login", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({email: form.email, password: (form.password || "").slice(0, 50)}),
          });
          const loginData = await loginRes.json();
          if (loginRes.ok && loginData.access_token) {
            token = loginData.access_token;
            userData = {...userData, ...loginData.user};
          }
        }
      }
    } catch(err) {
      console.error("Backend registration error:", err.message);
    }
    // Save token (real or demo)
    console.log("Token obtained:", token ? "REAL TOKEN" : "NO TOKEN - demo mode");
    if (token) {
      localStorage.setItem("zuzan_token", token);
      console.log("Real token saved!");
    } else {
      localStorage.setItem("zuzan_token", "demo_" + Date.now());
      console.log("Demo token saved - backend unreachable");
    }
    setProcessing(false);
    setComplete(true);
    setTimeout(() => onComplete({...userData, access_token: token || "demo"}), 1500);
  };

  if (complete) return (
    <div style={{minHeight:"100vh",background:C.bg,display:"flex",alignItems:"center",justifyContent:"center",padding:24}}>
      <div style={{textAlign:"center",maxWidth:480}}>
        <div style={{fontSize:64,marginBottom:20}}>🎉</div>
        <h2 style={{fontFamily:"serif",fontSize:36,color:C.ink,marginBottom:12}}>Welcome to ZuZan!</h2>
        <p style={{color:C.inkMid,fontSize:15,lineHeight:1.7}}>Your account is ready. Setting up your dashboard...</p>
      </div>
    </div>
  );

  return (
    <div style={{minHeight:"100vh",background:C.bg}}>
      <div style={{background:C.surface,borderBottom:`1px solid ${C.border}`,padding:"16px 32px",display:"flex",alignItems:"center",justifyContent:"space-between"}}>
        <div style={{fontFamily:"serif",fontSize:24,fontWeight:800,color:C.ink}}><span style={{color:C.accent}}>Zu</span>Zan</div>
        <div style={{display:"flex",gap:8}}>
          {["Plan","Account","Payment","Confirm"].map((s,i) => (
            <div key={i} style={{display:"flex",alignItems:"center",gap:6}}>
              <div style={{width:26,height:26,borderRadius:"50%",background:step>i+1?C.green:step===i+1?C.accent:C.border,display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,fontWeight:700,color:step>=i+1?"#fff":C.inkMid}}>{step>i+1?"v":i+1}</div>
              <span style={{fontSize:12,color:step===i+1?C.ink:C.inkDim,fontWeight:step===i+1?600:400}}>{s}</span>
              {i<3 && <div style={{width:24,height:1,background:C.border,marginLeft:2}}/>}
            </div>
          ))}
        </div>
        <div style={{fontSize:12,color:C.inkMid}}>Already have an account? <span style={{color:C.accent,cursor:"pointer",fontWeight:600}} onClick={() => onLogin && onLogin()}>Sign in</span></div>
      </div>
      <div style={{maxWidth:860,margin:"0 auto",padding:"48px 24px"}}>
        {step === 1 && (
          <div>
            <h1 style={{fontFamily:"serif",fontSize:34,color:C.ink,marginBottom:6}}>Choose your plan</h1>
            <p style={{color:C.inkMid,fontSize:15,marginBottom:28}}>14-day free trial on all plans. No credit card charged until trial ends.</p>
            <div style={{display:"inline-flex",background:C.border,borderRadius:10,padding:3,marginBottom:28}}>
              {["monthly","annual"].map(b => <button key={b} onClick={() => setBilling(b)} style={{padding:"8px 20px",borderRadius:8,border:"none",cursor:"pointer",fontSize:13,fontWeight:600,fontFamily:"inherit",background:billing===b?C.surface:"transparent",color:billing===b?C.ink:C.inkMid}}>{b==="monthly"?"Monthly":"Annual (Save 17%)"}</button>)}
            </div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:16,marginBottom:28}}>
              {PLANS.map(plan => {
                const price = billing === "monthly" ? plan.monthly : Math.round(plan.annual / 12);
                const sel = selectedPlan && selectedPlan.id === plan.id;
                return (
                  <div key={plan.id} onClick={() => setPlan(plan)} style={{background:C.surface,border:`2px solid ${sel?plan.color:C.border}`,borderRadius:18,padding:24,cursor:"pointer",position:"relative",transform:sel?"translateY(-3px)":"none",boxShadow:sel?`0 8px 32px ${plan.color}20`:"none"}}>
                    {plan.popular && <div style={{position:"absolute",top:-11,left:"50%",transform:"translateX(-50%)",background:C.accent,color:"#fff",fontSize:9,fontWeight:700,letterSpacing:1,padding:"3px 14px",borderRadius:20,textTransform:"uppercase"}}>Most Popular</div>}
                    <div style={{fontSize:28,marginBottom:10}}>{plan.icon}</div>
                    <div style={{fontSize:11,fontWeight:700,color:C.inkMid,letterSpacing:1.5,textTransform:"uppercase",marginBottom:6}}>{plan.name}</div>
                    <div style={{fontFamily:"serif",fontSize:36,fontWeight:800,color:C.ink,letterSpacing:-1,marginBottom:2}}>R{price.toLocaleString()}</div>
                    <div style={{fontSize:11,color:C.inkDim,marginBottom:14}}>{plan.users} users - {plan.invoices} invoices{plan.invoices!=="Unlimited"?"/mo":""}</div>
                    <div style={{borderTop:`1px solid ${C.border}`,paddingTop:12}}>
                      {plan.features.slice(0,5).map((f,i) => <div key={i} style={{display:"flex",gap:8,fontSize:12,color:C.inkMid,marginBottom:6}}><span style={{color:C.green}}>ok</span>{f}</div>)}
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{background:C.surface,border:`2px solid ${payrollEnabled?C.accent:C.border}`,borderRadius:18,padding:24,marginBottom:28}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:payrollEnabled?20:0}}>
                <div style={{display:"flex",gap:14,alignItems:"flex-start"}}>
                  <span style={{fontSize:32}}>👥</span>
                  <div>
                    <div style={{fontSize:15,fontWeight:700,color:C.ink,marginBottom:4}}>Payroll Module</div>
                    <div style={{fontSize:13,color:C.inkMid}}>SARS-compliant PAYE, UIF, SDL - EMP201 and IRP5 - <strong style={{color:C.accent}}>R17.50/employee/month</strong> (min R99/month)</div>
                  </div>
                </div>
                <button onClick={() => setPayroll(!payrollEnabled)} style={{padding:"8px 18px",borderRadius:8,border:`1.5px solid ${payrollEnabled?C.accent:C.border}`,background:payrollEnabled?C.accentLt:"transparent",color:payrollEnabled?C.accent:C.inkMid,fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>{payrollEnabled?"Added":"Add Payroll"}</button>
              </div>
              {payrollEnabled && (
                <div style={{display:"flex",alignItems:"center",gap:16,padding:"16px 0 0",borderTop:`1px solid ${C.border}`}}>
                  <span style={{fontSize:13,color:C.inkMid}}>Number of employees:</span>
                  <div style={{display:"flex",alignItems:"center",gap:10}}>
                    <button onClick={() => setEmpCount(Math.max(1,empCount-1))} style={{width:32,height:32,borderRadius:"50%",border:`1px solid ${C.border}`,background:C.bg,cursor:"pointer",fontSize:16,fontFamily:"inherit"}}>-</button>
                    <span style={{fontSize:20,fontWeight:700,color:C.ink,minWidth:30,textAlign:"center"}}>{empCount}</span>
                    <button onClick={() => setEmpCount(empCount+1)} style={{width:32,height:32,borderRadius:"50%",border:`1px solid ${C.border}`,background:C.bg,cursor:"pointer",fontSize:16,fontFamily:"inherit"}}>+</button>
                  </div>
                  <span style={{fontSize:13,color:C.accent,fontWeight:700}}>= {fmt(Math.max(99,empCount*17.50))}/month</span>
                </div>
              )}
            </div>
            {selectedPlan && (
              <div style={{background:C.ink,borderRadius:16,padding:"20px 24px",display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                <div>
                  <div style={{fontSize:11,color:"rgba(255,255,255,0.5)",marginBottom:4}}>MONTHLY TOTAL</div>
                  <div style={{fontFamily:"serif",fontSize:32,color:"#fff",fontWeight:800}}>{fmt(totalMonthly)}</div>
                  <div style={{fontSize:11,color:"rgba(255,255,255,0.4)"}}>{selectedPlan.name}{payrollEnabled?` + Payroll (${empCount} employees)`:""}</div>
                </div>
                <button onClick={() => setStep(2)} style={{background:C.accent,color:"#fff",border:"none",borderRadius:12,padding:"14px 32px",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Continue</button>
              </div>
            )}
          </div>
        )}
        {step === 2 && (
          <div style={{maxWidth:560,margin:"0 auto"}}>
            <h1 style={{fontFamily:"serif",fontSize:34,color:C.ink,marginBottom:24}}>Create your account</h1>
            <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:18,padding:28,marginBottom:20}}>
              <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Business Details</div>
              {[{l:"Company Name",k:"companyName",p:"Acme Pty Ltd"},{l:"Registration Number",k:"regNumber",p:"2020/123456/07"}].map(f => (
                <div key={f.k} style={{marginBottom:14}}>
                  <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                  <input placeholder={f.p} value={form[f.k]} onChange={e => setForm({...form,[f.k]:e.target.value})} style={{width:"100%",padding:"11px 14px",border:`1.5px solid ${C.border}`,borderRadius:10,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
                </div>
              ))}
            </div>
            <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:18,padding:28,marginBottom:20}}>
              <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Your Details</div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
                {[{l:"First Name",k:"firstName",p:"John"},{l:"Last Name",k:"lastName",p:"Smith"}].map(f => (
                  <div key={f.k}>
                    <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                    <input placeholder={f.p} value={form[f.k]} onChange={e => setForm({...form,[f.k]:e.target.value})} style={{width:"100%",padding:"11px 14px",border:`1.5px solid ${C.border}`,borderRadius:10,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
                  </div>
                ))}
              </div>
              {[{l:"Email Address",k:"email",t:"email",p:"john@acme.co.za"},{l:"Password",k:"password",t:"password",p:"Min 8 characters"},{l:"Confirm Password",k:"confirm",t:"password",p:"Repeat password"}].map(f => (
                <div key={f.k} style={{marginBottom:14}}>
                  <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                  <input type={f.t} placeholder={f.p} value={form[f.k]} onChange={e => setForm({...form,[f.k]:e.target.value})} style={{width:"100%",padding:"11px 14px",border:`1.5px solid ${C.border}`,borderRadius:10,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
                </div>
              ))}
            </div>
            <div style={{display:"flex",gap:12}}>
              <button onClick={() => setStep(1)} style={{flex:1,padding:"13px",border:`1.5px solid ${C.border}`,borderRadius:10,background:"transparent",color:C.inkMid,fontSize:14,cursor:"pointer",fontFamily:"inherit"}}>Back</button>
              <button onClick={() => setStep(3)} style={{flex:2,padding:"13px",border:"none",borderRadius:10,background:C.accent,color:"#fff",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Continue</button>
            </div>
          </div>
        )}
        {step === 3 && (
          <div style={{maxWidth:560,margin:"0 auto"}}>
            <h1 style={{fontFamily:"serif",fontSize:34,color:C.ink,marginBottom:6}}>Payment details</h1>
            <p style={{color:C.inkMid,fontSize:15,marginBottom:24}}>14-day free trial. No charge until trial ends.</p>
            <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:18,padding:24,marginBottom:20}}>
              <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Order Summary</div>
              <div style={{display:"flex",justifyContent:"space-between",marginBottom:10,fontSize:14}}><span style={{color:C.inkMid}}>{selectedPlan ? selectedPlan.name : ""} Plan ({billing})</span><span style={{fontWeight:600}}>{fmt(planPrice)}/mo</span></div>
              {payrollEnabled && <div style={{display:"flex",justifyContent:"space-between",marginBottom:10,fontSize:14}}><span style={{color:C.inkMid}}>Payroll ({empCount} employees x R17.50)</span><span style={{fontWeight:600}}>{fmt(payrollCost)}/mo</span></div>}
              <div style={{borderTop:`1px solid ${C.border}`,marginTop:12,paddingTop:12,display:"flex",justifyContent:"space-between",fontSize:16,fontWeight:800}}><span>Total (after trial)</span><span style={{color:C.accent}}>{fmt(totalMonthly)}/mo</span></div>
            </div>
            <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:18,padding:28,marginBottom:20}}>
              <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Card Details</div>
              {[{l:"Name on Card",k:"cardName",p:"John Smith"},{l:"Card Number",k:"cardNumber",p:"4242 4242 4242 4242"},{l:"Expiry Date",k:"expiry",p:"MM/YY"},{l:"CVV",k:"cvv",p:"123"}].map(f => (
                <div key={f.k} style={{marginBottom:14}}>
                  <label style={{display:"block",fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                  <input placeholder={f.p} value={payment[f.k]} onChange={e => setPayment({...payment,[f.k]:e.target.value})} style={{width:"100%",padding:"11px 14px",border:`1.5px solid ${C.border}`,borderRadius:10,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
                </div>
              ))}
              <div style={{display:"flex",alignItems:"center",gap:8,padding:"12px 14px",background:C.greenLt,borderRadius:8}}>
                <span style={{fontSize:14}}>🔒</span>
                <span style={{fontSize:11,color:C.green}}>256-bit SSL encryption - PCI DSS compliant - Powered by PayFast</span>
              </div>
            </div>
            <div style={{display:"flex",gap:12}}>
              <button onClick={() => setStep(2)} style={{flex:1,padding:"13px",border:`1.5px solid ${C.border}`,borderRadius:10,background:"transparent",color:C.inkMid,fontSize:14,cursor:"pointer",fontFamily:"inherit"}}>Back</button>
              <button onClick={() => setStep(4)} style={{flex:2,padding:"13px",border:"none",borderRadius:10,background:C.accent,color:"#fff",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Review Order</button>
            </div>
          </div>
        )}
        {step === 4 && (
          <div style={{maxWidth:560,margin:"0 auto"}}>
            <h1 style={{fontFamily:"serif",fontSize:34,color:C.ink,marginBottom:24}}>Confirm and Start Trial</h1>
            <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:18,padding:28,marginBottom:20}}>
              {[
                {label:"Company",value:form.companyName || "Your Company"},
                {label:"Plan",value:`${selectedPlan ? selectedPlan.name : ""} (${billing})`},
                {label:"Users",value:`Up to ${selectedPlan ? selectedPlan.users : ""}`},
                {label:"Invoices",value:selectedPlan ? `${selectedPlan.invoices}${selectedPlan.invoices !== "Unlimited" ? " per month" : ""}` : ""},
                {label:"Payroll",value:payrollEnabled ? `${empCount} employees x R17.50 = ${fmt(payrollCost)}/mo` : "Not included"},
                {label:"Trial Period",value:"14 days FREE"},
                {label:"First Charge",value:`${fmt(totalMonthly)}/month after trial`},
              ].map((r,i) => (
                <div key={i} style={{display:"flex",justifyContent:"space-between",padding:"11px 0",borderBottom:i<6?`1px solid ${C.border}30`:"none",fontSize:13}}>
                  <span style={{color:C.inkMid}}>{r.label}</span>
                  <span style={{fontWeight:600,color:C.ink}}>{r.value}</span>
                </div>
              ))}
            </div>
            <div style={{fontSize:11,color:C.inkDim,marginBottom:20,lineHeight:1.7}}>By starting your trial you agree to ZuZan's Terms of Service and Privacy Policy. Cancel anytime before trial ends.</div>
            <div style={{display:"flex",gap:12}}>
              <button onClick={() => setStep(3)} style={{flex:1,padding:"13px",border:`1.5px solid ${C.border}`,borderRadius:10,background:"transparent",color:C.inkMid,fontSize:14,cursor:"pointer",fontFamily:"inherit"}}>Back</button>
              <button onClick={handlePayment} disabled={processing} style={{flex:2,padding:"15px",border:"none",borderRadius:10,background:processing?C.inkDim:C.accent,color:"#fff",fontSize:15,fontWeight:700,cursor:processing?"wait":"pointer",fontFamily:"inherit"}}>{processing ? "Processing..." : "Start Free Trial"}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── CURRENCY HELPERS ─────────────────────────────────────────────────────────
const CURRENCIES = {
  ZAR:{symbol:"R",  code:"ZAR"},
  USD:{symbol:"$",  code:"USD"},
  EUR:{symbol:"€",  code:"EUR"},
  GBP:{symbol:"£",  code:"GBP"},
  BWP:{symbol:"P",  code:"BWP"},
  ZMW:{symbol:"K",  code:"ZMW"},
  MZN:{symbol:"MT", code:"MZN"},
  NAD:{symbol:"N$", code:"NAD"},
  KES:{symbol:"KSh",code:"KES"},
  CNY:{symbol:"¥",  code:"CNY"},
};
function fmtCurrency(amount, currency="ZAR") {
  const c = CURRENCIES[currency] || CURRENCIES.ZAR;
  return `${c.symbol}${Number(amount).toLocaleString("en-ZA",{minimumFractionDigits:2})}`;
}

// ── QUOTES / ESTIMATES ────────────────────────────────────────────────────────
const QUOTE_STATUSES = {draft:["Draft",C.inkMid,"#E8E0D5"],sent:["Sent",C.blue,C.blueLt],accepted:["Accepted",C.green,C.greenLt],declined:["Declined",C.red,C.redLt]};
function Quotes({live={},user={},onNavigate,docTemplate}) {
  const [quotes,    setQuotes]    = useState([]);
  const [showNew,   setShowNew]   = useState(false);
  const [preview,   setPreview]   = useState(null);
  const [editQuote, setEditQuote] = useState(null);
  const [saving,    setSaving]    = useState(false);
  const emptyForm = {client:"",amount:"",desc:"",validUntil:"",currency:"ZAR",rate:"18.5",notes:"",vatApplicable:true,vatAmount:"0"};
  const [form, setForm] = useState(emptyForm);
  const [customers, setCustomers] = useState([]);

  useEffect(()=>{
    api("/customers/").then(setCustomers).catch(()=>{});
    api("/quotes/").then(data=>setQuotes(data.map(q=>({
      id: q.quote_number, _id: q.id,
      client: q.client_name, desc: q.description,
      amount: q.amount, totalAmount: q.total_amount,
      vatApplicable: q.vat_applicable, vatAmount: q.vat_amount,
      date: q.created_at?.slice(0,10),
      validUntil: q.valid_until, status: q.status,
      currency: q.currency, rate: q.exchange_rate,
      notes: q.notes,
    })))).catch(()=>{});
  },[]);

  const [filterStatus, setFilterStatus] = useState(null); // null | "accepted" | "sent" | "draft" | "declined"
  const toZar = q => (q.totalAmount||q.amount||0) * (q.currency&&q.currency!=="ZAR" ? (q.rate||1) : 1);
  const totalAccepted = quotes.filter(q=>q.status==="accepted").reduce((s,q)=>s+toZar(q),0);
  const totalPending  = quotes.filter(q=>q.status==="sent").reduce((s,q)=>s+toZar(q),0);
  const displayedQuotes = filterStatus ? quotes.filter(q=>q.status===filterStatus) : quotes;
  const toggleFilter = (status) => setFilterStatus(prev => prev === status ? null : status);

  const handleCreate = async (status="draft") => {
    if(!form.client||!form.amount||!form.desc){alert("Client, description and amount are required.");return;}
    setSaving(true);
    try {
      const qBody = {
        client_name: form.client, description: form.desc,
        amount: +form.amount, vat_applicable: form.vatApplicable,
        currency: form.currency, exchange_rate: +form.rate,
        valid_until: form.validUntil||null, notes: form.notes||null,
        status,
      };
      if (form.currency !== "ZAR") qBody.vat_amount_override = +form.vatAmount || 0;
      const res = await api("/quotes/",{method:"POST",body:JSON.stringify(qBody)});
      setQuotes(prev=>[{id:res.quote_number,_id:res.id,client:res.client_name,desc:res.description,amount:res.amount,totalAmount:res.total_amount,vatApplicable:res.vat_applicable,vatAmount:res.vat_amount,date:res.created_at?.slice(0,10),validUntil:res.valid_until,status:res.status,currency:res.currency,rate:res.exchange_rate,notes:res.notes},...prev]);
      setShowNew(false); setForm(emptyForm);
    } catch(e){alert("Failed to create quote: "+(e.message||"Unknown error"));}
    finally{setSaving(false);}
  };

  const updateStatus = async (_id, status) => {
    try {
      await api(`/quotes/${_id}`,{method:"PUT",body:JSON.stringify({status})});
      setQuotes(prev=>prev.map(q=>q._id===_id?{...q,status}:q));
      if(preview&&preview._id===_id) setPreview(p=>({...p,status}));
    } catch(e){alert("Failed to update status.");}
  };

  const deleteQuote = async (_id) => {
    if(!window.confirm("Delete this quote?")) return;
    try {
      await api(`/quotes/${_id}`,{method:"DELETE"});
      setQuotes(prev=>prev.filter(q=>q._id!==_id));
      setPreview(null);
    } catch(e){alert("Failed to delete quote.");}
  };

  const handleAmend = async () => {
    if(!editQuote.client||!editQuote.amount||!editQuote.desc){alert("Client, description and amount are required.");return;}
    setSaving(true);
    try {
      const body = {
        client_name: editQuote.client, description: editQuote.desc,
        amount: +editQuote.amount, currency: editQuote.currency,
        exchange_rate: +editQuote.rate||1,
        valid_until: editQuote.validUntil||null, notes: editQuote.notes||null,
        vat_applicable: editQuote.vatApplicable,
      };
      if (editQuote.currency !== "ZAR") body.vat_amount_override = +editQuote.vatAmount||0;
      const res = await api(`/quotes/${editQuote._id}`,{method:"PUT",body:JSON.stringify(body)});
      setQuotes(prev=>prev.map(q=>q._id===editQuote._id ? {
        ...q, client:res.client_name, desc:res.description,
        amount:res.amount, totalAmount:res.total_amount,
        vatApplicable:res.vat_applicable, vatAmount:res.vat_amount,
        validUntil:res.valid_until, currency:res.currency,
        rate:res.exchange_rate, notes:res.notes,
      } : q));
      setEditQuote(null);
    } catch(e){alert("Failed to amend quote: "+(e.message||"Unknown error"));}
    finally{setSaving(false);}
  };

  const convertToInvoice = async (q) => {
    setSaving(true);
    try {
      const ciBody = {
        client_name:   q.client,
        description:   q.desc || "Converted from quote",
        amount:        q.amount,
        vat_applicable: q.vatApplicable,
        due_date:      q.validUntil || null,
        notes:         q.notes || `Converted from ${q.id}`,
        currency:      q.currency || "ZAR",
        exchange_rate: q.rate ? +q.rate : 1.0,
      };
      if (q.currency && q.currency !== "ZAR") ciBody.vat_amount_override = q.vatAmount || 0;
      await api("/invoices/",{method:"POST",body:JSON.stringify(ciBody)});
      await updateStatus(q._id, "accepted");
      setPreview(null);
      if(live && live.reload) await live.reload();
      if(onNavigate) onNavigate("invoicing");
    } catch(e){alert("Failed to convert quote: "+(e.message||"Unknown error"));}
    finally{setSaving(false);}
  };

  const inputStyle = {width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"};
  const isMobile = typeof window !== "undefined" && window.innerWidth <= 768;
  const printQuote = () => { const w=window.open("","_blank");if(!w)return;w.document.write(`<html><head><title>Quote ${(preview||{}).id||""}</title><style>body{font-family:${(docTemplate||DEFAULT_DOC_TEMPLATE).fontFamily};padding:40px;}</style></head><body>${(document.getElementById("quote-print-content")||{}).innerHTML||""}</body></html>`);w.document.close();w.onload=()=>{w.focus();w.print();w.close();}; };

  return (
    <div>
      <SectionHeader title="Quotes & Estimates" sub="Send quotes and convert to invoices" action="+ New Quote" onAction={()=>setShowNew(true)}/>
      <div style={{display:"flex",gap:12,marginBottom:filterStatus?8:24}}>
        <KPI label="Accepted" value={fmtCurrency(totalAccepted)} color={C.green} icon="✅" sub={`${quotes.filter(q=>q.status==="accepted").length} quotes`} onClick={()=>toggleFilter("accepted")} active={filterStatus==="accepted"}/>
        <KPI label="Pending" value={fmtCurrency(totalPending)} color={C.gold} icon="⏳" sub={`${quotes.filter(q=>q.status==="sent").length} sent`} onClick={()=>toggleFilter("sent")} active={filterStatus==="sent"}/>
        <KPI label="Total Quotes" value={quotes.length} color={C.blue} icon="📝" onClick={()=>setFilterStatus(null)} active={filterStatus===null}/>
      </div>
      {filterStatus && (
        <div style={{background:filterStatus==="accepted"?C.greenLt:C.goldLt,border:`1px solid ${filterStatus==="accepted"?C.green:C.gold}30`,borderRadius:10,padding:"10px 16px",marginBottom:16,display:"flex",alignItems:"center",justifyContent:"space-between",fontSize:13}}>
          <span style={{color:C.ink,fontWeight:500}}>Showing: <strong style={{textTransform:"capitalize"}}>{filterStatus==="sent"?"pending":filterStatus}</strong> ({displayedQuotes.length} quotes)</span>
          <button onClick={()=>setFilterStatus(null)} style={{background:"transparent",border:`1px solid ${C.border}`,borderRadius:6,padding:"3px 10px",fontSize:12,cursor:"pointer",color:C.inkMid,fontFamily:"inherit"}}>✕ Show All</button>
        </div>
      )}

      {showNew && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:24,marginBottom:20}}>
          <h3 style={{fontFamily:"serif",margin:"0 0 16px",color:C.ink}}>New Quote</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Client</label>
              {customers.length>0 && (
                <select value={form.client} onChange={e=>setForm(f=>({...f,client:e.target.value}))} style={{...inputStyle,marginBottom:6}}>
                  <option value="">— Select from customers —</option>
                  {customers.map(c=><option key={c.id} value={c.name}>{c.name}</option>)}
                </select>
              )}
              <input placeholder="Or type new client name" value={form.client} onChange={e=>setForm(f=>({...f,client:e.target.value}))} style={{...inputStyle,marginTop:customers.length>0?4:0}}/>
            </div>
            <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Amount</label><input type="number" placeholder="50000" value={form.amount} onChange={e=>setForm(f=>({...f,amount:e.target.value}))} style={inputStyle}/></div>
            <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Description</label><input placeholder="Services rendered" value={form.desc} onChange={e=>setForm(f=>({...f,desc:e.target.value}))} style={inputStyle}/></div>
            <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Valid Until</label><input type="date" value={form.validUntil} onChange={e=>setForm(f=>({...f,validUntil:e.target.value}))} style={inputStyle}/></div>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Currency</label>
              <select value={form.currency} onChange={e=>setForm(f=>({...f,currency:e.target.value}))} style={inputStyle}>
                <option value="ZAR">ZAR — South African Rand</option>
                <option value="USD">USD — US Dollar</option>
                <option value="EUR">EUR — Euro</option>
                <option value="GBP">GBP — British Pound</option>
                <option value="BWP">BWP — Botswana Pula</option>
                <option value="ZMW">ZMW — Zambian Kwacha</option>
                <option value="MZN">MZN — Mozambican Metical</option>
                <option value="NAD">NAD — Namibian Dollar</option>
                <option value="KES">KES — Kenyan Shilling</option>
                <option value="CNY">CNY — Chinese Yuan</option>
              </select>
            </div>
            {form.currency!=="ZAR" && <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Exchange Rate (1 {form.currency} = R...)</label><input type="number" value={form.rate} onChange={e=>setForm(f=>({...f,rate:e.target.value}))} style={inputStyle}/></div>}
            {form.currency!=="ZAR" && <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>VAT Amount ({form.currency}) — 0 if not applicable</label><input type="number" min="0" placeholder="0" value={form.vatAmount} onChange={e=>setForm(f=>({...f,vatAmount:e.target.value}))} style={inputStyle}/></div>}
            <div style={{gridColumn:"1/-1"}}><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Notes (optional)</label><input placeholder="Payment terms, delivery details..." value={form.notes} onChange={e=>setForm(f=>({...f,notes:e.target.value}))} style={inputStyle}/></div>
          </div>
          {form.amount && form.currency!=="ZAR" && (
            <div style={{background:C.blueLt,borderRadius:8,padding:"10px 14px",marginBottom:12,fontSize:12,color:C.blue}}>
              {form.currency} {fmtCurrency(form.amount,form.currency)}
              {+form.vatAmount > 0 && <> + VAT {fmtCurrency(form.vatAmount,form.currency)} = {fmtCurrency(+form.amount + +form.vatAmount, form.currency)}</>}
              {" "}≈ {fmt((+form.amount + (+form.vatAmount||0)) * +form.rate)} ZAR at R{form.rate}/{form.currency}
            </div>
          )}
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            <button onClick={()=>handleCreate("draft")} disabled={saving} style={{background:C.surface,color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>{saving?"Saving...":"Save as Draft"}</button>
            <button onClick={()=>handleCreate("sent")} disabled={saving} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>{saving?"Saving...":"Send Quote"}</button>
            <button onClick={()=>setShowNew(false)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
          </div>
        </div>
      )}

      {/* Amend Quote Modal */}
      {editQuote && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center",padding:20}} onClick={()=>setEditQuote(null)}>
          <div style={{background:C.surface,borderRadius:20,padding:32,width:580,maxHeight:"90vh",overflow:"auto"}} onClick={e=>e.stopPropagation()}>
            <h3 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:"0 0 20px"}}>Amend Quote — {editQuote.id}</h3>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
              <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Client Name</label><input value={editQuote.client||""} onChange={e=>setEditQuote(q=>({...q,client:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/></div>
              <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Amount (excl. VAT)</label><input type="number" value={editQuote.amount||""} onChange={e=>setEditQuote(q=>({...q,amount:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/></div>
              <div style={{gridColumn:"1/-1"}}><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Description</label><input value={editQuote.desc||""} onChange={e=>setEditQuote(q=>({...q,desc:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/></div>
              <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Valid Until</label><input type="date" value={editQuote.validUntil||""} onChange={e=>setEditQuote(q=>({...q,validUntil:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/></div>
              <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Currency</label>
                <select value={editQuote.currency||"ZAR"} onChange={e=>setEditQuote(q=>({...q,currency:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}>
                  <option value="ZAR">ZAR — South African Rand</option>
                  <option value="USD">USD — US Dollar</option>
                  <option value="EUR">EUR — Euro</option>
                  <option value="GBP">GBP — British Pound</option>
                  <option value="BWP">BWP — Botswana Pula</option>
                  <option value="ZMW">ZMW — Zambian Kwacha</option>
                  <option value="MZN">MZN — Mozambican Metical</option>
                  <option value="NAD">NAD — Namibian Dollar</option>
                  <option value="KES">KES — Kenyan Shilling</option>
                  <option value="CNY">CNY — Chinese Yuan</option>
                </select>
              </div>
              {editQuote.currency!=="ZAR" && <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Exchange Rate (1 {editQuote.currency} = R...)</label><input type="number" value={editQuote.rate||"18.5"} onChange={e=>setEditQuote(q=>({...q,rate:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/></div>}
              {editQuote.currency!=="ZAR" && <div><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>VAT Amount ({editQuote.currency}) — 0 if not applicable</label><input type="number" min="0" value={editQuote.vatAmount||"0"} onChange={e=>setEditQuote(q=>({...q,vatAmount:e.target.value}))} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/></div>}
              {(!editQuote.currency||editQuote.currency==="ZAR") && (
                <div style={{gridColumn:"1/-1",display:"flex",alignItems:"center",gap:10}}>
                  <label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer",fontSize:13,color:C.ink}}>
                    <input type="checkbox" checked={editQuote.vatApplicable!==false} onChange={e=>setEditQuote(q=>({...q,vatApplicable:e.target.checked}))} style={{width:16,height:16,cursor:"pointer"}}/>
                    Apply VAT @ 15%
                  </label>
                </div>
              )}
              <div style={{gridColumn:"1/-1"}}><label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Notes (optional)</label><input value={editQuote.notes||""} onChange={e=>setEditQuote(q=>({...q,notes:e.target.value}))} placeholder="Payment terms, delivery details..." style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/></div>
            </div>
            <div style={{display:"flex",gap:8,marginTop:8}}>
              <button onClick={handleAmend} disabled={saving} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"11px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>{saving?"Saving...":"Save Changes"}</button>
              <button onClick={()=>setEditQuote(null)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"11px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* ── MOBILE: Full-screen quote detail ── */}
      {preview && isMobile && (
        <div style={{position:"fixed",inset:0,background:C.bg,zIndex:200,display:"flex",flexDirection:"column"}}>
          {/* Sticky header */}
          <div style={{display:"flex",alignItems:"center",gap:12,padding:"14px 16px",background:C.surface,borderBottom:`1px solid ${C.border}`,flexShrink:0}}>
            <button onClick={()=>setPreview(null)} style={{background:"none",border:"none",fontSize:22,cursor:"pointer",color:C.ink,lineHeight:1,padding:"0 4px"}}>←</button>
            <div style={{flex:1}}>
              <div style={{fontWeight:800,fontSize:16,color:C.accent}}>{preview.id}</div>
              <div style={{fontSize:12,color:C.inkMid}}>{preview.client}</div>
            </div>
            {(() => { const [label,color,bg]=QUOTE_STATUSES[preview.status]||QUOTE_STATUSES.draft; return <Badge label={label} color={color} bg={bg}/>; })()}
          </div>
          {/* Scrollable body */}
          <div style={{flex:1,overflowY:"auto",padding:"20px 16px",WebkitOverflowScrolling:"touch"}}>
            <div id="quote-print-content">
              <InvoiceDocument type="quote" doc={preview} user={user} tmpl={docTemplate}/>
              {preview.currency&&preview.currency!=="ZAR" && <div style={{background:C.blueLt,borderRadius:8,padding:"10px 14px",marginTop:12,fontSize:12,color:C.blue}}>≈ {fmt((preview.totalAmount||preview.amount)*(preview.rate||18.5))} ZAR at R{preview.rate||18.5}/{preview.currency}</div>}
              {preview.notes && <div style={{background:C.bg,borderRadius:8,padding:"10px 14px",marginTop:10,fontSize:12,color:C.inkMid}}><strong>Notes:</strong> {preview.notes}</div>}
            </div>
          </div>
          {/* Sticky action bar */}
          <div style={{flexShrink:0,background:C.surface,borderTop:`1px solid ${C.border}`,padding:"12px 16px",display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
            {preview.status==="sent" && <button onClick={()=>{setPreview(null);convertToInvoice(preview);}} disabled={saving} style={{gridColumn:"1/-1",background:C.green,color:"#fff",border:"none",borderRadius:12,padding:"14px",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>{saving?"Converting...":"✓ Convert to Invoice"}</button>}
            {preview.status==="draft" && <button onClick={()=>updateStatus(preview._id,"sent")} style={{gridColumn:"1/-1",background:C.accent,color:"#fff",border:"none",borderRadius:12,padding:"14px",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Send Quote</button>}
            <button onClick={()=>{setPreview(null);setEditQuote({...preview,rate:preview.rate||"18.5",vatAmount:preview.vatAmount||"0"});}} style={{background:C.goldLt,color:C.gold,border:`1px solid ${C.gold}30`,borderRadius:12,padding:"13px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Amend</button>
            <button onClick={printQuote} style={{background:C.accent,color:"#fff",border:"none",borderRadius:12,padding:"13px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Print / PDF</button>
            {preview.status==="sent" && <button onClick={()=>updateStatus(preview._id,"declined")} style={{background:C.redLt,color:C.red,border:`1px solid ${C.red}30`,borderRadius:12,padding:"13px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Decline</button>}
            <button onClick={()=>{if(!window.confirm(`Delete ${preview.id}?`))return;deleteQuote(preview._id);setPreview(null);}} style={{background:C.redLt,color:C.red,border:`1px solid ${C.red}30`,borderRadius:12,padding:"13px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Delete</button>
          </div>
        </div>
      )}

      {/* ── DESKTOP: floating modal ── */}
      {preview && !isMobile && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center"}} onClick={()=>setPreview(null)}>
          <div style={{background:"#fff",borderRadius:20,padding:40,width:580,maxHeight:"85vh",overflow:"auto"}} onClick={e=>e.stopPropagation()}>
            <div id="quote-print-content">
              <InvoiceDocument type="quote" doc={preview} user={user} tmpl={docTemplate}/>
              {preview.currency&&preview.currency!=="ZAR" && <div style={{background:C.blueLt,borderRadius:8,padding:"10px 14px",marginTop:12,fontSize:12,color:C.blue}}>ZAR equivalent: ≈ {fmt((preview.totalAmount||preview.amount)*(preview.rate||18.5))} at R{preview.rate||18.5}/{preview.currency}</div>}
              {preview.notes && <div style={{background:C.bg,borderRadius:8,padding:"10px 14px",marginTop:10,fontSize:12,color:C.inkMid}}><strong>Notes:</strong> {preview.notes}</div>}
            </div>
            <div style={{display:"flex",gap:8,marginTop:20}}>
              <button onClick={()=>{setPreview(null);setEditQuote({...preview,rate:preview.rate||"18.5",vatAmount:preview.vatAmount||"0"});}} style={{flex:1,background:C.goldLt,color:C.gold,border:`1px solid ${C.gold}30`,borderRadius:10,padding:"11px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Amend</button>
              <button onClick={()=>convertToInvoice(preview)} disabled={saving} style={{flex:1,background:C.greenLt,color:C.green,border:`1px solid ${C.green}30`,borderRadius:10,padding:"11px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>{saving?"Converting...":"Convert to Invoice"}</button>
              <button onClick={printQuote} style={{flex:1,background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"11px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Print / PDF</button>
              <button onClick={()=>setPreview(null)} style={{flex:1,background:"transparent",border:`1px solid ${C.border}`,borderRadius:10,padding:"11px",fontSize:13,cursor:"pointer",fontFamily:"inherit",color:C.inkMid}}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* ── MOBILE: card list ── */}
      {isMobile ? (
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          {quotes.length===0 && <div style={{padding:"32px",textAlign:"center",color:C.inkMid,fontSize:13,background:C.surface,borderRadius:16,border:`1px solid ${C.border}`}}>No quotes yet. Create your first quote above.</div>}
          {displayedQuotes.map(q=>{
            const [label,color,bg]=QUOTE_STATUSES[q.status]||QUOTE_STATUSES.draft;
            return (
              <div key={q.id} onClick={()=>setPreview(q)} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:"16px",cursor:"pointer",WebkitTapHighlightColor:"transparent"}}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:6}}>
                  <div style={{fontWeight:800,fontSize:15,color:C.accent}}>{q.id}</div>
                  <Badge label={label} color={color} bg={bg}/>
                </div>
                <div style={{fontWeight:600,fontSize:14,color:C.ink,marginBottom:2}}>{q.client}</div>
                <div style={{fontSize:12,color:C.inkMid,marginBottom:10,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{q.desc}</div>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
                  <div style={{fontWeight:800,fontSize:16,color:C.ink}}>{fmt(q.totalAmount||q.amount||0)}</div>
                  <div style={{fontSize:11,color:C.inkMid}}>{q.validUntil?`Valid: ${fmtDate(q.validUntil)}`:"—"}</div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* ── DESKTOP: table ── */
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
          {quotes.length===0 ? (
            <div style={{padding:48,textAlign:"center",color:C.inkMid,fontSize:13}}>No quotes yet. Create your first quote above.</div>
          ) : (
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:13,minWidth:700}}>
              <thead><tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>{["Quote #","Client","Description","Amount","Currency","Valid Until","Status","Actions"].map(h=><th key={h} style={{textAlign:"left",padding:"12px 14px",fontSize:10,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>)}</tr></thead>
              <tbody>
                {displayedQuotes.length===0 && <tr><td colSpan={8} style={{padding:"32px",textAlign:"center",color:C.inkMid,fontSize:13}}>No {filterStatus==="sent"?"pending":filterStatus||""} quotes.</td></tr>}
                {displayedQuotes.map(q=>{
                  const [label,color,bg] = QUOTE_STATUSES[q.status]||QUOTE_STATUSES.draft;
                  return (
                    <tr key={q.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                      <td style={{padding:"13px 14px",fontWeight:700,color:C.accent,cursor:"pointer"}} onClick={()=>setPreview(q)}>{q.id}</td>
                      <td style={{padding:"13px 14px",fontWeight:500}}>{q.client}</td>
                      <td style={{padding:"13px 14px",color:C.inkMid,fontSize:12}}>{q.desc}</td>
                      <td style={{padding:"13px 14px",fontWeight:700}}>
                        {q.currency && q.currency!=="ZAR"
                          ? <>{fmt((q.totalAmount||q.amount||0)*(q.rate||1))}<div style={{fontSize:10,color:C.blue,fontWeight:400,marginTop:2}}>{fmtCurrency(q.totalAmount||q.amount,q.currency)}</div></>
                          : fmt(q.totalAmount||q.amount||0)}
                      </td>
                      <td style={{padding:"13px 14px"}}><Badge label={q.currency||"ZAR"} color={C.blue} bg={C.blueLt}/></td>
                      <td style={{padding:"13px 14px",color:C.inkMid}}>{q.validUntil?fmtDate(q.validUntil):"—"}</td>
                      <td style={{padding:"13px 14px"}}><Badge label={label} color={color} bg={bg}/></td>
                      <td style={{padding:"13px 14px"}}>
                        <div style={{display:"flex",gap:5}}>
                          <button onClick={()=>setPreview(q)} style={{background:C.blueLt,color:C.blue,border:"none",borderRadius:6,padding:"4px 8px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>View</button>
                          <button onClick={()=>setEditQuote({...q,rate:q.rate||"18.5",vatAmount:q.vatAmount||"0"})} style={{background:C.goldLt,color:C.gold,border:"none",borderRadius:6,padding:"4px 8px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Amend</button>
                          {q.status==="draft" && <button onClick={()=>updateStatus(q._id,"sent")} style={{background:C.goldLt,color:C.gold,border:"none",borderRadius:6,padding:"4px 8px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Send</button>}
                          {q.status==="sent"  && <button onClick={()=>convertToInvoice(q)} style={{background:C.greenLt,color:C.green,border:"none",borderRadius:6,padding:"4px 8px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Accept</button>}
                          {q.status==="sent"  && <button onClick={()=>updateStatus(q._id,"declined")} style={{background:C.redLt,color:C.red,border:"none",borderRadius:6,padding:"4px 8px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Decline</button>}
                          <button onClick={()=>deleteQuote(q._id)} style={{background:C.redLt,color:C.red,border:"none",borderRadius:6,padding:"4px 8px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

// ── MULTI-CURRENCY: update Invoicing form to support USD ──────────────────────
// (currency selector added inline in Invoicing component below via patch)

// ── CUSTOMERS ─────────────────────────────────────────────────────────────────
function Customers() {
  const [list,    setList]   = useState([]);
  const [showForm,setShowForm]= useState(false);
  const [editing, setEditing] = useState(null);
  const [search,  setSearch] = useState("");
  const empty = {name:"",contact_person:"",email:"",phone:"",address:"",vat_number:"",payment_terms:30,notes:""};
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const f = k => e => setForm(d=>({...d,[k]:e.target.value}));
  const is = {width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontFamily:"inherit",fontSize:13,background:C.bg};
  const lb = t => <div style={{fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:4}}>{t}</div>;

  const load = async () => {
    try { const d = await api("/customers/"); setList(d); } catch(e){}
  };
  useEffect(()=>{load();},[]);

  const save = async () => {
    if(!form.name){alert("Customer name is required.");return;}
    setSaving(true);
    try {
      if (editing) await api(`/customers/${editing.id}`, {method:"PUT",body:JSON.stringify(form)});
      else await api("/customers/", {method:"POST",body:JSON.stringify(form)});
      setShowForm(false); setEditing(null); setForm(empty); load();
    } catch(e){ alert(e.message); }
    finally { setSaving(false); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this customer?")) return;
    try { await api(`/customers/${id}`,{method:"DELETE"}); load(); } catch(e){}
  };

  const edit = (c) => { setEditing(c); setForm({name:c.name,contact_person:c.contact_person||"",email:c.email||"",phone:c.phone||"",address:c.address||"",vat_number:c.vat_number||"",payment_terms:c.payment_terms||30,notes:c.notes||""}); setShowForm(true); };

  const filtered = list.filter(c => c.name.toLowerCase().includes(search.toLowerCase()) || (c.email||"").toLowerCase().includes(search.toLowerCase()));

  return (
    <div>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:24}}>
        <div>
          <h2 style={{fontSize:22,fontWeight:700,color:C.ink}}>Customers</h2>
          <p style={{fontSize:13,color:C.inkMid,marginTop:2}}>{list.length} customer{list.length!==1?"s":""} on record</p>
        </div>
        <button onClick={()=>{setEditing(null);setForm(empty);setShowForm(true);}} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"10px 18px",fontWeight:600,cursor:"pointer",fontSize:13}}>+ Add Customer</button>
      </div>

      <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search customers..." style={{...is,marginBottom:16,maxWidth:320}}/>

      {showForm && (
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:24,marginBottom:24}}>
          <h3 style={{fontWeight:700,marginBottom:16,color:C.ink}}>{editing?"Edit Customer":"New Customer"}</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
            <div>{lb("Company / Customer Name *")}<input value={form.name} onChange={f("name")} style={is}/></div>
            <div>{lb("Contact Person")}<input value={form.contact_person} onChange={f("contact_person")} style={is}/></div>
            <div>{lb("Email")}<input value={form.email} onChange={f("email")} type="email" style={is}/></div>
            <div>{lb("Phone")}<input value={form.phone} onChange={f("phone")} style={is}/></div>
            <div>{lb("VAT Number")}<input value={form.vat_number} onChange={f("vat_number")} style={is}/></div>
            <div>{lb("Payment Terms")}<select value={form.payment_terms} onChange={f("payment_terms")} style={is}><option value={0}>COD (Cash on Delivery)</option><option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option><option value={60}>60 days</option><option value={90}>90 days</option></select></div>
          </div>
          <div style={{marginBottom:12}}>{lb("Address")}<textarea value={form.address} onChange={f("address")} rows={2} style={{...is,resize:"vertical"}}/></div>
          <div style={{marginBottom:16}}>{lb("Notes")}<textarea value={form.notes} onChange={f("notes")} rows={2} style={{...is,resize:"vertical"}}/></div>
          <div style={{display:"flex",gap:10}}>
            <button onClick={save} disabled={saving} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"10px 24px",fontWeight:600,cursor:"pointer",opacity:saving?0.6:1}}>{saving?"Saving...":"Save"}</button>
            <button onClick={()=>{setShowForm(false);setEditing(null);}} style={{background:"transparent",border:`1px solid ${C.border}`,borderRadius:8,padding:"10px 24px",cursor:"pointer",color:C.inkMid}}>Cancel</button>
          </div>
        </div>
      )}

      {filtered.length === 0 ? (
        <div style={{textAlign:"center",padding:"60px 0",color:C.inkDim}}>
          <div style={{fontSize:40,marginBottom:12}}>👥</div>
          <div style={{fontSize:15,fontWeight:600}}>No customers yet</div>
          <div style={{fontSize:13,marginTop:4}}>Add your first customer to get started</div>
        </div>
      ) : (
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(300px,1fr))",gap:12}}>
          {filtered.map(c=>(
            <div key={c.id} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:18}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8}}>
                <div style={{fontWeight:700,fontSize:15,color:C.ink}}>{c.name}</div>
                <div style={{display:"flex",gap:6}}>
                  <button onClick={()=>edit(c)} style={{background:"none",border:`1px solid ${C.border}`,borderRadius:6,padding:"4px 10px",fontSize:12,cursor:"pointer",color:C.inkMid}}>Edit</button>
                  <button onClick={()=>del(c.id)} style={{background:"none",border:`1px solid ${C.red}20`,borderRadius:6,padding:"4px 10px",fontSize:12,cursor:"pointer",color:C.red}}>Delete</button>
                </div>
              </div>
              {c.contact_person && <div style={{fontSize:12,color:C.inkMid,marginBottom:4}}>👤 {c.contact_person}</div>}
              {c.email && <div style={{fontSize:12,color:C.inkMid,marginBottom:4}}>✉ {c.email}</div>}
              {c.phone && <div style={{fontSize:12,color:C.inkMid,marginBottom:4}}>📞 {c.phone}</div>}
              {c.vat_number && <div style={{fontSize:11,color:C.inkDim,marginBottom:4}}>VAT: {c.vat_number}</div>}
              <div style={{fontSize:11,color:C.inkDim,marginTop:4,paddingTop:8,borderTop:`1px solid ${C.border}`}}>Payment terms: {c.payment_terms} days</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── SUPPLIERS ─────────────────────────────────────────────────────────────────
function Suppliers() {
  const [list,    setList]   = useState([]);
  const [showForm,setShowForm]= useState(false);
  const [editing, setEditing] = useState(null);
  const [search,  setSearch] = useState("");
  const empty = {name:"",contact_person:"",email:"",phone:"",address:"",vat_number:"",bank_name:"",account_number:"",branch_code:"",account_type:"Cheque",payment_terms:30,notes:""};
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const f = k => e => setForm(d=>({...d,[k]:e.target.value}));
  const is = {width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontFamily:"inherit",fontSize:13,background:C.bg};
  const lb = t => <div style={{fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:4}}>{t}</div>;

  const load = async () => { try { setList(await api("/suppliers/")); } catch(e){} };
  useEffect(()=>{load();},[]);

  const save = async () => {
    if(!form.name){alert("Supplier name is required.");return;}
    setSaving(true);
    try {
      if (editing) await api(`/suppliers/${editing.id}`,{method:"PUT",body:JSON.stringify(form)});
      else await api("/suppliers/",{method:"POST",body:JSON.stringify(form)});
      setShowForm(false); setEditing(null); setForm(empty); load();
    } catch(e){ alert(e.message); }
    finally { setSaving(false); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this supplier?")) return;
    try { await api(`/suppliers/${id}`,{method:"DELETE"}); load(); } catch(e){}
  };

  const edit = (s) => { setEditing(s); setForm({name:s.name,contact_person:s.contact_person||"",email:s.email||"",phone:s.phone||"",address:s.address||"",vat_number:s.vat_number||"",bank_name:s.bank_name||"",account_number:s.account_number||"",branch_code:s.branch_code||"",account_type:s.account_type||"Cheque",payment_terms:s.payment_terms||30,notes:s.notes||""}); setShowForm(true); };

  const filtered = list.filter(s => s.name.toLowerCase().includes(search.toLowerCase()) || (s.email||"").toLowerCase().includes(search.toLowerCase()));

  return (
    <div>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:24}}>
        <div>
          <h2 style={{fontSize:22,fontWeight:700,color:C.ink}}>Suppliers</h2>
          <p style={{fontSize:13,color:C.inkMid,marginTop:2}}>{list.length} supplier{list.length!==1?"s":""} on record</p>
        </div>
        <button onClick={()=>{setEditing(null);setForm(empty);setShowForm(true);}} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"10px 18px",fontWeight:600,cursor:"pointer",fontSize:13}}>+ Add Supplier</button>
      </div>

      <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search suppliers..." style={{...is,marginBottom:16,maxWidth:320}}/>

      {showForm && (
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:24,marginBottom:24}}>
          <h3 style={{fontWeight:700,marginBottom:16,color:C.ink}}>{editing?"Edit Supplier":"New Supplier"}</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
            <div>{lb("Supplier Name *")}<input value={form.name} onChange={f("name")} style={is}/></div>
            <div>{lb("Contact Person")}<input value={form.contact_person} onChange={f("contact_person")} style={is}/></div>
            <div>{lb("Email")}<input value={form.email} onChange={f("email")} type="email" style={is}/></div>
            <div>{lb("Phone")}<input value={form.phone} onChange={f("phone")} style={is}/></div>
            <div>{lb("VAT Number")}<input value={form.vat_number} onChange={f("vat_number")} style={is}/></div>
            <div>{lb("Payment Terms")}<select value={form.payment_terms} onChange={f("payment_terms")} style={is}><option value={0}>COD (Cash on Delivery)</option><option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option><option value={60}>60 days</option><option value={90}>90 days</option></select></div>
          </div>
          <div style={{marginBottom:12}}>{lb("Address")}<textarea value={form.address} onChange={f("address")} rows={2} style={{...is,resize:"vertical"}}/></div>
          <div style={{fontWeight:600,fontSize:13,color:C.ink,marginBottom:10,paddingTop:8,borderTop:`1px solid ${C.border}`}}>Banking Details</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:16}}>
            <div>{lb("Bank Name")}<select value={form.bank_name} onChange={f("bank_name")} style={is}><option value="">-- Select Bank --</option>{["ABSA","Capitec","Discovery Bank","FNB","Investec","Nedbank","Standard Bank","TymeBank","African Bank","Other"].map(b=><option key={b}>{b}</option>)}</select></div>
            <div>{lb("Account Type")}<select value={form.account_type} onChange={f("account_type")} style={is}><option>Cheque</option><option>Savings</option><option>Transmission</option></select></div>
            <div>{lb("Account Number")}<input value={form.account_number} onChange={f("account_number")} style={is}/></div>
            <div>{lb("Branch Code")}<input value={form.branch_code} onChange={f("branch_code")} style={is}/></div>
          </div>
          <div style={{marginBottom:16}}>{lb("Notes")}<textarea value={form.notes} onChange={f("notes")} rows={2} style={{...is,resize:"vertical"}}/></div>
          <div style={{display:"flex",gap:10}}>
            <button onClick={save} disabled={saving} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"10px 24px",fontWeight:600,cursor:"pointer",opacity:saving?0.6:1}}>{saving?"Saving...":"Save"}</button>
            <button onClick={()=>{setShowForm(false);setEditing(null);}} style={{background:"transparent",border:`1px solid ${C.border}`,borderRadius:8,padding:"10px 24px",cursor:"pointer",color:C.inkMid}}>Cancel</button>
          </div>
        </div>
      )}

      {filtered.length === 0 ? (
        <div style={{textAlign:"center",padding:"60px 0",color:C.inkDim}}>
          <div style={{fontSize:40,marginBottom:12}}>🏭</div>
          <div style={{fontSize:15,fontWeight:600}}>No suppliers yet</div>
          <div style={{fontSize:13,marginTop:4}}>Add your first supplier to get started</div>
        </div>
      ) : (
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(300px,1fr))",gap:12}}>
          {filtered.map(s=>(
            <div key={s.id} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:18}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8}}>
                <div style={{fontWeight:700,fontSize:15,color:C.ink}}>{s.name}</div>
                <div style={{display:"flex",gap:6}}>
                  <button onClick={()=>edit(s)} style={{background:"none",border:`1px solid ${C.border}`,borderRadius:6,padding:"4px 10px",fontSize:12,cursor:"pointer",color:C.inkMid}}>Edit</button>
                  <button onClick={()=>del(s.id)} style={{background:"none",border:`1px solid ${C.red}20`,borderRadius:6,padding:"4px 10px",fontSize:12,cursor:"pointer",color:C.red}}>Delete</button>
                </div>
              </div>
              {s.contact_person && <div style={{fontSize:12,color:C.inkMid,marginBottom:4}}>👤 {s.contact_person}</div>}
              {s.email && <div style={{fontSize:12,color:C.inkMid,marginBottom:4}}>✉ {s.email}</div>}
              {s.phone && <div style={{fontSize:12,color:C.inkMid,marginBottom:4}}>📞 {s.phone}</div>}
              {s.account_number && <div style={{fontSize:11,color:C.inkDim,marginBottom:4}}>🏦 {s.bank_name} — {s.account_number}</div>}
              <div style={{fontSize:11,color:C.inkDim,marginTop:4,paddingTop:8,borderTop:`1px solid ${C.border}`}}>Payment terms: {s.payment_terms} days</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── PURCHASE ORDERS ────────────────────────────────────────────────────────────
const PO_STATUSES = ["draft","sent","received","partial","cancelled"];
const PO_STATUS_COLORS = {draft:C.goldLt,sent:C.blueLt,received:C.greenLt,partial:C.accentLt,cancelled:C.redLt};
const PO_STATUS_TEXT   = {draft:C.gold,sent:C.blue,received:C.green,partial:C.accent,cancelled:C.red};

function PurchaseOrders() {
  const [list,      setList]     = useState([]);
  const [suppliers, setSuppliers]= useState([]);
  const [showForm,  setShowForm] = useState(false);
  const [viewing,   setViewing]  = useState(null);
  const [receiving, setReceiving]= useState(null); // PO being receipted
  const [recvQtys,  setRecvQtys] = useState({});   // {item_id: qty_received}
  const [recvCategory, setRecvCategory] = useState("6000 - Cost of Sales");
  const [recvDone,  setRecvDone] = useState(null);  // result after receiving
  const [statusFilter, setStatusFilter] = useState("all");
  const emptyForm = {supplier_id:"",supplier_name:"",delivery_date:"",vat_applicable:true,notes:"",items:[{description:"",quantity:1,unit_price:0}]};
  const [form, setForm] = useState(emptyForm);
  const is = {width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontFamily:"inherit",fontSize:13,background:C.bg};
  const lb = t => <div style={{fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:4}}>{t}</div>;

  const load = async () => {
    try {
      const [pos, sups] = await Promise.all([api("/purchase-orders/"), api("/suppliers/")]);
      setList(pos); setSuppliers(sups);
    } catch(e){ console.warn("PO load error:", e.message); }
  };
  useEffect(()=>{load();},[]);

  const subtotal = form.items.reduce((s,i)=>s+(parseFloat(i.quantity)||0)*(parseFloat(i.unit_price)||0),0);
  const vat      = form.vat_applicable ? subtotal*0.15 : 0;
  const total    = subtotal + vat;

  const setItem = (idx,key,val) => setForm(d=>({...d,items:d.items.map((it,i)=>i===idx?{...it,[key]:val}:it)}));
  const addItem = () => setForm(d=>({...d,items:[...d.items,{description:"",quantity:1,unit_price:0}]}));
  const removeItem = idx => setForm(d=>({...d,items:d.items.filter((_,i)=>i!==idx)}));

  const [saving,  setSaving]  = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [editingPO, setEditingPO] = useState(null); // PO being amended (null = creating new)

  const pingAndSubmit = async (payload, isEdit) => {
    for (let i = 0; i < 18; i++) {
      try {
        setSaveMsg(i === 0 ? "Connecting…" : `Starting up… (${i * 10}s)`);
        const h = await fetch(`${BASE_URL}/health`);
        if (h.ok) break;
      } catch(e) {
        if (i === 17) { setSaving(false); setSaveMsg(""); alert("Server is not responding. Please try again later."); return; }
        await new Promise(r => setTimeout(r, 10000)); continue;
      }
      break;
    }
    setSaveMsg("Saving…");
    try {
      if (isEdit) {
        await api(`/purchase-orders/${editingPO.id}`, {method:"PUT", body:JSON.stringify(payload)});
      } else {
        await api("/purchase-orders/", {method:"POST", body:JSON.stringify(payload)});
      }
      setSaving(false); setSaveMsg("");
      setShowForm(false); setForm(emptyForm); setEditingPO(null); load();
    } catch(e) { setSaving(false); setSaveMsg(""); alert(e.message); }
  };

  const save = async () => {
    if (!form.supplier_name && !form.supplier_id) { alert("Please select or enter a supplier"); return; }
    setSaving(true);
    const payload = {...form, supplier_id: form.supplier_id ? parseInt(form.supplier_id) : null};
    await pingAndSubmit(payload, !!editingPO);
  };

  const saveDraft = async () => {
    if (!form.supplier_name && !form.supplier_id) { alert("Please enter at least a supplier name to save a draft"); return; }
    setSaving(true);
    const payload = {...form, supplier_id: form.supplier_id ? parseInt(form.supplier_id) : null, status:"draft"};
    await pingAndSubmit(payload, !!editingPO);
  };

  const startEdit = (po) => {
    setForm({
      supplier_id: po.supplier_id || "",
      supplier_name: po.supplier_name || "",
      delivery_date: po.delivery_date || "",
      vat_applicable: po.vat_amount > 0,
      notes: po.notes || "",
      items: po.items.map(i => ({description: i.description, quantity: i.quantity, unit_price: i.unit_price})),
    });
    setEditingPO(po);
    setViewing(null);
    setShowForm(true);
  };

  const updateStatus = async (id, status) => {
    try { await api(`/purchase-orders/${id}`,{method:"PUT",body:JSON.stringify({status})}); load(); } catch(e){}
  };

  const del = async (id) => {
    if (!window.confirm("Delete this purchase order?")) return;
    try { await api(`/purchase-orders/${id}`,{method:"DELETE"}); setViewing(null); load(); } catch(e){}
  };

  const filtered = list.filter(p => statusFilter==="all" || p.status===statusFilter);

  return (
    <div>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:24}}>
        <div>
          <h2 style={{fontSize:22,fontWeight:700,color:C.ink}}>Purchase Orders</h2>
          <p style={{fontSize:13,color:C.inkMid,marginTop:2}}>{list.length} PO{list.length!==1?"s":""} total</p>
        </div>
        <button onClick={async()=>{setShowForm(true);setViewing(null);setEditingPO(null);setForm(emptyForm);try{const sups=await api("/suppliers/");setSuppliers(sups);}catch(e){}}} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"10px 18px",fontWeight:600,cursor:"pointer",fontSize:13}}>+ New PO</button>
      </div>

      {/* Status filter */}
      <div style={{display:"flex",gap:8,marginBottom:16,flexWrap:"wrap"}}>
        {["all",...PO_STATUSES].map(s=>(
          <button key={s} onClick={()=>setStatusFilter(s)} style={{padding:"6px 14px",borderRadius:20,border:`1px solid ${C.border}`,fontSize:12,cursor:"pointer",fontFamily:"inherit",background:statusFilter===s?C.accent:"transparent",color:statusFilter===s?"#fff":C.inkMid,fontWeight:statusFilter===s?600:400,textTransform:"capitalize"}}>{s}</button>
        ))}
      </div>

      {/* New PO Form */}
      {showForm && (
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:24,marginBottom:24}}>
          <h3 style={{fontWeight:700,marginBottom:16,color:C.ink}}>{editingPO ? `Edit ${editingPO.po_number}` : "New Purchase Order"}</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:16}}>
            <div>{lb("Supplier")}
              <select value={form.supplier_id} onChange={e=>{const s=suppliers.find(x=>x.id===parseInt(e.target.value));setForm(d=>({...d,supplier_id:e.target.value,supplier_name:s?s.name:d.supplier_name}));}} style={is}>
                <option value="">— Select supplier —</option>
                {suppliers.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>{lb("Or type supplier name")}<input value={form.supplier_name} onChange={e=>setForm(d=>({...d,supplier_name:e.target.value}))} placeholder="Supplier name" style={is}/></div>
            <div>{lb("Delivery Date")}<input type="date" value={form.delivery_date} onChange={e=>setForm(d=>({...d,delivery_date:e.target.value}))} style={is}/></div>
            <div style={{display:"flex",alignItems:"center",gap:8,paddingTop:20}}>
              <input type="checkbox" checked={form.vat_applicable} onChange={e=>setForm(d=>({...d,vat_applicable:e.target.checked}))} id="po_vat"/>
              <label htmlFor="po_vat" style={{fontSize:13,color:C.inkMid,cursor:"pointer"}}>Apply VAT @ 15%</label>
            </div>
          </div>

          {/* Line items */}
          <div style={{fontWeight:600,fontSize:13,color:C.ink,marginBottom:10}}>Line Items</div>
          <div style={{background:C.bg,borderRadius:8,padding:12,marginBottom:12}}>
            {form.items.map((item,idx)=>(
              <div key={idx} style={{display:"grid",gridTemplateColumns:"1fr 80px 100px 40px",gap:8,marginBottom:8,alignItems:"center"}}>
                <input value={item.description} onChange={e=>setItem(idx,"description",e.target.value)} placeholder="Description" style={is}/>
                <input value={item.quantity} onChange={e=>setItem(idx,"quantity",e.target.value)} type="number" min="0" placeholder="Qty" style={is}/>
                <input value={item.unit_price} onChange={e=>setItem(idx,"unit_price",e.target.value)} type="number" min="0" placeholder="Unit price" style={is}/>
                <button onClick={()=>removeItem(idx)} disabled={form.items.length===1} style={{background:"none",border:"none",cursor:"pointer",fontSize:18,color:C.red,opacity:form.items.length===1?0.3:1}}>×</button>
              </div>
            ))}
            <button onClick={addItem} style={{fontSize:12,color:C.accent,background:"none",border:"none",cursor:"pointer",padding:"4px 0"}}>+ Add line</button>
          </div>

          {/* Totals */}
          <div style={{textAlign:"right",marginBottom:16,fontSize:13,color:C.inkMid}}>
            <div>Subtotal: R{subtotal.toFixed(2)}</div>
            {form.vat_applicable && <div>VAT (15%): R{vat.toFixed(2)}</div>}
            <div style={{fontWeight:700,fontSize:16,color:C.ink,marginTop:4}}>Total: R{total.toFixed(2)}</div>
          </div>

          <div style={{marginBottom:16}}>{lb("Notes")}<textarea value={form.notes} onChange={e=>setForm(d=>({...d,notes:e.target.value}))} rows={2} style={{...is,resize:"vertical"}}/></div>
          <div style={{display:"flex",gap:10}}>
            <button onClick={save} disabled={saving} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"10px 24px",fontWeight:600,cursor:"pointer",opacity:saving?0.7:1}}>{saving?(saveMsg||"Saving…"):editingPO?"Save Changes":"Create PO"}</button>
            <button onClick={saveDraft} disabled={saving} style={{background:"transparent",border:`1px solid ${C.border}`,borderRadius:8,padding:"10px 24px",cursor:"pointer",color:C.inkMid,fontWeight:500}}>{editingPO?"Save as Draft":"Save Draft"}</button>
            <button onClick={()=>{setShowForm(false);setEditingPO(null);setForm(emptyForm);}} style={{background:"transparent",border:"none",borderRadius:8,padding:"10px 24px",cursor:"pointer",color:C.inkDim}}>Cancel</button>
          </div>
        </div>
      )}

      {/* PO View modal */}
      {viewing && !receiving && !recvDone && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:200,display:"flex",alignItems:"center",justifyContent:"center",padding:16}} onClick={()=>setViewing(null)}>
          <div style={{background:C.surface,borderRadius:16,padding:28,maxWidth:560,width:"100%",maxHeight:"80vh",overflowY:"auto"}} onClick={e=>e.stopPropagation()}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
              <div>
                <div style={{fontWeight:700,fontSize:18,color:C.ink}}>{viewing.po_number}</div>
                <div style={{fontSize:12,color:C.inkMid,marginTop:2}}>{viewing.supplier_name}</div>
                {viewing.received_date && <div style={{fontSize:11,color:C.green,marginTop:2}}>✓ Received {viewing.received_date}</div>}
              </div>
              <span style={{padding:"4px 12px",borderRadius:20,fontSize:12,fontWeight:600,background:PO_STATUS_COLORS[viewing.status]||C.goldLt,color:PO_STATUS_TEXT[viewing.status]||C.gold,textTransform:"capitalize"}}>{viewing.status}</span>
            </div>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:13,marginBottom:16}}>
              <thead><tr style={{background:C.bg}}><th style={{textAlign:"left",padding:"8px 10px"}}>Description</th><th style={{textAlign:"right",padding:"8px 10px"}}>Qty</th><th style={{textAlign:"right",padding:"8px 10px"}}>Unit Price</th><th style={{textAlign:"right",padding:"8px 10px"}}>Total</th></tr></thead>
              <tbody>{viewing.items.map((it,i)=><tr key={i}><td style={{padding:"8px 10px"}}>{it.description}</td><td style={{textAlign:"right",padding:"8px 10px"}}>{it.quantity}</td><td style={{textAlign:"right",padding:"8px 10px"}}>R{it.unit_price.toFixed(2)}</td><td style={{textAlign:"right",padding:"8px 10px"}}>R{it.total.toFixed(2)}</td></tr>)}</tbody>
            </table>
            <div style={{textAlign:"right",fontSize:13,color:C.inkMid,marginBottom:16}}>
              <div>Subtotal: R{viewing.subtotal.toFixed(2)}</div>
              {viewing.vat_amount>0 && <div>VAT: R{viewing.vat_amount.toFixed(2)}</div>}
              <div style={{fontWeight:700,fontSize:16,color:C.ink,marginTop:4}}>Total: R{viewing.total_amount.toFixed(2)}</div>
            </div>
            <div style={{display:"flex",gap:8,flexWrap:"wrap",alignItems:"center"}}>
              {!["received","partial","paid","cancelled"].includes(viewing.status) && (
                <button onClick={()=>{
                  const init = {};
                  viewing.items.forEach(it=>{ init[it.id]=it.quantity; });
                  setRecvQtys(init); setReceiving(viewing);
                }} style={{background:C.green,color:"#fff",border:"none",borderRadius:8,padding:"8px 18px",fontSize:13,fontWeight:600,cursor:"pointer"}}>
                  📦 Receive Goods
                </button>
              )}
              {["received","partial"].includes(viewing.status) && (
                <button onClick={async()=>{
                  try {
                    const res = await api(`/purchase-orders/${viewing.id}/pay`,{method:"POST"});
                    setViewing(res); load();
                  } catch(e){ alert(e.message); }
                }} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"8px 18px",fontSize:13,fontWeight:600,cursor:"pointer"}}>
                  💳 Mark as Paid
                </button>
              )}
              {["draft","sent"].includes(viewing.status) && (
                <button onClick={()=>startEdit(viewing)} style={{background:C.goldLt,color:C.gold,border:`1px solid ${C.gold}40`,borderRadius:6,padding:"6px 14px",fontSize:12,cursor:"pointer",fontWeight:600}}>✏️ Edit PO</button>
              )}
              {["draft","sent"].includes(viewing.status) && (
                <button onClick={async()=>{
                  if(!window.confirm(`Mark ${viewing.po_number} as sent and email ${viewing.supplier_name}?`)) return;
                  try {
                    const res = await api(`/purchase-orders/${viewing.id}/send`,{method:"POST"});
                    if (res.email_sent) alert(`✅ PO emailed to ${res.emailed_to}`);
                    else alert(`✅ ${viewing.po_number} marked as Sent. No email sent — supplier has no email address on file.`);
                    setViewing(res); load();
                  } catch(e){ alert(e.message); }
                }} style={{background:C.blueLt,color:C.blue,border:`1px solid ${C.blue}40`,borderRadius:6,padding:"6px 14px",fontSize:12,cursor:"pointer",fontWeight:600}}>📧 Send to Supplier</button>
              )}
              {viewing.status==="draft" && (
                <button onClick={()=>{updateStatus(viewing.id,"cancelled");setViewing({...viewing,status:"cancelled"});}} style={{background:C.bg,border:`1px solid ${C.border}`,borderRadius:6,padding:"6px 14px",fontSize:12,cursor:"pointer",color:C.inkMid}}>Cancel PO</button>
              )}
              <button onClick={()=>del(viewing.id)} style={{marginLeft:"auto",background:"none",border:`1px solid ${C.red}30`,borderRadius:6,padding:"6px 14px",fontSize:12,cursor:"pointer",color:C.red}}>Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* Goods Receipt modal */}
      {receiving && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:200,display:"flex",alignItems:"center",justifyContent:"center",padding:16}}>
          <div style={{background:C.surface,borderRadius:16,padding:28,maxWidth:600,width:"100%",maxHeight:"85vh",overflowY:"auto"}}>
            <div style={{marginBottom:20}}>
              <div style={{fontWeight:700,fontSize:18,color:C.ink}}>📦 Receive Goods — {receiving.po_number}</div>
              <div style={{fontSize:12,color:C.inkMid,marginTop:2}}>{receiving.supplier_name} · Confirm quantities received</div>
            </div>

            {/* Line items with received qty */}
            <div style={{background:C.bg,borderRadius:10,padding:14,marginBottom:16}}>
              <div style={{display:"grid",gridTemplateColumns:"1fr 80px 80px",gap:8,marginBottom:8}}>
                <div style={{fontSize:11,fontWeight:600,color:C.inkMid}}>Description</div>
                <div style={{fontSize:11,fontWeight:600,color:C.inkMid,textAlign:"right"}}>Ordered</div>
                <div style={{fontSize:11,fontWeight:600,color:C.inkMid,textAlign:"right"}}>Received</div>
              </div>
              {receiving.items.map(it=>(
                <div key={it.id} style={{display:"grid",gridTemplateColumns:"1fr 80px 80px",gap:8,marginBottom:8,alignItems:"center"}}>
                  <div style={{fontSize:13,color:C.ink}}>{it.description}</div>
                  <div style={{fontSize:13,color:C.inkMid,textAlign:"right"}}>{it.quantity}</div>
                  <input
                    type="number" min="0" max={it.quantity} step="0.01"
                    value={recvQtys[it.id]??it.quantity}
                    onChange={e=>setRecvQtys(q=>({...q,[it.id]:parseFloat(e.target.value)||0}))}
                    style={{padding:"6px 8px",border:`1px solid ${C.border}`,borderRadius:6,fontFamily:"inherit",fontSize:13,textAlign:"right",background:C.surface}}
                  />
                </div>
              ))}
            </div>

            {/* Received total */}
            {(()=>{
              const recvTotal = receiving.items.reduce((s,it)=>s+(recvQtys[it.id]??it.quantity)*it.unit_price,0);
              const vatAmt = receiving.vat_amount>0 ? recvTotal*0.15 : 0;
              return (
                <div style={{background:C.greenLt,borderRadius:8,padding:14,marginBottom:16,textAlign:"right",fontSize:13}}>
                  <div style={{color:C.inkMid}}>Received value: R{recvTotal.toFixed(2)}</div>
                  {vatAmt>0 && <div style={{color:C.inkMid}}>VAT (15%): R{vatAmt.toFixed(2)}</div>}
                  <div style={{fontWeight:700,fontSize:16,color:C.green,marginTop:4}}>Amount payable: R{(recvTotal+vatAmt).toFixed(2)}</div>
                </div>
              );
            })()}

            {/* Expense category */}
            <div style={{marginBottom:16}}>
              <div style={{fontSize:11,fontWeight:600,color:C.inkMid,marginBottom:4}}>Expense category (for payment processing)</div>
              <select value={recvCategory} onChange={e=>setRecvCategory(e.target.value)}
                style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontFamily:"inherit",fontSize:13,background:C.bg}}>
                <option value="5000 - Cost of Sales">5000 - Cost of Sales</option>
                <option value="6000 - Other Expenses">6000 - Other Expenses</option>
                <option value="6100 - Office Expenses">6100 - Office Expenses</option>
                <option value="6200 - Equipment">6200 - Equipment</option>
                <option value="6300 - Raw Materials">6300 - Raw Materials</option>
                <option value="6400 - Repairs & Maintenance">6400 - Repairs & Maintenance</option>
                <option value="6510 - Fuel and Oil">6510 - Fuel and Oil</option>
              </select>
            </div>

            <div style={{display:"flex",gap:10}}>
              <button onClick={async ()=>{
                try {
                  const payload = {
                    items: receiving.items.map(it=>({item_id:it.id, quantity_received: recvQtys[it.id]??it.quantity})),
                    create_expense: true,
                    expense_category: recvCategory,
                  };
                  const result = await api(`/purchase-orders/${receiving.id}/receive`,{method:"POST",body:JSON.stringify(payload)});
                  setRecvDone(result); setReceiving(null); load();
                } catch(e){ alert(e.message); }
              }} style={{background:C.green,color:"#fff",border:"none",borderRadius:8,padding:"10px 24px",fontWeight:600,cursor:"pointer"}}>
                ✓ Confirm Receipt
              </button>
              <button onClick={()=>{setReceiving(null);setViewing(null);}} style={{background:"transparent",border:`1px solid ${C.border}`,borderRadius:8,padding:"10px 24px",cursor:"pointer",color:C.inkMid}}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Receipt confirmation / payment summary */}
      {recvDone && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:200,display:"flex",alignItems:"center",justifyContent:"center",padding:16}}>
          <div style={{background:C.surface,borderRadius:16,padding:32,maxWidth:480,width:"100%",textAlign:"center"}}>
            <div style={{fontSize:48,marginBottom:12}}>✅</div>
            <div style={{fontWeight:700,fontSize:20,color:C.ink,marginBottom:8}}>Goods Received</div>
            <div style={{fontSize:13,color:C.inkMid,marginBottom:20}}>
              {recvDone.po_number} — {recvDone.supplier_name}<br/>
              Status updated to <strong style={{textTransform:"capitalize"}}>{recvDone.status}</strong>
            </div>
            <div style={{background:C.greenLt,borderRadius:10,padding:16,marginBottom:20}}>
              <div style={{fontSize:13,color:C.inkMid,marginBottom:4}}>Amount payable to supplier</div>
              <div style={{fontSize:28,fontWeight:700,color:C.green}}>R{recvDone.received_total?.toFixed(2)}</div>
              <div style={{fontSize:12,color:C.green,marginTop:8}}>✓ Inventory & accounts payable updated in ledger</div>
            </div>
            <div style={{fontSize:13,color:C.inkMid,marginBottom:20}}>
              Journal entries posted: DR Inventory / CR Accounts Payable. Click <strong>Mark as Paid</strong> on the PO when you process payment to clear the liability.
            </div>
            <button onClick={()=>setRecvDone(null)} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"12px 32px",fontWeight:600,cursor:"pointer",fontSize:14}}>Done</button>
          </div>
        </div>
      )}

      {filtered.length === 0 ? (
        <div style={{textAlign:"center",padding:"60px 0",color:C.inkDim}}>
          <div style={{fontSize:40,marginBottom:12}}>📋</div>
          <div style={{fontSize:15,fontWeight:600}}>No purchase orders</div>
          <div style={{fontSize:13,marginTop:4}}>Create your first PO to start tracking procurement</div>
        </div>
      ) : (
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,overflow:"hidden"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
            <thead><tr style={{background:C.bg}}>
              <th style={{textAlign:"left",padding:"12px 16px",fontWeight:600,color:C.inkMid}}>PO Number</th>
              <th style={{textAlign:"left",padding:"12px 16px",fontWeight:600,color:C.inkMid}}>Supplier</th>
              <th style={{textAlign:"left",padding:"12px 16px",fontWeight:600,color:C.inkMid}}>Date</th>
              <th style={{textAlign:"left",padding:"12px 16px",fontWeight:600,color:C.inkMid}}>Status</th>
              <th style={{textAlign:"right",padding:"12px 16px",fontWeight:600,color:C.inkMid}}>Total</th>
              <th style={{padding:"12px 16px"}}></th>
            </tr></thead>
            <tbody>{filtered.map(p=>(
              <tr key={p.id} style={{borderTop:`1px solid ${C.border}`}}>
                <td style={{padding:"12px 16px",fontWeight:600,color:C.ink}}>{p.po_number}</td>
                <td style={{padding:"12px 16px",color:C.inkMid}}>{p.supplier_name||"—"}</td>
                <td style={{padding:"12px 16px",color:C.inkMid}}>{p.order_date}</td>
                <td style={{padding:"12px 16px"}}><span style={{padding:"3px 10px",borderRadius:20,fontSize:11,fontWeight:600,background:PO_STATUS_COLORS[p.status]||C.goldLt,color:PO_STATUS_TEXT[p.status]||C.gold,textTransform:"capitalize"}}>{p.status}</span></td>
                <td style={{padding:"12px 16px",textAlign:"right",fontWeight:600,color:C.ink}}>R{p.total_amount.toFixed(2)}</td>
                <td style={{padding:"12px 16px"}}><button onClick={()=>setViewing(p)} style={{background:C.accentLt,color:C.accent,border:"none",borderRadius:6,padding:"5px 12px",fontSize:12,cursor:"pointer",fontWeight:600}}>View</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── AI ASSISTANT ──────────────────────────────────────────────────────────────
const AI_SUGGESTIONS = [
  "How do I categorise a fuel expense?",
  "What is the PAYE rate for R35,000/month?",
  "When is EMP201 due?",
  "How do I record a bad debt?",
  "What is the VAT rate in South Africa?",
];
const AI_QUICK_PROMPTS = {
  invoicing: ["How do I create an invoice?","How do I mark an invoice as paid?","What makes a valid tax invoice?","How do I handle overdue invoices?"],
  quotes:    ["How do I create a quote?","How do I convert a quote to an invoice?","What should a quote include?","How long should a quote be valid?"],
  expenses:  ["How do I add an expense?","How do I categorise expenses?","Can I claim input VAT on expenses?","How do I scan a receipt?"],
  payroll:   ["What is the PAYE rate for R35,000/month?","When is EMP201 due?","How is UIF calculated?","What is SDL?"],
  default:   ["How do I create an invoice?","What is the VAT rate?","How do I record a bad debt?","When is EMP201 due?"],
};

function AIAssistant({tab}) {
  const [open,     setOpen]     = useState(false);
  const [messages, setMessages] = useState([{role:"assistant",text:"Hi! I'm ZuZan AI. Ask me anything about invoicing, quotes, expenses, payroll, or SARS compliance."}]);
  const [input,    setInput]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const bottomRef = useRef(null);
  const prompts = AI_QUICK_PROMPTS[tab] || AI_QUICK_PROMPTS.default;

  useEffect(() => { if(bottomRef.current) bottomRef.current.scrollIntoView({behavior:"smooth"}); }, [messages]);

  const send = async (text) => {
    const q = text || input;
    if (!q.trim()) return;
    setInput("");
    setMessages(m=>[...m,{role:"user",text:q}]);
    setLoading(true);
    try {
      const res = await api("/ai/chat",{method:"POST",body:JSON.stringify({message:q,context:tab||"dashboard"})});
      const reply = typeof res === "string" ? res : (res.reply||res.response||res.message||res.answer||res.text||JSON.stringify(res));
      setMessages(m=>[...m,{role:"assistant",text:reply||"I can help with that. Please check the relevant section of the app."}]);
    } catch(e) {
      // Fallback local answers
      const lower = q.toLowerCase();
      let reply = "I'm not connected to the AI service right now. Please try again later.";
      if(lower.includes("paye") && lower.includes("35000")) reply = "For R35,000/month gross: Annual income R420,000. PAYE ≈ R4,673/month after the R17,235 primary rebate. Check the Payroll tab for exact figures.";
      else if(lower.includes("emp201")) reply = "EMP201 is due by the 7th of each month following the payroll period. You can download the EMP201 from the Payroll tab after running payroll.";
      else if(lower.includes("vat")) reply = "The standard VAT rate in South Africa is 15%. Some items are zero-rated (basic foods, exports). VAT201 is due monthly or bi-monthly depending on your registration.";
      else if(lower.includes("fuel") || lower.includes("petrol")) reply = "Fuel should be categorised to account 6510 - Fuel and Oil under Expenses. If the vehicle is used partly for business and partly private, only the business portion is deductible.";
      else if(lower.includes("bad debt")) reply = "Record a bad debt by creating an expense to account 7300 - Bad Debts Written Off, matching it against the outstanding invoice. This reduces your debtors and is tax deductible.";
      else if(lower.includes("uif")) reply = "UIF is 1% employee + 1% employer, capped at R17,712/month gross. Both amounts are calculated automatically in the Payroll tab.";
      setMessages(m=>[...m,{role:"assistant",text:reply}]);
    } finally { setLoading(false); }
  };

  return (
    <>
      {/* Floating button */}
      <button onClick={()=>setOpen(o=>!o)} style={{position:"fixed",bottom:90,right:20,width:50,height:50,borderRadius:"50%",background:C.accent,color:"#fff",border:"none",fontSize:22,cursor:"pointer",boxShadow:"0 4px 20px rgba(200,64,26,0.4)",zIndex:500,display:"flex",alignItems:"center",justifyContent:"center"}}>
        {open?"✕":"🤖"}
      </button>

      {/* Chat panel */}
      {open && (
        <div style={{position:"fixed",bottom:152,right:20,width:360,height:460,background:C.surface,borderRadius:20,boxShadow:"0 8px 40px rgba(0,0,0,0.2)",zIndex:500,display:"flex",flexDirection:"column",overflow:"hidden",border:`1px solid ${C.border}`}}>
          <div style={{padding:"14px 18px",background:C.accent,color:"#fff",display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <div><div style={{fontWeight:700,fontSize:14}}>ZuZan AI Assistant</div><div style={{fontSize:11,opacity:0.8}}>Bookkeeping & SARS help</div></div>
          </div>

          {/* Messages */}
          <div style={{flex:1,overflowY:"auto",padding:"14px 16px",display:"flex",flexDirection:"column",gap:10}}>
            {messages.map((m,i)=>(
              <div key={i} style={{display:"flex",justifyContent:m.role==="user"?"flex-end":"flex-start"}}>
                <div style={{maxWidth:"80%",padding:"10px 14px",borderRadius:m.role==="user"?"16px 16px 4px 16px":"16px 16px 16px 4px",background:m.role==="user"?C.accent:C.bg,color:m.role==="user"?"#fff":C.ink,fontSize:13,lineHeight:1.5}}>
                  {m.text}
                </div>
              </div>
            ))}
            {loading && (
              <div style={{display:"flex",justifyContent:"flex-start"}}>
                <div style={{padding:"10px 14px",borderRadius:"16px 16px 16px 4px",background:C.bg,fontSize:13,color:C.inkMid}}>Thinking...</div>
              </div>
            )}
            <div ref={bottomRef}/>
          </div>

          {/* Suggestions */}
          {messages.length <= 1 && (
            <div style={{padding:"0 12px 8px",display:"flex",flexWrap:"wrap",gap:6}}>
              {prompts.map(s=>(
                <button key={s} onClick={()=>send(s)} style={{padding:"5px 10px",borderRadius:14,border:`1px solid ${C.border}`,background:C.bg,color:C.inkMid,fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>{s}</button>
              ))}
            </div>
          )}

          {/* Input */}
          <div style={{padding:"10px 12px",borderTop:`1px solid ${C.border}`,display:"flex",gap:8}}>
            <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&send()} placeholder="Ask a bookkeeping question..." style={{flex:1,padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:10,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}/>
            <button onClick={()=>send()} disabled={loading} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"9px 16px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Send</button>
          </div>
        </div>
      )}
    </>
  );
}

// ── FIXED ASSETS ─────────────────────────────────────────────────────────────
const FA_CATS = ["Land & Buildings","Plant & Machinery","Motor Vehicles","Furniture & Fittings","Computer Equipment","Office Equipment","Leasehold Improvements","Other Fixed Assets"];
const FA_USEFUL_LIVES = {"Land & Buildings":480,"Plant & Machinery":120,"Motor Vehicles":60,"Furniture & Fittings":120,"Computer Equipment":36,"Office Equipment":60,"Leasehold Improvements":120,"Other Fixed Assets":60};

// SARS IN47 Wear & Tear table — client-side mirror for instant previews
const SARS_WT = {
  "Computers — desktops / laptops":          {years:3, section:"11(e)"},
  "Smartphones / Tablets":                   {years:2, section:"11(e)"},
  "Printers / Photocopiers / Scanners":      {years:3, section:"11(e)"},
  "Fax machines":                            {years:3, section:"11(e)"},
  "Software — purchased (off-the-shelf)":    {years:2, section:"11(e)"},
  "Software — custom developed":             {years:3, section:"11(e)"},
  "Office equipment (general)":              {years:5, section:"11(e)"},
  "Televisions / Display screens":           {years:6, section:"11(e)"},
  "Furniture and fittings":                  {years:6, section:"11(e)"},
  "Carpets / Floor coverings":               {years:6, section:"11(e)"},
  "Air conditioners (portable)":             {years:5, section:"11(e)"},
  "Motor vehicles — passenger":              {years:5, section:"11(e)"},
  "Motor vehicles — light delivery (≤3.5t)":{years:4, section:"11(e)"},
  "Trucks / Heavy vehicles (>3.5t)":         {years:4, section:"11(e)"},
  "Motorcycles":                             {years:4, section:"11(e)"},
  "Trailers":                                {years:5, section:"11(e)"},
  "Forklifts":                               {years:4, section:"11(e)"},
  "Aircraft (light)":                        {years:4, section:"11(e)"},
  "Machinery — general":                     {years:5, section:"11(e)"},
  "Manufacturing plant (general)":           {years:5, section:"11(e)"},
  "Manufacturing plant — new/unused (s12C)":{years:4, section:"12C", note:"40% yr1, 20% yrs 2-4"},
  "Tools — hand tools":                      {years:3, section:"11(e)"},
  "Tools — power tools":                     {years:3, section:"11(e)"},
  "Commercial buildings (s13quin)":          {years:25, section:"13quin", note:"Eligible commercial buildings only"},
  "Industrial / Manufacturing buildings":    {years:10, section:"13",     note:"Used in process of manufacture"},
  "Hotel buildings":                         {years:20, section:"13bis"},
  "Residential rental property":             {years:25, section:"13sex",  note:"New/unused residential units only"},
  "Solar PV panels (≤1 MW, s12BA)":         {years:1, section:"12BA", note:"125% first-year deduction"},
  "Wind energy equipment":                   {years:1, section:"12B",  note:"100% first-year deduction"},
  "Biomass / Small hydro equipment":         {years:3, section:"12B"},
  "Bicycles":                                {years:4, section:"11(e)"},
  "Cash registers / POS systems":            {years:3, section:"11(e)"},
  "Security systems / CCTV":                 {years:5, section:"11(e)"},
  "Telephone systems (PABX / VoIP)":         {years:5, section:"11(e)"},
  "Medical / Dental equipment":              {years:5, section:"11(e)"},
  "Kitchen equipment (commercial)":          {years:6, section:"11(e)"},
  "Gym / Fitness equipment":                 {years:5, section:"11(e)"},
};
const SARS_WT_CATS = Object.keys(SARS_WT);
const SA_CIT = 0.27;

function sarsCalcTaxBase(cost, purchaseDateStr, sarsCategory) {
  const info = SARS_WT[sarsCategory];
  if (!info || !purchaseDateStr || !cost) return null;
  const years = info.years;
  const purchaseDate = new Date(purchaseDateStr);
  const now = new Date();
  const monthsElapsed = Math.max(0,
    (now.getFullYear() - purchaseDate.getFullYear()) * 12 +
    (now.getMonth()    - purchaseDate.getMonth()));
  const monthlyAllowance = years > 0 ? cost / (years * 12) : cost;
  const accumulated = years > 0 ? Math.min(monthsElapsed * monthlyAllowance, cost) : cost;
  const taxBase = Math.max(0, cost - accumulated);
  return {taxBase, accumulated, monthlyAllowance, years, section:info.section, note:info.note};
}

function FixedAssets() {
  const [assets,     setAssets]     = useState([]);
  const [schedule,   setSchedule]   = useState([]);
  const [cats,       setCats]       = useState([]);
  const [deferredTax,setDeferredTax]= useState(null);
  const [loading,    setLoading]    = useState(true);
  const [section,    setSection]    = useState("register");  // register | schedule | tax | add
  const [disposing,    setDisposing]    = useState(null);
  const [saving,       setSaving]       = useState(false);
  const [runningDepr,  setRunningDepr]  = useState(false);
  const [form, setForm] = useState({
    asset_name:"", category:"Motor Vehicles", description:"", location:"",
    purchase_date: new Date().toISOString().slice(0,10),
    cost:"", residual_value:"0", useful_life_months:"60",
    depreciation_method:"straight_line", depreciation_rate:"0.20",
    sars_category:"",
    post_journal:true,
  });
  const [dispForm, setDispForm] = useState({disposal_date: new Date().toISOString().slice(0,10), disposal_proceeds:"0", disposal_notes:"", is_write_off:false});

  const load = async () => {
    setLoading(true);
    try {
      const [a, s, c, dt] = await Promise.all([
        api("/fixed-assets/"),
        api("/fixed-assets/schedule"),
        api("/fixed-assets/categories"),
        api("/fixed-assets/deferred-tax"),
      ]);
      setAssets(a); setSchedule(s); setCats(c); setDeferredTax(dt);
    } catch(e) { console.warn("Fixed assets load:", e); }
    setLoading(false);
  };
  useEffect(()=>{ load(); },[]);

  // KPI aggregates
  const activeAssets   = assets.filter(a => a.status === "active");
  const totalCost      = activeAssets.reduce((s,a) => s + a.cost, 0);
  const totalAccumDepr = activeAssets.reduce((s,a) => s + a.accumulated_depreciation, 0);
  const totalNBV       = activeAssets.reduce((s,a) => s + a.carrying_value, 0);
  const monthlyDepr    = activeAssets.reduce((s,a) => s + (a.monthly_depreciation||0), 0);
  const netDT          = deferredTax?.summary?.net_position ?? 0;
  const netDTType      = deferredTax?.summary?.net_type ?? "Nil";

  const statusColor = st => st === "active" ? C.green : st === "disposed" ? C.blue : C.red;
  const statusBg    = st => st === "active" ? C.greenLt : st === "disposed" ? C.blueLt : C.redLt;

  const handleAdd = async () => {
    if (!form.asset_name || !form.cost || !form.purchase_date) {
      alert("Asset name, cost and purchase date are required."); return;
    }
    if (form.depreciation_method === "diminishing_balance" && !form.depreciation_rate) {
      alert("Depreciation rate is required for diminishing balance method."); return;
    }
    setSaving(true);
    try {
      await api("/fixed-assets/", {method:"POST", body: JSON.stringify({
        asset_name:          form.asset_name,
        category:            form.category,
        description:         form.description || null,
        location:            form.location || null,
        purchase_date:       form.purchase_date,
        cost:                +form.cost,
        residual_value:      +form.residual_value || 0,
        useful_life_months:  +form.useful_life_months,
        depreciation_method: form.depreciation_method,
        depreciation_rate:   form.depreciation_method === "diminishing_balance" ? +form.depreciation_rate : null,
        sars_category:       form.sars_category || null,
        post_journal:        form.post_journal,
      })});
      setForm({asset_name:"",category:"Motor Vehicles",description:"",location:"",purchase_date:new Date().toISOString().slice(0,10),cost:"",residual_value:"0",useful_life_months:"60",depreciation_method:"straight_line",depreciation_rate:"0.20",sars_category:"",post_journal:true});
      setSection("register");
      load();
    } catch(e) { alert("Failed: " + e.message); }
    setSaving(false);
  };

  const handleDispose = async () => {
    if (!disposing) return;
    setSaving(true);
    try {
      const res = await api(`/fixed-assets/${disposing.id}/dispose`, {method:"POST", body: JSON.stringify({
        disposal_date:     dispForm.disposal_date,
        disposal_proceeds: dispForm.is_write_off ? 0 : +dispForm.disposal_proceeds,
        disposal_notes:    dispForm.disposal_notes || null,
        is_write_off:      dispForm.is_write_off,
      })});
      const gl = res.gain_loss;
      alert(`${res.message}`);
      setDisposing(null); setSection("register"); load();
    } catch(e) { alert("Failed: " + e.message); }
    setSaving(false);
  };

  const INP = {width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"};
  const LBL = {fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:5,textTransform:"uppercase",letterSpacing:0.5};
  const TABS = [{id:"register",label:"Asset Register"},{id:"schedule",label:"Depreciation Schedule"},{id:"tax",label:"Deferred Tax (IAS 12)"},{id:"add",label:"+ Add Asset"}];

  return (
    <div>
      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:20}}>
        <div>
          <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:0}}>Fixed Assets</h2>
          <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>IAS 16 — cost model, straight-line &amp; diminishing balance</p>
        </div>
        <button
          disabled={runningDepr}
          onClick={async()=>{
            if(!window.confirm("Run monthly depreciation for all active assets now?")) return;
            setRunningDepr(true);
            try {
              const res = await api("/fixed-assets/run-depreciation", {method:"POST"});
              alert(res.message || `Depreciation complete — ${res.assets_depreciated} asset(s), R${(res.total_depreciation||0).toFixed(2)} charged.`);
              load();
            } catch(e) { alert("Depreciation failed: " + e.message); }
            setRunningDepr(false);
          }}
          style={{background:C.gold,color:"#fff",border:"none",borderRadius:10,padding:"10px 18px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:runningDepr?0.6:1,whiteSpace:"nowrap"}}>
          {runningDepr ? "Running..." : "▶ Run Depreciation"}
        </button>
      </div>

      {/* KPI cards */}
      <div style={{display:"flex",gap:12,marginBottom:20,flexWrap:"wrap"}}>
        <KPI label="At Cost"             value={fmt(totalCost)}      color={C.ink}    icon="🏭"/>
        <KPI label="Accum. Depreciation" value={fmt(totalAccumDepr)} color={C.gold}   icon="📉"/>
        <KPI label="Net Book Value"      value={fmt(totalNBV)}       color={C.accent} icon="📊"/>
        <KPI label="Monthly Charge"      value={fmt(monthlyDepr)}    color={C.blue}   icon="📅"/>
        <KPI label={`Deferred Tax (${netDTType})`}
             value={fmt(Math.abs(netDT))}
             color={netDTType==="DTL"?C.red:netDTType==="DTA"?C.green:C.inkMid}
             icon="🧾"
             onClick={()=>{setSection("tax");setDisposing(null);}}
             active={section==="tax"}/>
      </div>

      {/* Section tabs */}
      <div style={{display:"flex",gap:4,marginBottom:20,borderBottom:`1px solid ${C.border}`}}>
        {TABS.map(t=>(
          <button key={t.id} onClick={()=>{setSection(t.id);setDisposing(null);}} style={{background:"none",border:"none",borderBottom:section===t.id?`2px solid ${C.accent}`:"2px solid transparent",padding:"8px 18px",fontSize:13,fontWeight:section===t.id?700:400,color:section===t.id?C.accent:C.inkMid,cursor:"pointer",fontFamily:"inherit",marginBottom:"-1px"}}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── ASSET REGISTER ── */}
      {section === "register" && !disposing && (
        <div>
          {loading ? <div style={{color:C.inkMid,padding:20}}>Loading...</div> : assets.length === 0 ? (
            <div style={{textAlign:"center",color:C.inkMid,padding:40}}>No assets yet. Click "+ Add Asset" to begin.</div>
          ) : (
            <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden",marginBottom:16}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                <thead>
                  <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                    {["#","Asset","Category","Cost","Accum. Depr","Carrying Value","Method","Monthly Depr","Status",""].map(h=>(
                      <th key={h} style={{textAlign:"left",padding:"11px 14px",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {assets.map(a => (
                    <tr key={a.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                      <td style={{padding:"12px 14px",color:C.inkMid,fontSize:11}}>{a.asset_number}</td>
                      <td style={{padding:"12px 14px"}}>
                        <div style={{fontWeight:600,color:C.ink}}>{a.asset_name}</div>
                        {a.description && <div style={{fontSize:10,color:C.inkMid}}>{a.description}</div>}
                        {a.location    && <div style={{fontSize:10,color:C.inkDim}}>📍 {a.location}</div>}
                      </td>
                      <td style={{padding:"12px 14px",color:C.inkMid,whiteSpace:"nowrap"}}>{a.category}</td>
                      <td style={{padding:"12px 14px",fontWeight:600}}>{fmt(a.cost)}</td>
                      <td style={{padding:"12px 14px",color:C.gold,fontWeight:600}}>{fmt(a.accumulated_depreciation)}</td>
                      <td style={{padding:"12px 14px",fontWeight:700,color:C.accent}}>{fmt(a.carrying_value)}</td>
                      <td style={{padding:"12px 14px",fontSize:11,color:C.inkMid,whiteSpace:"nowrap"}}>
                        {a.depreciation_method === "straight_line" ? `SL / ${a.useful_life_months}m` : `DB ${((a.depreciation_rate||0)*100).toFixed(0)}%`}
                      </td>
                      <td style={{padding:"12px 14px",color:C.blue,fontWeight:600}}>{a.status==="active"?fmt(a.monthly_depreciation):"—"}</td>
                      <td style={{padding:"12px 14px"}}>
                        <span style={{background:statusBg(a.status),color:statusColor(a.status),borderRadius:6,padding:"3px 10px",fontSize:11,fontWeight:700,textTransform:"capitalize"}}>{a.status}</span>
                      </td>
                      <td style={{padding:"12px 14px"}}>
                        {a.status === "active" && (
                          <button onClick={()=>{setDisposing(a);setDispForm({disposal_date:new Date().toISOString().slice(0,10),disposal_proceeds:"0",disposal_notes:"",is_write_off:false});}} style={{background:C.redLt,color:C.red,border:"none",borderRadius:6,padding:"5px 10px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:700,whiteSpace:"nowrap"}}>Dispose</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{background:C.bg,borderTop:`2px solid ${C.border}`}}>
                    <td colSpan={3} style={{padding:"12px 14px",fontWeight:800,color:C.ink}}>TOTALS ({activeAssets.length} active)</td>
                    <td style={{padding:"12px 14px",fontWeight:800}}>{fmt(totalCost)}</td>
                    <td style={{padding:"12px 14px",fontWeight:800,color:C.gold}}>{fmt(totalAccumDepr)}</td>
                    <td style={{padding:"12px 14px",fontWeight:800,color:C.accent}}>{fmt(totalNBV)}</td>
                    <td colSpan={2} style={{padding:"12px 14px",fontWeight:800,color:C.blue}}>{fmt(monthlyDepr)}/mo</td>
                    <td colSpan={2}/>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
          <div style={{fontSize:12,color:C.inkMid,padding:"10px 14px",background:C.accentLt,border:`1px solid ${C.accent}30`,borderRadius:10}}>
            <strong style={{color:C.accent}}>Depreciation note:</strong> Click "▶ Run Depreciation" at the top of this page to post monthly depreciation for all active assets. The run is idempotent — running it more than once in the same calendar month has no effect.
          </div>
        </div>
      )}

      {/* ── DISPOSAL MODAL ── */}
      {section === "register" && disposing && (
        <div style={{background:C.surface,border:`2px solid ${C.red}`,borderRadius:16,padding:28,maxWidth:560}}>
          <h3 style={{fontFamily:"serif",fontSize:20,margin:"0 0 4px",color:C.ink}}>Dispose / Write-off Asset</h3>
          <p style={{fontSize:13,color:C.inkMid,marginBottom:20}}>{disposing.asset_number} — {disposing.asset_name}</p>

          <div style={{background:C.bg,borderRadius:10,padding:14,marginBottom:20,fontSize:13}}>
            <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}><span style={{color:C.inkMid}}>Cost</span><span style={{fontWeight:600}}>{fmt(disposing.cost)}</span></div>
            <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}><span style={{color:C.inkMid}}>Accumulated Depreciation</span><span style={{color:C.gold,fontWeight:600}}>{fmt(disposing.accumulated_depreciation)}</span></div>
            <div style={{display:"flex",justifyContent:"space-between",borderTop:`1px solid ${C.border}`,paddingTop:8,marginTop:4}}><span style={{fontWeight:700}}>Carrying Value</span><span style={{fontWeight:800,color:C.accent}}>{fmt(disposing.carrying_value)}</span></div>
          </div>

          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:16,padding:"12px",background:C.redLt,borderRadius:10}}>
            <input type="checkbox" checked={dispForm.is_write_off} onChange={e=>setDispForm(v=>({...v,is_write_off:e.target.checked,disposal_proceeds:"0"}))} style={{width:18,height:18}}/>
            <span style={{fontSize:14,color:C.ink}}>Write-off (no proceeds — full loss recognised)</span>
          </div>

          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
            <div>
              <label style={LBL}>Disposal Date</label>
              <input type="date" value={dispForm.disposal_date} onChange={e=>setDispForm(v=>({...v,disposal_date:e.target.value}))} style={INP}/>
            </div>
            {!dispForm.is_write_off && (
              <div>
                <label style={LBL}>Proceeds Received (ZAR)</label>
                <input type="number" value={dispForm.disposal_proceeds} onChange={e=>setDispForm(v=>({...v,disposal_proceeds:e.target.value}))} style={INP}/>
              </div>
            )}
          </div>
          <div style={{marginBottom:16}}>
            <label style={LBL}>Notes</label>
            <input placeholder="e.g. Sold to XYZ, vehicle scrapped..." value={dispForm.disposal_notes} onChange={e=>setDispForm(v=>({...v,disposal_notes:e.target.value}))} style={INP}/>
          </div>

          {/* Preview gain/loss */}
          {(() => {
            const proceeds = dispForm.is_write_off ? 0 : (+dispForm.disposal_proceeds||0);
            const gl = proceeds - disposing.carrying_value;
            return (
              <div style={{background: gl >= 0 ? C.greenLt : C.redLt, border:`1px solid ${gl>=0?C.green:C.red}40`, borderRadius:10, padding:"12px 16px", marginBottom:16, fontSize:13}}>
                <strong>{gl >= 0 ? "Gain on disposal" : "Loss on disposal"}:</strong> {fmt(Math.abs(gl))}
                {gl < 0 && <span style={{color:C.inkMid,marginLeft:8}}>— will be posted to Loss on Disposal (6800)</span>}
                {gl > 0 && <span style={{color:C.inkMid,marginLeft:8}}>— will be posted to Gain on Disposal (4900)</span>}
              </div>
            );
          })()}

          <div style={{display:"flex",gap:10}}>
            <button onClick={()=>setDisposing(null)} style={{flex:1,background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"11px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
            <button onClick={handleDispose} disabled={saving} style={{flex:1,background:C.red,color:"#fff",border:"none",borderRadius:10,padding:"11px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>
              {saving ? "Processing..." : dispForm.is_write_off ? "Write Off Asset" : "Confirm Disposal"}
            </button>
          </div>
        </div>
      )}

      {/* ── DEFERRED TAX (IAS 12) ── */}
      {section === "tax" && (
        <div>
          {/* Summary cards */}
          {deferredTax && (
            <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12,marginBottom:20}}>
              <div style={{background:C.redLt,border:`1px solid ${C.red}30`,borderRadius:12,padding:"16px 20px"}}>
                <div style={{fontSize:10,fontWeight:700,color:C.red,textTransform:"uppercase",letterSpacing:0.5,marginBottom:6}}>Gross DTL</div>
                <div style={{fontSize:20,fontWeight:800,color:C.red}}>{fmt(deferredTax.summary.gross_dtl)}</div>
                <div style={{fontSize:11,color:C.inkMid,marginTop:4}}>Deferred Tax Liabilities</div>
              </div>
              <div style={{background:C.greenLt,border:`1px solid ${C.green}30`,borderRadius:12,padding:"16px 20px"}}>
                <div style={{fontSize:10,fontWeight:700,color:C.green,textTransform:"uppercase",letterSpacing:0.5,marginBottom:6}}>Gross DTA</div>
                <div style={{fontSize:20,fontWeight:800,color:C.green}}>{fmt(deferredTax.summary.gross_dta)}</div>
                <div style={{fontSize:11,color:C.inkMid,marginTop:4}}>Deferred Tax Assets</div>
              </div>
              <div style={{background:C.accentLt,border:`1px solid ${C.accent}30`,borderRadius:12,padding:"16px 20px"}}>
                <div style={{fontSize:10,fontWeight:700,color:C.accent,textTransform:"uppercase",letterSpacing:0.5,marginBottom:6}}>Net Position</div>
                <div style={{fontSize:20,fontWeight:800,color:deferredTax.summary.net_type==="DTL"?C.red:deferredTax.summary.net_type==="DTA"?C.green:C.inkMid}}>{fmt(Math.abs(deferredTax.summary.net_position))}</div>
                <div style={{fontSize:11,color:C.inkMid,marginTop:4}}>Net {deferredTax.summary.net_type} — Balance sheet line</div>
              </div>
            </div>
          )}

          {/* Deferred tax asset schedule */}
          {deferredTax?.assets?.length > 0 ? (
            <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden",marginBottom:16}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:11}}>
                <thead>
                  <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                    {["Asset","SARS Category (s)","Cost","Accum. SARS Allowance","Tax Base","IAS 16 Carrying Value","Temp. Difference","Deferred Tax @ 27%","Type"].map(h=>(
                      <th key={h} style={{textAlign:"left",padding:"10px 12px",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {deferredTax.assets.map(row => {
                    const isLiability = row.deferred_tax_type === "DTL";
                    const isAsset     = row.deferred_tax_type === "DTA";
                    return (
                      <tr key={row.asset_id} style={{borderBottom:`1px solid ${C.border}30`}}>
                        <td style={{padding:"11px 12px"}}>
                          <div style={{fontWeight:600,color:C.ink}}>{row.asset_name}</div>
                          <div style={{fontSize:10,color:C.inkMid}}>{row.asset_number} · {row.category}</div>
                        </td>
                        <td style={{padding:"11px 12px"}}>
                          <div style={{color:C.ink,fontSize:11}}>{row.sars_category}</div>
                          <div style={{fontSize:10,color:C.blue,fontWeight:600}}>s{row.section} · {row.sars_years}yr write-off</div>
                          {row.note && <div style={{fontSize:9,color:C.inkMid,fontStyle:"italic",marginTop:2}}>{row.note}</div>}
                        </td>
                        <td style={{padding:"11px 12px",fontWeight:600}}>{fmt(row.cost)}</td>
                        <td style={{padding:"11px 12px",color:C.gold,fontWeight:600}}>{fmt(row.accumulated_allowance)}</td>
                        <td style={{padding:"11px 12px",fontWeight:700}}>{fmt(row.tax_base)}</td>
                        <td style={{padding:"11px 12px",fontWeight:700,color:C.accent}}>{fmt(row.accounting_carrying_value)}</td>
                        <td style={{padding:"11px 12px",fontWeight:700,color:row.temporary_difference>0?C.red:row.temporary_difference<0?C.green:C.inkMid}}>
                          {row.temporary_difference > 0 ? "+" : ""}{fmt(row.temporary_difference)}
                        </td>
                        <td style={{padding:"11px 12px",fontWeight:800,color:isLiability?C.red:isAsset?C.green:C.inkMid}}>
                          {fmt(Math.abs(row.deferred_tax))}
                        </td>
                        <td style={{padding:"11px 12px"}}>
                          <span style={{background:isLiability?C.redLt:isAsset?C.greenLt:C.bg,color:isLiability?C.red:isAsset?C.green:C.inkMid,borderRadius:6,padding:"3px 10px",fontSize:11,fontWeight:700}}>{row.deferred_tax_type}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr style={{background:C.bg,borderTop:`2px solid ${C.border}`}}>
                    <td colSpan={6} style={{padding:"11px 12px",fontWeight:800,color:C.ink}}>NET DEFERRED TAX POSITION</td>
                    <td style={{padding:"11px 12px",fontWeight:800,color:deferredTax.summary.net_type==="DTL"?C.red:deferredTax.summary.net_type==="DTA"?C.green:C.inkMid}}>
                      {deferredTax.summary.net_position > 0 ? "+" : ""}{fmt(deferredTax.summary.net_position)}
                    </td>
                    <td style={{padding:"11px 12px",fontWeight:800,color:deferredTax.summary.net_type==="DTL"?C.red:C.green}}>
                      {fmt(Math.abs(deferredTax.summary.net_position))}
                    </td>
                    <td style={{padding:"11px 12px"}}>
                      <span style={{background:deferredTax.summary.net_type==="DTL"?C.redLt:deferredTax.summary.net_type==="DTA"?C.greenLt:C.bg,color:deferredTax.summary.net_type==="DTL"?C.red:deferredTax.summary.net_type==="DTA"?C.green:C.inkMid,borderRadius:6,padding:"3px 10px",fontSize:11,fontWeight:700}}>{deferredTax.summary.net_type}</span>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          ) : (
            <div style={{textAlign:"center",color:C.inkMid,padding:40}}>
              No assets with SARS categories assigned yet. Add a SARS category when creating an asset to see deferred tax.
            </div>
          )}

          {/* Unclassified warning */}
          {deferredTax?.unclassified_count > 0 && (
            <div style={{background:"#fff8e1",border:"1px solid #ffc10730",borderRadius:10,padding:"12px 16px",fontSize:12,color:"#7c5c00",marginBottom:12}}>
              ⚠️ <strong>{deferredTax.unclassified_count} active asset{deferredTax.unclassified_count>1?"s":""}</strong> have no SARS category assigned — these are excluded from the deferred tax calculation. Assign a SARS category by editing the asset.
            </div>
          )}

          <div style={{fontSize:12,color:C.inkMid,padding:"10px 14px",background:C.accentLt,border:`1px solid ${C.accent}30`,borderRadius:10}}>
            <strong style={{color:C.accent}}>IAS 12 note:</strong> Temporary differences arise when the IAS 16 carrying value differs from the SARS tax base (cost less IN47 wear & tear allowances claimed). A DTL arises when the carrying value exceeds the tax base (accounting depreciated more slowly than SARS allows). A DTA arises when the tax base exceeds the carrying value. CIT rate used: 27%.
          </div>
        </div>
      )}

      {/* ── DEPRECIATION SCHEDULE ── */}
      {section === "schedule" && (
        <div>
          {loading ? <div style={{color:C.inkMid,padding:20}}>Loading...</div> : schedule.length === 0 ? (
            <div style={{textAlign:"center",color:C.inkMid,padding:40}}>No depreciation entries yet. Use the "▶ Run Depreciation" button to post the first month.</div>
          ) : (
            <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                <thead>
                  <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                    {["Period","Asset","Amount","Posted"].map(h=>(
                      <th key={h} style={{textAlign:"left",padding:"11px 14px",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {schedule.map(e=>(
                    <tr key={e.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                      <td style={{padding:"12px 14px",fontWeight:700,color:C.ink}}>{e.period}</td>
                      <td style={{padding:"12px 14px",color:C.inkMid}}>{e.asset_name}</td>
                      <td style={{padding:"12px 14px",fontWeight:600,color:C.gold}}>{fmt(e.amount)}</td>
                      <td style={{padding:"12px 14px",fontSize:11,color:C.inkDim}}>{e.posted_at ? new Date(e.posted_at).toLocaleDateString("en-ZA") : "—"}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{background:C.bg,borderTop:`2px solid ${C.border}`}}>
                    <td colSpan={2} style={{padding:"12px 14px",fontWeight:800}}>Total Depreciation Posted</td>
                    <td style={{padding:"12px 14px",fontWeight:800,color:C.gold}}>{fmt(schedule.reduce((s,e)=>s+e.amount,0))}</td>
                    <td/>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── ADD ASSET FORM ── */}
      {section === "add" && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:28,maxWidth:680}}>
          <h3 style={{fontFamily:"serif",fontSize:20,margin:"0 0 20px",color:C.ink}}>Add Fixed Asset</h3>

          <div style={{fontSize:11,fontWeight:700,color:C.accent,textTransform:"uppercase",letterSpacing:1,marginBottom:10}}>Asset Details</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:16}}>
            <div>
              <label style={LBL}>Asset Name</label>
              <input placeholder="e.g. Delivery Vehicle — Toyota Hilux" value={form.asset_name} onChange={e=>setForm(v=>({...v,asset_name:e.target.value}))} style={INP}/>
            </div>
            <div>
              <label style={LBL}>Category</label>
              <select value={form.category} onChange={e=>{const ul=FA_USEFUL_LIVES[e.target.value]||60;setForm(v=>({...v,category:e.target.value,useful_life_months:String(ul)}));}} style={INP}>
                {FA_CATS.map(c=><option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label style={LBL}>Description (optional)</label>
              <input placeholder="Registration number, serial, etc." value={form.description} onChange={e=>setForm(v=>({...v,description:e.target.value}))} style={INP}/>
            </div>
            <div>
              <label style={LBL}>Location (optional)</label>
              <input placeholder="e.g. Head Office, Johannesburg" value={form.location} onChange={e=>setForm(v=>({...v,location:e.target.value}))} style={INP}/>
            </div>
          </div>

          <div style={{fontSize:11,fontWeight:700,color:C.accent,textTransform:"uppercase",letterSpacing:1,marginBottom:10}}>Cost &amp; Dates</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12,marginBottom:16}}>
            <div>
              <label style={LBL}>Purchase Date</label>
              <input type="date" value={form.purchase_date} onChange={e=>setForm(v=>({...v,purchase_date:e.target.value}))} style={INP}/>
            </div>
            <div>
              <label style={LBL}>Cost (ZAR)</label>
              <input type="number" placeholder="0.00" value={form.cost} onChange={e=>setForm(v=>({...v,cost:e.target.value}))} style={INP}/>
            </div>
            <div>
              <label style={LBL}>Residual Value (ZAR)</label>
              <input type="number" placeholder="0.00" value={form.residual_value} onChange={e=>setForm(v=>({...v,residual_value:e.target.value}))} style={INP}/>
            </div>
          </div>

          <div style={{fontSize:11,fontWeight:700,color:C.accent,textTransform:"uppercase",letterSpacing:1,marginBottom:10}}>Depreciation</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12,marginBottom:16}}>
            <div>
              <label style={LBL}>Method</label>
              <select value={form.depreciation_method} onChange={e=>setForm(v=>({...v,depreciation_method:e.target.value}))} style={INP}>
                <option value="straight_line">Straight-Line</option>
                <option value="diminishing_balance">Diminishing Balance</option>
              </select>
            </div>
            {form.depreciation_method === "straight_line" ? (
              <div>
                <label style={LBL}>Useful Life (months)</label>
                <input type="number" placeholder="60" value={form.useful_life_months} onChange={e=>setForm(v=>({...v,useful_life_months:e.target.value}))} style={INP}/>
              </div>
            ) : (
              <div>
                <label style={LBL}>Annual Rate (e.g. 0.20 = 20%)</label>
                <input type="number" step="0.01" placeholder="0.20" value={form.depreciation_rate} onChange={e=>setForm(v=>({...v,depreciation_rate:e.target.value}))} style={INP}/>
              </div>
            )}
            <div style={{alignSelf:"end",paddingBottom:2}}>
              {form.cost && form.depreciation_method === "straight_line" && (
                <div style={{background:C.accentLt,borderRadius:8,padding:"10px 12px",fontSize:12}}>
                  <div style={{color:C.inkMid}}>Monthly charge</div>
                  <div style={{fontWeight:700,color:C.accent}}>{fmt((+form.cost - (+form.residual_value||0)) / Math.max(1,+form.useful_life_months))}</div>
                </div>
              )}
            </div>
          </div>

          <div style={{fontSize:11,fontWeight:700,color:C.accent,textTransform:"uppercase",letterSpacing:1,marginBottom:10}}>SARS Tax Depreciation (IN47)</div>
          <div style={{marginBottom:6}}>
            <label style={LBL}>SARS Wear &amp; Tear Category (optional — for deferred tax)</label>
            <select value={form.sars_category} onChange={e=>setForm(v=>({...v,sars_category:e.target.value}))} style={INP}>
              <option value="">— None assigned —</option>
              {SARS_WT_CATS.map(c=>{
                const info = SARS_WT[c];
                return <option key={c} value={c}>{c} — {info.years}yr (s{info.section})</option>;
              })}
            </select>
          </div>
          {/* SARS preview strip */}
          {form.sars_category && form.cost && (() => {
            const tb = sarsCalcTaxBase(+form.cost, form.purchase_date, form.sars_category);
            if (!tb) return null;
            const accountingCV  = Math.max(0, +form.cost - (((+form.cost - (+form.residual_value||0)) / Math.max(1,+form.useful_life_months)) * 0)); // at acquisition CV = cost
            const tempDiff = +form.cost - tb.taxBase; // at acquisition tax base lags after month 1
            const dtAmt    = Math.abs(tb.taxBase - +form.cost) * SA_CIT;
            const wt       = SARS_WT[form.sars_category];
            return (
              <div style={{background:"#f0f7ff",border:"1px solid #b3d4f530",borderRadius:10,padding:"12px 16px",marginBottom:12,fontSize:12}}>
                <div style={{fontWeight:700,color:C.blue,marginBottom:6}}>SARS {wt.section} — {tb.years}-year write-off</div>
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10}}>
                  <div><span style={{color:C.inkMid}}>Monthly SARS allowance</span><br/><strong>{fmt(tb.monthlyAllowance)}/mo</strong></div>
                  <div><span style={{color:C.inkMid}}>Annual SARS allowance</span><br/><strong>{fmt(tb.monthlyAllowance*12)}/yr</strong></div>
                  <div><span style={{color:C.inkMid}}>Full deduction over</span><br/><strong>{tb.years} year{tb.years>1?"s":""}</strong></div>
                </div>
                {tb.note && <div style={{marginTop:8,fontSize:11,color:"#7c5c00",background:"#fff8e1",borderRadius:6,padding:"6px 10px"}}>⚠️ {tb.note}</div>}
              </div>
            );
          })()}

          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:20,padding:"12px",background:C.accentLt,borderRadius:10}}>
            <input type="checkbox" checked={form.post_journal} onChange={e=>setForm(v=>({...v,post_journal:e.target.checked}))} style={{width:18,height:18}}/>
            <span style={{fontSize:14,color:C.ink}}>Post acquisition journal entry (DR Fixed Assets / CR Bank)</span>
          </div>

          <div style={{display:"flex",gap:10}}>
            <button onClick={()=>setSection("register")} style={{flex:1,background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"11px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
            <button onClick={handleAdd} disabled={saving} style={{flex:2,background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"11px",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit",opacity:saving?0.6:1}}>
              {saving ? "Saving..." : "Add to Asset Register"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── INVENTORY ─────────────────────────────────────────────────────────────────
function Inventory() {
  const [items,    setItems]   = useState([]);
  const [summary,  setSummary] = useState(null);
  const [showNew,  setShowNew] = useState(false);
  const [editItem, setEditItem]= useState(null);
  const [adjItem,  setAdjItem] = useState(null);
  const [adjQty,   setAdjQty]  = useState("");
  const [adjReason,setAdjReason]=useState("");
  const [search,      setSearch]     = useState("");
  const [stockFilter, setStockFilter]= useState("all"); // all | low | ok
  const [loading,  setLoading] = useState(true);
  const [form, setForm] = useState({name:"",sku:"",category:"",description:"",unit_cost:"",unit_price:"",quantity_on_hand:"",reorder_level:"5",unit_of_measure:"Unit"});

  useEffect(()=>{ load(); },[]);

  const load = async () => {
    setLoading(true);
    try {
      const [it, sm] = await Promise.all([
        api("/inventory/").catch(()=>[]),
        api("/inventory/summary").catch(()=>null),
      ]);
      setItems(it); setSummary(sm);
    } finally { setLoading(false); }
  };

  const handleCreate = async () => {
    try {
      await api("/inventory/",{method:"POST",body:JSON.stringify({...form,unit_cost:+form.unit_cost||0,unit_price:+form.unit_price||0,quantity_on_hand:+form.quantity_on_hand||0,reorder_level:+form.reorder_level||5})});
      setShowNew(false);
      setForm({name:"",sku:"",category:"",description:"",unit_cost:"",unit_price:"",quantity_on_hand:"",reorder_level:"5",unit_of_measure:"Unit"});
      load();
    } catch(e) { alert("Failed: "+e.message); }
  };

  const handleUpdate = async () => {
    try {
      await api(`/inventory/${editItem.id}`,{method:"PUT",body:JSON.stringify({...editItem,unit_cost:+editItem.unit_cost||0,unit_price:+editItem.unit_price||0,quantity_on_hand:+editItem.quantity_on_hand||0,reorder_level:+editItem.reorder_level||5})});
      setEditItem(null); load();
    } catch(e) { alert("Failed: "+e.message); }
  };

  const handleAdjust = async () => {
    try {
      await api(`/inventory/${adjItem.id}/adjust`,{method:"POST",body:JSON.stringify({quantity:+adjQty,reason:adjReason})});
      setAdjItem(null); setAdjQty(""); setAdjReason(""); load();
    } catch(e) { alert("Failed: "+e.message); }
  };

  const handleDelete = async (id,name) => {
    if(!window.confirm(`Delete "${name}"?`)) return;
    await api(`/inventory/${id}`,{method:"DELETE"});
    load();
  };

  const filtered = items
    .filter(i=>(i.name||"").toLowerCase().includes(search.toLowerCase())||(i.sku||"").toLowerCase().includes(search.toLowerCase())||(i.category||"").toLowerCase().includes(search.toLowerCase()))
    .filter(i => {
      if (stockFilter === "low") return i.quantity_on_hand <= i.reorder_level;
      if (stockFilter === "ok")  return i.quantity_on_hand >  i.reorder_level;
      return true;
    });
  const is = {width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"};
  const lb = (t) => <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{t}</label>;

  return (
    <div>
      <SectionHeader title="Inventory" sub="Track stock levels, costs and reorder alerts" action="+ Add Item" onAction={()=>setShowNew(true)}/>

      {/* Summary KPIs — clickable to filter table */}
      <div style={{display:"flex",gap:12,marginBottom:24,flexWrap:"wrap"}}>
        <KPI label="Total Items"        value={summary?.total_items||items.length}  color={C.blue}  icon="📦"
          sub={stockFilter==="all"?"All items":"Tap to show all"}
          onClick={()=>setStockFilter("all")}/>
        <KPI label="Stock Value (Cost)" value={fmt(summary?.total_cost_value||0)}   color={C.ink}   icon="💰"
          sub="Total cost of stock on hand"/>
        <KPI label="Retail Value"       value={fmt(summary?.total_retail_value||0)} color={C.green} icon="🏷️"
          sub="Total selling value of stock"/>
        <KPI label="OK Stock"           value={items.filter(i=>i.quantity_on_hand>i.reorder_level).length} color={C.green} icon="✅"
          sub={stockFilter==="ok"?"Filtering ▼":"Tap to filter"}
          onClick={()=>setStockFilter(f=>f==="ok"?"all":"ok")}/>
        <KPI label="Low Stock Alerts"   value={summary?.low_stock_count||items.filter(i=>i.quantity_on_hand<=i.reorder_level).length} color={C.red} icon="⚠️"
          sub={stockFilter==="low"?"Filtering ▼":"Tap to filter"}
          onClick={()=>setStockFilter(f=>f==="low"?"all":"low")}/>
      </div>
      {/* Active filter indicator */}
      {stockFilter !== "all" && (
        <div style={{background:stockFilter==="low"?C.redLt:C.greenLt,border:`1px solid ${stockFilter==="low"?C.red:C.green}30`,borderRadius:8,padding:"8px 14px",marginBottom:16,display:"flex",justifyContent:"space-between",alignItems:"center",fontSize:12}}>
          <span style={{color:stockFilter==="low"?C.red:C.green,fontWeight:600}}>
            {stockFilter==="low"?"⚠️ Showing low-stock items only":"✅ Showing in-stock items only"}
          </span>
          <button onClick={()=>setStockFilter("all")} style={{background:"none",border:"none",cursor:"pointer",color:C.inkMid,fontSize:12,fontFamily:"inherit"}}>✕ Clear filter</button>
        </div>
      )}

      {/* Low stock banner */}
      {summary?.low_stock_items?.length > 0 && (
        <div style={{background:C.redLt,border:`1px solid ${C.red}30`,borderRadius:12,padding:"12px 18px",marginBottom:20}}>
          <div style={{fontSize:13,fontWeight:700,color:C.red,marginBottom:6}}>⚠️ Low Stock — Reorder needed</div>
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            {summary.low_stock_items.map(i=>(
              <span key={i.id} style={{background:C.surface,border:`1px solid ${C.red}30`,borderRadius:8,padding:"4px 10px",fontSize:12,color:C.red}}>{i.name} — {i.quantity_on_hand} {i.unit_of_measure} left</span>
            ))}
          </div>
        </div>
      )}

      {/* Add item form */}
      {showNew && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:24,marginBottom:20}}>
          <h3 style={{fontFamily:"serif",margin:"0 0 16px",color:C.ink}}>New Inventory Item</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12,marginBottom:12}}>
            <div>{lb("Item Name")}<input placeholder="Widget A" value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} style={is}/></div>
            <div>{lb("SKU / Code")}<input placeholder="WGT-001" value={form.sku} onChange={e=>setForm(f=>({...f,sku:e.target.value}))} style={is}/></div>
            <div>{lb("Category")}<input placeholder="Electronics" value={form.category} onChange={e=>setForm(f=>({...f,category:e.target.value}))} style={is}/></div>
            <div>{lb("Cost Price (ZAR)")}<input type="number" placeholder="100" value={form.unit_cost} onChange={e=>setForm(f=>({...f,unit_cost:e.target.value}))} style={is}/></div>
            <div>{lb("Selling Price (ZAR)")}<input type="number" placeholder="150" value={form.unit_price} onChange={e=>setForm(f=>({...f,unit_price:e.target.value}))} style={is}/></div>
            <div>{lb("Unit of Measure")}<select value={form.unit_of_measure} onChange={e=>setForm(f=>({...f,unit_of_measure:e.target.value}))} style={is}>{["Unit","Each","Box","Kg","Litre","Metre","Hour"].map(u=><option key={u}>{u}</option>)}</select></div>
            <div>{lb("Opening Stock")}<input type="number" placeholder="0" value={form.quantity_on_hand} onChange={e=>setForm(f=>({...f,quantity_on_hand:e.target.value}))} style={is}/></div>
            <div>{lb("Reorder Level")}<input type="number" placeholder="5" value={form.reorder_level} onChange={e=>setForm(f=>({...f,reorder_level:e.target.value}))} style={is}/></div>
            <div>{lb("Description")}<input placeholder="Optional description" value={form.description} onChange={e=>setForm(f=>({...f,description:e.target.value}))} style={is}/></div>
          </div>
          {form.unit_cost && form.unit_price && (
            <div style={{background:C.greenLt,borderRadius:8,padding:"8px 14px",marginBottom:12,fontSize:12,color:C.green}}>
              Margin: {fmt(+form.unit_price - +form.unit_cost)} ({form.unit_cost>0?Math.round(((+form.unit_price - +form.unit_cost)/+form.unit_cost)*100):0}%)
            </div>
          )}
          <div style={{display:"flex",gap:8}}>
            <button onClick={handleCreate} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Add Item</button>
            <button onClick={()=>setShowNew(false)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
          </div>
        </div>
      )}

      {/* Edit modal */}
      {editItem && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center",padding:20}} onClick={()=>setEditItem(null)}>
          <div style={{background:C.surface,borderRadius:20,padding:32,width:580,maxHeight:"90vh",overflow:"auto"}} onClick={e=>e.stopPropagation()}>
            <h3 style={{fontFamily:"serif",fontSize:20,color:C.ink,margin:"0 0 20px"}}>Edit Item — {editItem.name}</h3>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:16}}>
              {[{l:"Item Name",k:"name"},{l:"SKU",k:"sku"},{l:"Category",k:"category"},{l:"Cost Price",k:"unit_cost",t:"number"},{l:"Selling Price",k:"unit_price",t:"number"},{l:"Stock on Hand",k:"quantity_on_hand",t:"number"},{l:"Reorder Level",k:"reorder_level",t:"number"}].map(f=>(
                <div key={f.k}>{lb(f.l)}<input type={f.t||"text"} value={editItem[f.k]||""} onChange={e=>setEditItem(i=>({...i,[f.k]:e.target.value}))} style={is}/></div>
              ))}
            </div>
            <div style={{display:"flex",gap:8}}>
              <button onClick={handleUpdate} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 24px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Save</button>
              <button onClick={()=>setEditItem(null)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Stock adjustment modal */}
      {adjItem && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center"}} onClick={()=>setAdjItem(null)}>
          <div style={{background:C.surface,borderRadius:20,padding:32,width:420}} onClick={e=>e.stopPropagation()}>
            <h3 style={{fontFamily:"serif",fontSize:20,color:C.ink,margin:"0 0 6px"}}>Adjust Stock — {adjItem.name}</h3>
            <p style={{fontSize:12,color:C.inkMid,marginBottom:20}}>Current: {adjItem.quantity_on_hand} {adjItem.unit_of_measure}</p>
            <div style={{marginBottom:14}}>{lb("Quantity (+ receive / − issue)")}<input type="number" placeholder="e.g. 10 or -5" value={adjQty} onChange={e=>setAdjQty(e.target.value)} style={is}/></div>
            <div style={{marginBottom:20}}>{lb("Reason")}<input placeholder="Purchase order, sale, write-off..." value={adjReason} onChange={e=>setAdjReason(e.target.value)} style={is}/></div>
            {adjQty && <div style={{background:C.greenLt,borderRadius:8,padding:"8px 14px",marginBottom:14,fontSize:12,color:C.green}}>New stock: {Math.max(0,adjItem.quantity_on_hand + +adjQty)} {adjItem.unit_of_measure}</div>}
            <div style={{display:"flex",gap:8}}>
              <button onClick={handleAdjust} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Apply</button>
              <button onClick={()=>setAdjItem(null)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Search */}
      <div style={{marginBottom:16}}>
        <input placeholder="Search by name, SKU or category..." value={search} onChange={e=>setSearch(e.target.value)} style={{...is,maxWidth:360}}/>
      </div>

      {/* Table */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
        {loading ? <div style={{padding:40,textAlign:"center",color:C.inkMid}}>Loading...</div> :
        filtered.length===0 ? <div style={{padding:40,textAlign:"center",color:C.inkMid}}>No items yet. Add your first inventory item.</div> : (
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
            <thead>
              <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
                {["SKU","Name","Category","Cost","Price","Margin","Stock","Value","Status","Actions"].map(h=><th key={h} style={{textAlign:"left",padding:"11px 14px",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {filtered.map(item=>{
                const margin = item.unit_price>0?Math.round(((item.unit_price-item.unit_cost)/item.unit_price)*100):0;
                const isLow  = item.quantity_on_hand <= item.reorder_level;
                return (
                  <tr key={item.id} style={{borderBottom:`1px solid ${C.border}20`,background:isLow?"#FFF5F520":"transparent"}}>
                    <td style={{padding:"12px 14px",fontFamily:"monospace",color:C.inkMid,fontSize:11}}>{item.sku||"—"}</td>
                    <td style={{padding:"12px 14px",fontWeight:600,color:C.ink}}>{item.name}</td>
                    <td style={{padding:"12px 14px"}}>{item.category?<Badge label={item.category} color={C.blue} bg={C.blueLt}/>:"—"}</td>
                    <td style={{padding:"12px 14px",color:C.inkMid}}>{fmt(item.unit_cost)}</td>
                    <td style={{padding:"12px 14px",fontWeight:600}}>{fmt(item.unit_price)}</td>
                    <td style={{padding:"12px 14px",color:margin>=30?C.green:margin>=15?C.gold:C.red,fontWeight:600}}>{margin}%</td>
                    <td style={{padding:"12px 14px",fontWeight:700,color:isLow?C.red:C.ink}}>{item.quantity_on_hand} {item.unit_of_measure}</td>
                    <td style={{padding:"12px 14px",color:C.green,fontWeight:600}}>{fmt(item.stock_value)}</td>
                    <td style={{padding:"12px 14px"}}>{isLow?<Badge label="Low Stock" color={C.red} bg={C.redLt}/>:<Badge label="OK" color={C.green} bg={C.greenLt}/>}</td>
                    <td style={{padding:"12px 14px"}}>
                      <div style={{display:"flex",gap:5}}>
                        <button onClick={()=>setAdjItem(item)} style={{background:C.goldLt,color:C.gold,border:"none",borderRadius:6,padding:"4px 8px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Adjust</button>
                        <button onClick={()=>setEditItem({...item})} style={{background:C.blueLt,color:C.blue,border:"none",borderRadius:6,padding:"4px 8px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Edit</button>
                        <button onClick={()=>handleDelete(item.id,item.name)} style={{background:C.redLt,color:C.red,border:"none",borderRadius:6,padding:"4px 8px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Del</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── DEVELOPER / API ACCESS ────────────────────────────────────────────────────
function Developer() {
  const [keys,     setKeys]     = useState([]);
  const [usage,    setUsage]    = useState(null);
  const [showNew,  setShowNew]  = useState(false);
  const [newKey,   setNewKey]   = useState(null);   // revealed once on creation
  const [form,     setForm]     = useState({name:"", scopes:["read"]});
  const [loading,  setLoading]  = useState(true);
  const [activeDoc,setActiveDoc]= useState("overview");
  const BASE = "https://zuzan-backend.onrender.com";

  useEffect(()=>{ loadKeys(); },[]);

  const loadKeys = async () => {
    setLoading(true);
    try {
      const [k, u] = await Promise.all([
        api("/api-keys/").catch(()=>[]),
        api("/api-keys/usage").catch(()=>null),
      ]);
      setKeys(k); setUsage(u);
    } finally { setLoading(false); }
  };

  const handleCreate = async () => {
    try {
      const res = await api("/api-keys/",{method:"POST",body:JSON.stringify({name:form.name,scopes:form.scopes})});
      setNewKey(res);
      setShowNew(false);
      setForm({name:"",scopes:["read"]});
      loadKeys();
    } catch(e) { alert("Failed to create key: " + e.message); }
  };

  const handleRevoke = async (id, name) => {
    if (!window.confirm(`Revoke "${name}"? This cannot be undone.`)) return;
    await api(`/api-keys/${id}`,{method:"DELETE"});
    loadKeys();
  };

  const toggleScope = (s) => setForm(f=>({...f,scopes:f.scopes.includes(s)?f.scopes.filter(x=>x!==s):[...f.scopes,s]}));

  const DOCS = {
    overview: {
      title:"Overview",
      content: `# ZuZan API

The ZuZan REST API gives you programmatic access to your financial data.

**Base URL**
\`\`\`
${BASE}/v1
\`\`\`

**Authentication**
Pass your API key in the request header:
\`\`\`
X-API-Key: zuzan_xxxxxxxxxxxxxxxx
\`\`\`

**Rate Limits**
- 1,000 requests per key per day
- Responses are JSON

**Scopes**
| Scope | Access |
|---|---|
| read | Invoices, expenses, summary |
| write | Create/update records |
| payroll | Employee and payroll data |
| reports | Financial reports |`,
    },
    invoices: {
      title:"Invoices",
      content:`# GET /v1/invoices

List all invoices for your company.

**Request**
\`\`\`bash
curl ${BASE}/v1/invoices \\
  -H "X-API-Key: YOUR_API_KEY"
\`\`\`

**Response**
\`\`\`json
[
  {
    "id": 1,
    "invoice_number": "INV-001",
    "client_name": "Acme Pty Ltd",
    "amount": 50000.00,
    "status": "paid",
    "issue_date": "2025-04-01",
    "due_date": "2025-05-01"
  }
]
\`\`\`

**Scopes required:** \`read\``,
    },
    expenses: {
      title:"Expenses",
      content:`# GET /v1/expenses

List all expenses.

**Request**
\`\`\`bash
curl ${BASE}/v1/expenses \\
  -H "X-API-Key: YOUR_API_KEY"
\`\`\`

**Response**
\`\`\`json
[
  {
    "id": 1,
    "vendor": "Eskom",
    "description": "Electricity",
    "amount": 3200.00,
    "category": "6220 - Electricity and Water",
    "date": "2025-04-02"
  }
]
\`\`\`

**Scopes required:** \`read\``,
    },
    employees: {
      title:"Employees",
      content:`# GET /v1/employees

List active employees (requires payroll scope).

**Request**
\`\`\`bash
curl ${BASE}/v1/employees \\
  -H "X-API-Key: YOUR_API_KEY"
\`\`\`

**Response**
\`\`\`json
[
  {
    "id": 1,
    "name": "Sipho Dlamini",
    "position": "Developer",
    "department": "Tech",
    "gross_salary": 45000.00
  }
]
\`\`\`

**Scopes required:** \`payroll\``,
    },
    summary: {
      title:"Summary",
      content:`# GET /v1/summary

Get a financial summary of your company.

**Request**
\`\`\`bash
curl ${BASE}/v1/summary \\
  -H "X-API-Key: YOUR_API_KEY"
\`\`\`

**Response**
\`\`\`json
{
  "company": "Acme Pty Ltd",
  "total_revenue": 156500.00,
  "total_expenses": 24600.00,
  "outstanding": 96500.00,
  "net_profit": 131900.00
}
\`\`\`

**Scopes required:** \`read\``,
    },
  };

  const codeBlock = (text) => (
    <pre style={{background:"#1A1209",color:"#C8E6C9",borderRadius:10,padding:"14px 18px",fontSize:12,overflow:"auto",lineHeight:1.7,margin:"10px 0"}}>{text}</pre>
  );

  const renderDoc = (doc) => doc.content.split("\n").map((line,i)=>{
    if(line.startsWith("# ")) return <h2 key={i} style={{fontFamily:"serif",fontSize:20,color:C.ink,margin:"0 0 12px"}}>{line.slice(2)}</h2>;
    if(line.startsWith("## ")) return <h3 key={i} style={{fontFamily:"serif",fontSize:16,color:C.ink,margin:"16px 0 8px"}}>{line.slice(3)}</h3>;
    if(line.startsWith("**") && line.endsWith("**")) return <div key={i} style={{fontWeight:700,color:C.ink,margin:"12px 0 4px"}}>{line.slice(2,-2)}</div>;
    if(line.startsWith("```")) return null;
    if(line.startsWith("|")) return <div key={i} style={{fontFamily:"monospace",fontSize:12,color:C.inkMid,padding:"3px 0",borderBottom:`1px solid ${C.border}20`}}>{line}</div>;
    if(line.trim()==="") return <div key={i} style={{height:8}}/>;
    return <div key={i} style={{fontSize:13,color:C.inkMid,lineHeight:1.7}}>{line}</div>;
  });

  return (
    <div>
      <SectionHeader title="Developer API" sub="Integrate ZuZan with your systems"/>

      {/* Usage summary */}
      {usage && (
        <div style={{display:"flex",gap:12,marginBottom:24}}>
          <KPI label="Active Keys" value={usage.active_keys} color={C.blue} icon="🔑"/>
          <KPI label="Requests Today" value={usage.total_requests_today} sub={`of ${usage.rate_limit_per_key * usage.active_keys} limit`} color={C.green} icon="📡"/>
          <KPI label="Base URL" value="REST API" sub={BASE} color={C.accent} icon="🌐"/>
        </div>
      )}

      <div style={{display:"grid",gridTemplateColumns:"260px 1fr",gap:20}}>
        {/* Left: Keys + sidebar nav */}
        <div>
          {/* API Keys panel */}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:20,marginBottom:16}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:14}}>
              <div style={{fontSize:13,fontWeight:700,color:C.ink}}>API Keys</div>
              <button onClick={()=>setShowNew(true)} style={{background:C.accent,color:"#fff",border:"none",borderRadius:8,padding:"5px 12px",fontSize:11,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>+ New</button>
            </div>

            {showNew && (
              <div style={{background:C.bg,borderRadius:10,padding:14,marginBottom:14}}>
                <div style={{marginBottom:8}}>
                  <label style={{fontSize:10,fontWeight:600,color:C.inkMid,display:"block",marginBottom:4,textTransform:"uppercase"}}>Key Name</label>
                  <input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} placeholder="My Integration" style={{width:"100%",padding:"8px 10px",border:`1px solid ${C.border}`,borderRadius:6,fontSize:12,fontFamily:"inherit",background:C.surface,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
                </div>
                <div style={{marginBottom:10}}>
                  <label style={{fontSize:10,fontWeight:600,color:C.inkMid,display:"block",marginBottom:4,textTransform:"uppercase"}}>Scopes</label>
                  {["read","write","payroll","reports"].map(s=>(
                    <label key={s} style={{display:"flex",alignItems:"center",gap:6,marginBottom:4,cursor:"pointer",fontSize:12,color:C.inkMid}}>
                      <input type="checkbox" checked={form.scopes.includes(s)} onChange={()=>toggleScope(s)}/>
                      {s}
                    </label>
                  ))}
                </div>
                <div style={{display:"flex",gap:6}}>
                  <button onClick={handleCreate} style={{flex:1,background:C.accent,color:"#fff",border:"none",borderRadius:6,padding:"7px",fontSize:11,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Create</button>
                  <button onClick={()=>setShowNew(false)} style={{flex:1,background:"transparent",border:`1px solid ${C.border}`,borderRadius:6,padding:"7px",fontSize:11,cursor:"pointer",fontFamily:"inherit",color:C.inkMid}}>Cancel</button>
                </div>
              </div>
            )}

            {newKey && (
              <div style={{background:"#1A1209",borderRadius:10,padding:14,marginBottom:14}}>
                <div style={{fontSize:11,color:"#C8E6C9",fontWeight:700,marginBottom:6}}>⚠️ Copy now — shown once only</div>
                <div style={{fontFamily:"monospace",fontSize:10,color:"#80CBC4",wordBreak:"break-all",marginBottom:8}}>{newKey.key}</div>
                <button onClick={()=>{navigator.clipboard.writeText(newKey.key); alert("Copied!");}} style={{width:"100%",background:"#2A6B3C",color:"#fff",border:"none",borderRadius:6,padding:"6px",fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>Copy Key</button>
                <button onClick={()=>setNewKey(null)} style={{width:"100%",background:"transparent",color:"#aaa",border:"none",padding:"4px",fontSize:10,cursor:"pointer",fontFamily:"inherit",marginTop:4}}>Dismiss</button>
              </div>
            )}

            {loading ? <div style={{fontSize:12,color:C.inkMid,textAlign:"center",padding:16}}>Loading...</div> :
              keys.length===0 ? <div style={{fontSize:12,color:C.inkMid,textAlign:"center",padding:12}}>No keys yet</div> :
              keys.map(k=>(
                <div key={k.id} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"10px 0",borderBottom:`1px solid ${C.border}30`}}>
                  <div>
                    <div style={{fontSize:12,fontWeight:600,color:C.ink}}>{k.name}</div>
                    <div style={{fontSize:10,fontFamily:"monospace",color:C.inkMid}}>{k.key_prefix}...</div>
                    <div style={{fontSize:10,color:C.inkDim}}>{k.scopes} · {k.requests_today} req today</div>
                  </div>
                  <button onClick={()=>handleRevoke(k.id,k.name)} style={{background:C.redLt,color:C.red,border:"none",borderRadius:6,padding:"4px 8px",fontSize:10,cursor:"pointer",fontFamily:"inherit"}}>Revoke</button>
                </div>
              ))
            }
          </div>

          {/* Doc nav */}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:14}}>
            <div style={{fontSize:11,fontWeight:700,color:C.inkMid,textTransform:"uppercase",letterSpacing:0.5,marginBottom:10}}>Documentation</div>
            {Object.entries(DOCS).map(([key,doc])=>(
              <button key={key} onClick={()=>setActiveDoc(key)} style={{width:"100%",textAlign:"left",padding:"8px 10px",borderRadius:8,border:"none",background:activeDoc===key?C.accentLt:"transparent",color:activeDoc===key?C.accent:C.inkMid,fontSize:12,fontWeight:activeDoc===key?700:400,cursor:"pointer",fontFamily:"inherit",marginBottom:2}}>
                {doc.title}
              </button>
            ))}
          </div>
        </div>

        {/* Right: Documentation */}
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:28}}>
          {/* Code block sections */}
          {activeDoc==="overview" ? (
            <div>
              <h2 style={{fontFamily:"serif",fontSize:22,color:C.ink,margin:"0 0 16px"}}>ZuZan API Overview</h2>
              <p style={{fontSize:13,color:C.inkMid,lineHeight:1.7,marginBottom:16}}>The ZuZan REST API lets you integrate your financial data with other systems — accounting tools, dashboards, ERPs, or custom scripts.</p>
              <div style={{fontWeight:700,color:C.ink,marginBottom:6,fontSize:13}}>Base URL</div>
              {codeBlock(BASE + "/v1")}
              <div style={{fontWeight:700,color:C.ink,marginBottom:6,fontSize:13,marginTop:16}}>Authentication</div>
              {codeBlock(`curl ${BASE}/v1/summary \\\n  -H "X-API-Key: zuzan_your_api_key_here"`)}
              <div style={{fontWeight:700,color:C.ink,marginBottom:6,fontSize:13,marginTop:16}}>Available Endpoints</div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginTop:8}}>
                {[["GET /v1/summary","Financial overview",C.green],["GET /v1/invoices","List all invoices",C.blue],["GET /v1/expenses","List all expenses",C.accent],["GET /v1/employees","Employee list (payroll scope)",C.gold]].map(([ep,desc,c])=>(
                  <div key={ep} style={{background:C.bg,borderRadius:10,padding:"12px 14px"}}>
                    <div style={{fontFamily:"monospace",fontSize:11,color:c,fontWeight:700,marginBottom:4}}>{ep}</div>
                    <div style={{fontSize:11,color:C.inkMid}}>{desc}</div>
                  </div>
                ))}
              </div>
              <div style={{background:C.goldLt,border:`1px solid ${C.gold}30`,borderRadius:10,padding:"12px 16px",marginTop:20,fontSize:12,color:C.inkMid}}>
                <strong style={{color:C.ink}}>Rate Limits:</strong> 1,000 requests/day per key. Headers <code>X-RateLimit-Remaining</code> and <code>X-RateLimit-Reset</code> are included in every response.
              </div>
            </div>
          ) : (
            <div>{renderDoc(DOCS[activeDoc])}{activeDoc!=="overview" && codeBlock(DOCS[activeDoc].content.split("```bash\n")[1]?.split("\n```")[0]||"")}</div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── MOBILE DASHBOARD ──────────────────────────────────────────────────────────
function MobileDashboard({live, user, onNavigate}) {
  const d = live.dashboard;
  const totalRevenue  = d ? d.total_revenue  : MOCK_INVOICES.filter(i=>i.status==="paid").reduce((s,i)=>s+i.amount,0);
  const totalExpenses = d ? d.total_expenses : MOCK_EXPENSES.reduce((s,e)=>s+e.amount,0);
  const outstanding   = d ? d.total_outstanding : MOCK_INVOICES.filter(i=>i.status!=="paid").reduce((s,i)=>s+i.amount,0);
  const profit        = totalRevenue - totalExpenses;

  return (
    <div style={{padding:"0 0 100px"}}>
      {/* Header */}
      <div style={{background:`linear-gradient(135deg,${C.accent},#A03010)`,padding:"28px 20px 32px",marginBottom:-16}}>
        <div style={{fontSize:13,color:"rgba(255,255,255,0.7)",marginBottom:4}}>{(()=>{const h=new Date().getHours();return h<12?"Good morning":h<17?"Good afternoon":"Good evening";})()}</div>
        <div style={{fontFamily:"serif",fontSize:24,color:"#fff",fontWeight:800}}>{user?.companyName||"Your Company"}</div>
        <div style={{fontSize:12,color:"rgba(255,255,255,0.6)",marginTop:2}}>{new Date().toLocaleDateString("en-ZA",{weekday:"long",day:"numeric",month:"long"})}</div>
      </div>

      <div style={{padding:"0 16px"}}>
        {/* Main KPI card */}
        <div style={{background:C.surface,borderRadius:20,padding:20,boxShadow:"0 4px 24px rgba(0,0,0,0.08)",marginBottom:16}}>
          <div style={{fontSize:11,color:C.inkMid,fontWeight:600,textTransform:"uppercase",letterSpacing:0.5,marginBottom:8}}>Net Profit This Month</div>
          <div style={{fontFamily:"serif",fontSize:36,fontWeight:800,color:profit>=0?C.green:C.red}}>{fmt(profit)}</div>
          <div style={{display:"flex",gap:16,marginTop:12}}>
            <div><div style={{fontSize:10,color:C.inkMid}}>Revenue</div><div style={{fontSize:15,fontWeight:700,color:C.green}}>{fmt(totalRevenue)}</div></div>
            <div style={{width:1,background:C.border}}/>
            <div><div style={{fontSize:10,color:C.inkMid}}>Expenses</div><div style={{fontSize:15,fontWeight:700,color:C.red}}>{fmt(totalExpenses)}</div></div>
            <div style={{width:1,background:C.border}}/>
            <div><div style={{fontSize:10,color:C.inkMid}}>Outstanding</div><div style={{fontSize:15,fontWeight:700,color:C.gold}}>{fmt(outstanding)}</div></div>
          </div>
        </div>

        {/* Quick actions */}
        <div style={{fontSize:13,fontWeight:700,color:C.ink,marginBottom:10}}>Quick Actions</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginBottom:20}}>
          {[
            {label:"New Invoice",   icon:"🧾",tab:"invoicing", color:C.accent},
            {label:"Add Expense",   icon:"💳",tab:"expenses",  color:C.blue},
            {label:"View Reports",  icon:"📊",tab:"reports",   color:C.green},
            {label:"Run Payroll",   icon:"👥",tab:"payroll",   color:C.gold},
          ].map(a=>(
            <button key={a.tab} onClick={()=>onNavigate(a.tab)}
              style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:"16px 14px",display:"flex",alignItems:"center",gap:10,cursor:"pointer",fontFamily:"inherit",textAlign:"left",boxShadow:"0 2px 8px rgba(0,0,0,0.04)"}}>
              <div style={{width:40,height:40,borderRadius:12,background:a.color+"15",display:"flex",alignItems:"center",justifyContent:"center",fontSize:20}}>{a.icon}</div>
              <span style={{fontSize:13,fontWeight:600,color:C.ink}}>{a.label}</span>
            </button>
          ))}
        </div>

        {/* Recent invoices */}
        <div style={{fontSize:13,fontWeight:700,color:C.ink,marginBottom:10}}>Recent Invoices</div>
        {MOCK_INVOICES.slice(0,4).map(inv=>{
          const statusColor = inv.status==="paid"?C.green:inv.status==="overdue"?C.red:C.gold;
          const statusBg    = inv.status==="paid"?C.greenLt:inv.status==="overdue"?C.redLt:C.goldLt;
          return (
            <div key={inv.id} style={{background:C.surface,borderRadius:14,padding:"14px 16px",marginBottom:10,boxShadow:"0 2px 8px rgba(0,0,0,0.04)"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
                <div>
                  <div style={{fontSize:14,fontWeight:700,color:C.ink}}>{inv.client}</div>
                  <div style={{fontSize:11,color:C.inkMid,marginTop:2}}>{inv.id} · Due {fmtDate(inv.due)}</div>
                </div>
                <div style={{textAlign:"right"}}>
                  <div style={{fontSize:15,fontWeight:800,color:C.ink}}>{fmt(inv.amount)}</div>
                  <div style={{marginTop:4,fontSize:10,fontWeight:700,color:statusColor,background:statusBg,padding:"2px 8px",borderRadius:10,textTransform:"uppercase"}}>{inv.status}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── MOBILE SHELL ──────────────────────────────────────────────────────────────
function MobileApp({user, onLogout, onUserUpdate, live, docTemplate, onTemplateChange}) {
  const [tab, setTab] = useState("home");
  const [moreOpen, setMoreOpen] = useState(false);

  const BOTTOM_TABS = [
    {id:"home",      label:"Home",     icon:"🏠"},
    {id:"invoicing", label:"Invoices", icon:"🧾"},
    {id:"expenses",  label:"Expenses", icon:"💳"},
    {id:"payroll",   label:"Payroll",  icon:"👥"},
    {id:"more",      label:"More",     icon:"⋯"},
  ];

  const MORE_ITEMS = [
    {id:"quotes",          label:"Quotes",      icon:"📝"},
    {id:"budgeting",       label:"Budgeting",   icon:"🎯"},
    {id:"customers",       label:"Customers",   icon:"👥"},
    {id:"suppliers",       label:"Suppliers",   icon:"🏭"},
    {id:"purchase_orders", label:"Purchase Orders", icon:"📋"},
    {id:"reports",         label:"Reports",     icon:"📊"},
    {id:"inventory",       label:"Inventory",   icon:"📦"},
    {id:"fixed_assets",   label:"Fixed Assets", icon:"🏭"},
    {id:"bankimport",      label:"Bank",        icon:"🏦"},
    {id:"debtors",         label:"Debtors",     icon:"📥"},
    {id:"creditors",       label:"Creditors",   icon:"📤"},
    {id:"coa",             label:"Accounts",    icon:"📒"},
    {id:"settings",        label:"Settings",    icon:"⚙️"},
  ];

  const navigate = (id) => { setTab(id); setMoreOpen(false); };

  const screens = {
    home:       <MobileDashboard live={live} user={user} onNavigate={navigate}/>,
    invoicing:  <div style={{padding:"16px 16px 100px"}}><Invoicing  live={live} user={user} docTemplate={docTemplate}/></div>,
    expenses:   <div style={{padding:"16px 16px 100px"}}><Expenses   live={live}/></div>,
    payroll:    <div style={{padding:"16px 16px 100px"}}><Payroll    live={live} user={user}/></div>,
    quotes:     <div style={{padding:"16px 16px 100px"}}><Quotes     live={live} user={user} onNavigate={navigate} docTemplate={docTemplate}/></div>,
    budgeting:  <div style={{padding:"16px 16px 100px"}}><Budgeting  live={live}/></div>,
    reports:    <div style={{padding:"16px 16px 100px"}}><Reports    live={live}/></div>,
    inventory:       <div style={{padding:"16px 16px 100px"}}><Inventory/></div>,
    fixed_assets:    <div style={{padding:"16px 16px 100px"}}><FixedAssets/></div>,
    customers:       <div style={{padding:"16px 16px 100px"}}><Customers/></div>,
    suppliers:       <div style={{padding:"16px 16px 100px"}}><Suppliers/></div>,
    purchase_orders: <div style={{padding:"16px 16px 100px"}}><PurchaseOrders/></div>,
    bankimport:      <div style={{padding:"16px 16px 100px"}}><BankImport live={live} onNavigate={navigate}/></div>,
    debtors:    <div style={{padding:"16px 16px 100px"}}><Debtors    live={live}/></div>,
    creditors:  <div style={{padding:"16px 16px 100px"}}><Creditors  live={live}/></div>,
    coa:        <div style={{padding:"16px 16px 100px"}}><ChartOfAccounts/></div>,
    settings:   <div style={{padding:"16px 16px 100px"}}><AppSettings user={user} onLogout={onLogout} onUserUpdate={onUserUpdate} docTemplate={docTemplate} onTemplateChange={onTemplateChange}/></div>,
  };

  const activeLabel = [...BOTTOM_TABS,...MORE_ITEMS].find(t=>t.id===tab)?.label || "ZuZan";

  return (
    <div style={{fontFamily:"sans-serif",background:C.bg,minHeight:"100vh",minHeight:"100dvh"}}>
      <style>{`*{box-sizing:border-box;margin:0;padding:0;}button:active{opacity:0.7;}`}</style>

      {/* Top bar */}
      <div style={{position:"fixed",top:0,left:0,right:0,height:56,background:C.surface,borderBottom:`1px solid ${C.border}`,display:"flex",alignItems:"center",justifyContent:"space-between",padding:"0 16px",zIndex:50}}>
        <div style={{fontFamily:"serif",fontSize:22,fontWeight:800,color:C.ink}}><span style={{color:C.accent}}>Zu</span>Zan</div>
        <div style={{fontSize:14,fontWeight:600,color:C.ink}}>{activeLabel}</div>
        <button onClick={()=>navigate("settings")} style={{background:"none",border:"none",fontSize:22,cursor:"pointer"}}>{user?.firstName?.[0]||"👤"}</button>
      </div>

      {/* Content */}
      <div style={{paddingTop:56,minHeight:"100vh",overflowY:"auto"}}>
        {screens[tab] || screens.home}
      </div>

      {/* More drawer */}
      {moreOpen && (
        <>
          <div onClick={()=>setMoreOpen(false)} style={{position:"fixed",inset:0,background:"#00000050",zIndex:60}}/>
          <div style={{position:"fixed",bottom:0,left:0,right:0,background:C.surface,borderRadius:"24px 24px 0 0",padding:"12px 0 40px",zIndex:70}}>
            <div style={{width:40,height:4,background:C.border,borderRadius:2,margin:"0 auto 20px"}}/>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:4,padding:"0 16px"}}>
              {MORE_ITEMS.map(item=>(
                <button key={item.id} onClick={()=>navigate(item.id)}
                  style={{background:"transparent",border:"none",cursor:"pointer",fontFamily:"inherit",padding:"12px 4px",display:"flex",flexDirection:"column",alignItems:"center",gap:6,borderRadius:12,background:tab===item.id?C.accentLt:"transparent"}}>
                  <span style={{fontSize:26}}>{item.icon}</span>
                  <span style={{fontSize:10,color:tab===item.id?C.accent:C.inkMid,fontWeight:tab===item.id?700:400}}>{item.label}</span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Bottom navigation */}
      <div style={{position:"fixed",bottom:0,left:0,right:0,background:C.surface,borderTop:`1px solid ${C.border}`,display:"flex",paddingBottom:"env(safe-area-inset-bottom)",zIndex:50}}>
        {BOTTOM_TABS.map(t=>{
          const active = t.id==="more" ? moreOpen : tab===t.id;
          return (
            <button key={t.id} onClick={()=>{ if(t.id==="more"){setMoreOpen(o=>!o);}else{setTab(t.id);setMoreOpen(false);}}}
              style={{flex:1,background:"none",border:"none",cursor:"pointer",padding:"10px 4px 8px",display:"flex",flexDirection:"column",alignItems:"center",gap:3,fontFamily:"inherit"}}>
              <span style={{fontSize:22}}>{t.icon}</span>
              <span style={{fontSize:10,color:active?C.accent:C.inkMid,fontWeight:active?700:400}}>{t.label}</span>
              {active && t.id!=="more" && <div style={{width:4,height:4,borderRadius:"50%",background:C.accent}}/>}
            </button>
          );
        })}
      </div>
      <AIAssistant tab={tab}/>
    </div>
  );
}

// ── MAIN APP ──────────────────────────────────────────────────────────────────
function ZuZanApp({user, onLogout, onUserUpdate}) {
  const live = useLiveData();
  const [tab, setTab] = useState("dashboard");
  const [docTemplate, setDocTemplate] = useState(() => {
    try { const s = localStorage.getItem("zuzan_doc_template"); return s ? {...DEFAULT_DOC_TEMPLATE, ...JSON.parse(s)} : DEFAULT_DOC_TEMPLATE; } catch { return DEFAULT_DOC_TEMPLATE; }
  });
  const handleTemplateChange = (tmpl) => {
    setDocTemplate(tmpl);
    try { localStorage.setItem("zuzan_doc_template", JSON.stringify(tmpl)); } catch {}
  };
  const [expanded, setExpanded] = useState({sales: true, procurement: false, banking: false});
  const isMobile = typeof window !== "undefined" && window.innerWidth <= 768;

  const TABS = [
    {id:"dashboard",  label:"Dashboard",   icon:"🏠"},
    {id:"sales",      label:"Sales",       icon:"💼", children:[
      {id:"invoicing",       label:"Invoices",        icon:"🧾"},
      {id:"quotes",          label:"Quotes",          icon:"📝"},
      {id:"customers",       label:"Customers",       icon:"👥"},
    ]},
    {id:"procurement", label:"Procurement", icon:"🛒", children:[
      {id:"purchase_orders", label:"Purchase Orders", icon:"📋"},
      {id:"suppliers",       label:"Suppliers",       icon:"🏭"},
    ]},
    {id:"expenses",   label:"Expenses",    icon:"💳"},
    {id:"payroll",    label:"Payroll",     icon:"👥"},
    {id:"reports",    label:"Reports",     icon:"📊"},
    {id:"budgeting",  label:"Budgeting",   icon:"🎯"},
    {id:"debtors",    label:"Debtors",     icon:"📥"},
    {id:"creditors",  label:"Creditors",   icon:"📤"},
    {id:"coa",        label:"Accounts",    icon:"📒"},
    {id:"inventory",    label:"Inventory",   icon:"📦"},
    {id:"fixed_assets", label:"Fixed Assets", icon:"🏭"},
    {id:"banking",    label:"Banking",     icon:"🏦", children:[
      {id:"bankimport", label:"Manual Update",   icon:"📄"},
      {id:"bankfeeds",  label:"Connect to Bank", icon:"🔗"},
    ]},
    {id:"settings",   label:"Settings",    icon:"⚙️"},
  ];

  const toggleGroup = (id) => setExpanded(e => ({...e, [id]: !e[id]}));

  const navBtn = (t, isChild=false) => {
    const active = tab === t.id;
    return (
      <button key={t.id} onClick={()=>setTab(t.id)} style={{
        width:"100%", display:"flex", alignItems:"center", gap:10,
        padding: isChild ? "8px 12px 8px 36px" : "10px 12px",
        borderRadius:10, border:"none", cursor:"pointer", fontFamily:"inherit",
        fontSize: isChild ? 12 : 13,
        fontWeight: active ? 700 : 400,
        marginBottom:2,
        background: active ? C.accentLt : "transparent",
        color: active ? C.accent : isChild ? C.inkMid : C.inkMid,
        textAlign:"left",
      }}>
        <span style={{fontSize: isChild ? 14 : 17}}>{t.icon}</span>{t.label}
        {active && <div style={{marginLeft:"auto",width:4,height:4,borderRadius:"50%",background:C.accent}}/>}
      </button>
    );
  };

  if (isMobile) return <MobileApp user={user} onLogout={onLogout} onUserUpdate={onUserUpdate} live={live} docTemplate={docTemplate} onTemplateChange={handleTemplateChange}/>;

  const screens = {
    dashboard:  <Dashboard  live={live}/>,
    invoicing:  <Invoicing  live={live} user={user} docTemplate={docTemplate}/>,
    quotes:     <Quotes     live={live} user={user} onNavigate={setTab} docTemplate={docTemplate}/>,
    expenses:   <Expenses   live={live}/>,
    payroll:    <Payroll    live={live} user={user}/>,
    reports:    <Reports    live={live}/>,
    budgeting:  <Budgeting  live={live}/>,
    debtors:    <Debtors    live={live}/>,
    creditors:  <Creditors  live={live}/>,
    coa:        <ChartOfAccounts/>,
    inventory:       <Inventory/>,
    fixed_assets:    <FixedAssets/>,
    customers:       <Customers/>,
    suppliers:       <Suppliers/>,
    purchase_orders: <PurchaseOrders/>,
    bankimport:      <BankImport live={live} onNavigate={setTab}/>,
    bankfeeds:       <BankFeeds/>,
    settings:   <AppSettings user={user} onLogout={onLogout} onUserUpdate={onUserUpdate} docTemplate={docTemplate} onTemplateChange={handleTemplateChange}/>,
  };

  return (
    <div style={{fontFamily:"sans-serif",background:C.bg,minHeight:"100vh",display:"flex"}}>
      <style>{`*{box-sizing:border-box;margin:0;padding:0;}::-webkit-scrollbar{width:4px;}::-webkit-scrollbar-thumb{background:${C.border};}button:hover{opacity:0.9;}`}</style>
      <div style={{width:230,background:C.surface,borderRight:`1px solid ${C.border}`,display:"flex",flexDirection:"column",position:"fixed",top:0,left:0,bottom:0,zIndex:10}}>
        <div style={{padding:"24px 20px 20px",borderBottom:`1px solid ${C.border}`}}>
          <div style={{fontFamily:"serif",fontSize:26,fontWeight:800,color:C.ink}}><span style={{color:C.accent}}>Zu</span>Zan</div>
          <div style={{fontSize:10,color:C.inkMid,marginTop:3,letterSpacing:0.5}}>SA BOOKKEEPING PLATFORM</div>
        </div>
        <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.border}`}}>
          <div style={{fontSize:12,fontWeight:600,color:C.ink,marginBottom:2}}>{user?.companyName||"Your Company"}</div>
          <div style={{fontSize:10,color:C.inkDim}}>{user?.plan?.name||"Professional"} Plan</div>
          <div style={{marginTop:8,height:3,background:C.border,borderRadius:2}}><div style={{height:"100%",width:"65%",background:C.accent,borderRadius:2}}/></div>
          <div style={{fontSize:9,color:C.inkDim,marginTop:4}}>{user?.trialEnds ? (()=>{const d=Math.max(0,Math.ceil((new Date(user.trialEnds)-new Date())/86400000));return d>0?`Trial: ${d} day${d===1?"":"s"} remaining`:"Trial expired";})() : "Trial: 14 days remaining"}</div>
        </div>
        <nav style={{flex:1,padding:"12px 10px",overflowY:"auto"}}>
          {TABS.map(t => {
            if (!t.children) return navBtn(t);
            const isOpen = expanded[t.id];
            const childActive = t.children.some(c => c.id === tab);
            return (
              <div key={t.id}>
                <button onClick={()=>toggleGroup(t.id)} style={{
                  width:"100%", display:"flex", alignItems:"center", gap:10,
                  padding:"10px 12px", borderRadius:10, border:"none", cursor:"pointer",
                  fontFamily:"inherit", fontSize:13, marginBottom:2,
                  fontWeight: childActive ? 700 : 400,
                  background: childActive ? C.accentLt : "transparent",
                  color: childActive ? C.accent : C.inkMid,
                  textAlign:"left",
                }}>
                  <span style={{fontSize:17}}>{t.icon}</span>
                  {t.label}
                  <span style={{marginLeft:"auto",fontSize:10,opacity:.5}}>{isOpen ? "▾" : "▸"}</span>
                </button>
                {isOpen && t.children.map(c => navBtn(c, true))}
              </div>
            );
          })}
        </nav>
        <div style={{padding:"14px 20px",borderTop:`1px solid ${C.border}`}}>
          <div style={{fontSize:12,fontWeight:600,color:C.ink}}>{user?.firstName||"User"} {user?.lastName||""}</div>
          <div style={{fontSize:10,color:C.inkDim,marginBottom:8}}>{user?.email||"user@company.co.za"}</div>
          <button onClick={onLogout} style={{fontSize:11,color:C.inkDim,background:"none",border:"none",cursor:"pointer",padding:0,fontFamily:"inherit"}}>Sign out</button>
        </div>
      </div>
      <div style={{marginLeft:230,flex:1,padding:"36px",maxWidth:"calc(100vw - 230px)",overflowY:"auto",minHeight:"100vh"}}>
        {screens[tab]}
      </div>
      <AIAssistant tab={tab}/>
    </div>
  );
}

// ── ROOT ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [screen, setScreen] = useState("loading");
  const [user,   setUser]   = useState(null);

  // Keep Render free-tier backend alive — pings /health every 8 min while logged in
  useEffect(() => {
    if (screen !== "app") return;
    const id = setInterval(() => fetch(`${BASE_URL}/health`).catch(() => {}), 8 * 60 * 1000);
    return () => clearInterval(id);
  }, [screen]);

  useEffect(() => {
    const token = localStorage.getItem("zuzan_token");
    if (!token || token.startsWith("demo_")) { setScreen("login"); return; }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    fetch("https://zuzan-backend.onrender.com/auth/me", {
      headers: {"Authorization": "Bearer " + token},
      signal: controller.signal
    })
      .then(r => { clearTimeout(timeout); return r.ok ? r.json() : Promise.reject(); })
      .then(data => {
        setUser({
          firstName:    data.user.first_name,
          lastName:     data.user.last_name,
          email:        data.user.email,
          companyName:  data.company.name,
          logoUrl:      data.company.logo_url || "",
          plan:         {name: data.company.plan, id: data.company.plan},
          access_token: token,
          trialEnds:    data.company.trial_ends,
        });
        setScreen("app");
      })
      .catch(() => { clearTimeout(timeout); localStorage.removeItem("zuzan_token"); setScreen("login"); });
  }, []);

  const handleLogin = userData => { setUser(userData); setScreen("app"); };

  const handleRegistrationComplete = userData => {
    const savedToken = localStorage.getItem("zuzan_token");
    if (!savedToken || savedToken.startsWith("demo_")) {
      localStorage.setItem("zuzan_token", "demo_" + Date.now());
    }
    setUser(userData);
    setScreen("app");
  };

  const handleLogout = () => {
    localStorage.removeItem("zuzan_token");
    setUser(null);
    setScreen("login");
  };

  // ── Auto-logout after 5 minutes of inactivity ──
  useEffect(() => {
    if (screen !== "app") return;
    const TIMEOUT_MS = 5 * 60 * 1000;
    let timer;
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        localStorage.removeItem("zuzan_token");
        setUser(null);
        setScreen("login");
        // Brief delay so React can unmount cleanly before the alert
        setTimeout(() => alert("You were signed out due to 5 minutes of inactivity."), 50);
      }, TIMEOUT_MS);
    };
    const events = ["mousemove","mousedown","keydown","touchstart","scroll","click"];
    events.forEach(e => window.addEventListener(e, reset, {passive:true}));
    reset(); // start timer on mount
    return () => {
      clearTimeout(timer);
      events.forEach(e => window.removeEventListener(e, reset));
    };
  }, [screen]);

  if (screen === "loading") return (
    <div style={{minHeight:"100vh",background:C.bg,display:"flex",alignItems:"center",justifyContent:"center"}}>
      <div style={{textAlign:"center"}}>
        <div style={{fontFamily:"serif",fontSize:40,fontWeight:800,color:C.ink,marginBottom:12}}><span style={{color:C.accent}}>Zu</span>Zan</div>
        <div style={{fontSize:13,color:C.inkMid}}>Loading your account...</div>
      </div>
    </div>
  );

  if (screen === "login")        return <Login        onLogin={handleLogin} onRegister={()=>setScreen("registration")}/>;
  if (screen === "registration") return <Registration onComplete={handleRegistrationComplete} onLogin={()=>setScreen("login")}/>;

  return <ZuZanApp user={user} onLogout={handleLogout} onUserUpdate={setUser}/>;
}
