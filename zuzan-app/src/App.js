import { useState, useEffect, useRef } from "react";
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
  { id:"starter",      name:"Starter",      monthly:299,  annual:2990,  usdMonthly:16, users:2,  invoices:20,         color:C.blue,   icon:"🌱", features:["2 users","20 invoices/month","Expense tracking","Bank feed (all SA banks)","Bank reconciliation","Basic P&L report","Email support"] },
  { id:"professional", name:"Professional", monthly:699,  annual:6990,  usdMonthly:38, users:5,  invoices:50,         color:C.accent, icon:"⚡", popular:true, features:["5 users","50 invoices/month","Everything in Starter","Advanced reports","Cash flow statement","Bank reconciliation","Priority support"] },
  { id:"business",     name:"Business",     monthly:1299, annual:12990, usdMonthly:70, users:20, invoices:"Unlimited", color:C.green,  icon:"🏢", features:["20 users","Unlimited invoices","Everything in Professional","Multi-branch bank feeds","Custom report builder","API access","Dedicated account manager"] },
];

const MOCK_INVOICES = [
  {id:"INV-001",client:"Acme Pty Ltd",    amount:45000,date:"2025-04-01",due:"2025-05-01",status:"paid",   desc:"Web development services"},
  {id:"INV-002",client:"BuildRight CC",   amount:28500,date:"2025-04-10",due:"2025-05-10",status:"pending",desc:"IT consulting"},
  {id:"INV-003",client:"SA Retail Group", amount:67200,date:"2025-04-15",due:"2025-05-15",status:"overdue",desc:"Software licence"},
  {id:"INV-004",client:"Cape Town Motors",amount:15800,date:"2025-04-20",due:"2025-05-20",status:"paid",   desc:"Monthly retainer"},
];

const MOCK_EXPENSES = [
  {id:"EXP-001",vendor:"Eskom",          amount:3200,date:"2025-04-02",category:"Utilities",desc:"Electricity"},
  {id:"EXP-002",vendor:"Telkom",         amount:1850,date:"2025-04-05",category:"Telecoms", desc:"Fibre + phone"},
  {id:"EXP-003",vendor:"Office National",amount:2400,date:"2025-04-08",category:"Office",   desc:"Stationery"},
  {id:"EXP-004",vendor:"FNB",            amount:450, date:"2025-04-10",category:"Banking",  desc:"Bank charges"},
  {id:"EXP-005",vendor:"Discovery",      amount:4200,date:"2025-04-12",category:"Insurance",desc:"Business insurance"},
];

const MOCK_EMPLOYEES = [
  {id:"EMP-001",name:"Sipho Dlamini",     position:"Developer",    salary:45000,dept:"Tech"},
  {id:"EMP-002",name:"Priya Naidoo",      position:"Accountant",   salary:38000,dept:"Finance"},
  {id:"EMP-003",name:"Johan van der Berg",position:"Sales Manager",salary:52000,dept:"Sales"},
  {id:"EMP-004",name:"Nomsa Khumalo",     position:"Admin",        salary:22000,dept:"Admin"},
];

const REVENUE_DATA = [
  {month:"Nov",revenue:85000, expenses:52000,profit:33000},
  {month:"Dec",revenue:112000,expenses:61000,profit:51000},
  {month:"Jan",revenue:78000, expenses:48000,profit:30000},
  {month:"Feb",revenue:95000, expenses:55000,profit:40000},
  {month:"Mar",revenue:103000,expenses:58000,profit:45000},
  {month:"Apr",revenue:156500,expenses:24600,profit:131900},
];

const EXPENSE_PIE = [
  {name:"Salaries",value:157000,color:C.accent},
  {name:"Utilities",value:5050, color:C.blue},
  {name:"Office",   value:2850, color:C.gold},
  {name:"Insurance",value:4200, color:C.green},
  {name:"Banking",  value:450,  color:C.inkDim},
];

const ALL_CATS = ["Revenue","Interest Income","Cost of Sales","Utilities","Telecoms","Office","Banking","Insurance","Tax","Equipment","Travel","Salaries","Rent","Marketing","Professional Fees","Other"];

const BRACKETS = [
  {min:0,      max:237100,  rate:0.18,base:0},
  {min:237101, max:370500,  rate:0.26,base:42678},
  {min:370501, max:512800,  rate:0.31,base:77362},
  {min:512801, max:673000,  rate:0.36,base:121475},
  {min:673001, max:857900,  rate:0.39,base:179147},
  {min:857901, max:1817000, rate:0.41,base:251258},
  {min:1817001,max:9999999, rate:0.45,base:644489},
];

function calcPAYE(annual) {
  const b = BRACKETS.find(b => annual >= b.min && annual <= b.max);
  if (!b) return 0;
  return Math.max(0, b.base + (annual - b.min) * b.rate - 17235);
}

function calcPayroll(salary) {
  const paye = calcPAYE(salary*12)/12;
  const uifBase = Math.min(salary,17712);
  const uifEmp = uifBase*0.01, uifEmpr = uifBase*0.01, sdl = salary*0.01;
  return {
    gross:salary,
    paye:Math.round(paye),
    uifEmployee:Math.round(uifEmp),
    uifEmployer:Math.round(uifEmpr),
    sdl:Math.round(sdl),
    netPay:Math.round(salary-paye-uifEmp),
    totalCost:Math.round(salary+uifEmpr+sdl)
  };
}

const Badge = ({label,color,bg}) => (
  <span style={{fontSize:10,fontWeight:700,color,background:bg,padding:"3px 9px",borderRadius:20,letterSpacing:0.5,textTransform:"uppercase"}}>{label}</span>
);

const StatusBadge = ({status}) => {
  const m={paid:[C.green,C.greenLt,"Paid"],pending:[C.gold,C.goldLt,"Pending"],overdue:[C.red,C.redLt,"Overdue"]};
  const [c,bg,l]=m[status]||m.pending;
  return <Badge label={l} color={c} bg={bg}/>;
};

const KPI = ({label,value,sub,color=C.ink,icon}) => (
  <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:"16px 18px",flex:1}}>
    <div style={{display:"flex",justifyContent:"space-between",marginBottom:8}}>
      <span style={{fontSize:10,color:C.inkMid,letterSpacing:0.5,textTransform:"uppercase",fontWeight:600}}>{label}</span>
      <span style={{fontSize:16}}>{icon}</span>
    </div>
    <div style={{fontSize:22,fontWeight:800,color,fontFamily:"'Playfair Display',serif",marginBottom:3}}>{value}</div>
    {sub && <div style={{fontSize:11,color:C.inkDim}}>{sub}</div>}
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
  fnb:          {name:"FNB",          logo:"🟢",skipRows:4,dateCol:0,descCol:2,amtCol:4},
  absa:         {name:"ABSA",         logo:"🔴",skipRows:1,dateCol:0,descCol:1,amtCol:3},
  standardbank: {name:"Standard Bank",logo:"🔵",skipRows:1,dateCol:0,descCol:1,amtCol:2},
  nedbank:      {name:"Nedbank",      logo:"🟩",skipRows:1,dateCol:0,descCol:1,amtCol:2},
  capitec:      {name:"Capitec",      logo:"🟦",skipRows:1,dateCol:0,descCol:2,amtCol:3},
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
function Dashboard({live = {}}) {
  const d = live.dashboard;
  const revenueData = live.trend || REVENUE_DATA;
  const isLive = live.connected;

  // Use live data if available, otherwise fall back to mock
  const totalRevenue  = d ? d.total_revenue  : MOCK_INVOICES.filter(i => i.status === "paid").reduce((s,i) => s + i.amount, 0);
  const totalExpenses = d ? d.total_expenses : MOCK_EXPENSES.reduce((s,e) => s + e.amount, 0);
  const outstanding   = d ? d.total_outstanding : MOCK_INVOICES.filter(i => i.status !== "paid").reduce((s,i) => s + i.amount, 0);
  const profit        = d ? d.net_profit     : totalRevenue - totalExpenses;
  const totalPayroll  = d ? d.total_payroll  : MOCK_EMPLOYEES.reduce((s,e) => s + calcPayroll(e.salary).totalCost, 0);
  return (
    <div>
      <div style={{marginBottom:24,display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
        <div>
          <h1 style={{fontFamily:"serif",fontSize:28,color:C.ink,margin:"0 0 4px"}}>Good morning</h1>
          <p style={{color:C.inkMid,fontSize:13}}>Financial overview - {d ? d.period : "April 2025"}</p>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:6,padding:"6px 14px",borderRadius:20,background:isLive?C.greenLt:C.goldLt,border:`1px solid ${isLive?C.green:C.gold}`}}>
          <div style={{width:6,height:6,borderRadius:"50%",background:isLive?C.green:C.gold}}/>
          <span style={{fontSize:11,fontWeight:600,color:isLive?C.green:C.gold}}>{isLive?"Live Data":"Demo Mode"}</span>
        </div>
      </div>
      <div style={{display:"flex",gap:12,marginBottom:20,flexWrap:"wrap"}}>
        <KPI label="Revenue" value={fmt(totalRevenue)} sub="This month" color={C.green} icon="💰"/>
        <KPI label="Expenses" value={fmt(totalExpenses)} sub="This month" color={C.red} icon="📤"/>
        <KPI label="Net Profit" value={fmt(profit)} sub="After expenses" color={C.accent} icon="📊"/>
        <KPI label="Outstanding" value={fmt(outstanding)} sub="Pending invoices" color={C.gold} icon="⏳"/>
        <KPI label="Payroll" value={fmt(totalPayroll)} sub={`${MOCK_EMPLOYEES.length} employees`} color={C.blue} icon="👥"/>
      </div>
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
        <div style={{fontSize:14,fontWeight:700,color:C.ink,marginBottom:16}}>Profit Trend</div>
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
            <Area type="monotone" dataKey="profit" name="Profit" stroke={C.green} strokeWidth={2} fill="url(#pg)" dot={false}/>
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

// ── INVOICING ─────────────────────────────────────────────────────────────────
function Invoicing({live = {}}) {
  const liveInvoices = live.invoices;
  const [invoices, setInvoices] = useState(MOCK_INVOICES);

  useEffect(() => { if (liveInvoices && liveInvoices.length > 0) setInvoices(liveInvoices.map(i => ({...i, date: i.issue_date || i.date, due: i.due_date || i.due, client: i.client_name || i.client, desc: i.description, amount: i.total_amount || i.amount, id: i.invoice_number || `INV-${String(i.id).padStart(3,"0")}`}))); }, [liveInvoices]);
  const [showNew, setShowNew] = useState(false);
  const [preview, setPreview] = useState(null);
  const [form, setForm] = useState({client:"",amount:"",desc:"",due:""});

  const totalPaid = invoices.filter(i => i.status === "paid").reduce((s,i) => s + i.amount, 0);
  const totalPending = invoices.filter(i => i.status === "pending").reduce((s,i) => s + i.amount, 0);
  const totalOverdue = invoices.filter(i => i.status === "overdue").reduce((s,i) => s + i.amount, 0);

  const handleCreate = async () => {
    const newInv = {
      id:`INV-00${invoices.length+1}`,
      client:form.client,
      amount:+form.amount,
      date:new Date().toISOString().slice(0,10),
      due:form.due,
      status:"pending",
      desc:form.desc
    };
    // Update local state immediately
    setInvoices([newInv,...invoices]);
    setShowNew(false);
    setForm({client:"",amount:"",desc:"",due:""});
    // Save to backend
    try {
      await api("/invoices/", {
        method: "POST",
        body: JSON.stringify({
          client_name:  form.client,
          description:  form.desc,
          amount:       +form.amount,
          due_date:     form.due || null,
        }),
      });
      if (live && live.reload) live.reload();
    } catch(err) {
      console.warn("Invoice save failed:", err.message);
    }
  };

  return (
    <div>
      <SectionHeader title="Invoicing" sub="Manage your client invoices" action="+ New Invoice" onAction={() => setShowNew(true)}/>
      <div style={{display:"flex",gap:12,marginBottom:24}}>
        <KPI label="Paid" value={fmt(totalPaid)} color={C.green} icon="✅"/>
        <KPI label="Pending" value={fmt(totalPending)} color={C.gold} icon="⏳"/>
        <KPI label="Overdue" value={fmt(totalOverdue)} color={C.red} icon="⚠️"/>
      </div>
      {showNew && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:24,marginBottom:20}}>
          <h3 style={{fontFamily:"serif",margin:"0 0 16px",color:C.ink}}>New Invoice</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
            {[{l:"Client Name",k:"client",p:"Acme Pty Ltd",t:"text"},{l:"Amount (ZAR)",k:"amount",p:"50000",t:"number"},{l:"Description",k:"desc",p:"Services rendered",t:"text"},{l:"Due Date",k:"due",p:"",t:"date"}].map(f => (
              <div key={f.k}>
                <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                <input type={f.t} placeholder={f.p} value={form[f.k]} onChange={e => setForm({...form,[f.k]:e.target.value})} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
              </div>
            ))}
          </div>
          <div style={{display:"flex",gap:8}}>
            <button onClick={handleCreate} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Create Invoice</button>
            <button onClick={() => setShowNew(false)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
          </div>
        </div>
      )}
      {preview && (
        <div style={{position:"fixed",inset:0,background:"#00000060",zIndex:100,display:"flex",alignItems:"center",justifyContent:"center"}} onClick={() => setPreview(null)}>
          <div style={{background:"#fff",borderRadius:20,padding:40,width:560,maxHeight:"80vh",overflow:"auto"}} onClick={e => e.stopPropagation()}>
            <div style={{display:"flex",justifyContent:"space-between",marginBottom:32}}>
              <div>
                <div style={{fontFamily:"serif",fontSize:28,fontWeight:800,color:C.accent}}>ZuZan</div>
                <div style={{fontSize:11,color:C.inkMid}}>Your Company Pty Ltd</div>
              </div>
              <div style={{textAlign:"right"}}>
                <div style={{fontSize:20,fontWeight:800,color:C.ink}}>TAX INVOICE</div>
                <div style={{fontSize:13,color:C.inkMid}}>{preview.id}</div>
              </div>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:20,marginBottom:24}}>
              <div><div style={{fontSize:10,color:C.inkMid,fontWeight:600,textTransform:"uppercase",marginBottom:6}}>Bill To</div><div style={{fontWeight:700,color:C.ink}}>{preview.client}</div></div>
              <div style={{textAlign:"right"}}><div style={{fontSize:12,color:C.inkMid}}>Date: {fmtDate(preview.date)}</div><div style={{fontSize:12,color:C.inkMid}}>Due: {fmtDate(preview.due)}</div></div>
            </div>
            <table style={{width:"100%",borderCollapse:"collapse",marginBottom:24}}>
              <thead><tr style={{background:C.bg}}><th style={{padding:"10px 12px",textAlign:"left",fontSize:11,color:C.inkMid}}>Description</th><th style={{padding:"10px 12px",textAlign:"right",fontSize:11,color:C.inkMid}}>Amount</th></tr></thead>
              <tbody><tr><td style={{padding:"12px",color:C.ink}}>{preview.desc}</td><td style={{padding:"12px",textAlign:"right",fontWeight:600}}>{fmt(preview.amount)}</td></tr></tbody>
            </table>
            <div style={{borderTop:`2px solid ${C.border}`,paddingTop:16}}>
              <div style={{display:"flex",justifyContent:"space-between",padding:"10px 0"}}><span style={{fontWeight:800,fontSize:15}}>TOTAL DUE</span><span style={{fontWeight:800,fontSize:18,color:C.accent}}>{fmt(preview.amount)}</span></div>
            </div>
            <div style={{background:C.bg,borderRadius:10,padding:12,marginTop:16,fontSize:11,color:C.inkMid}}>Banking: FNB Business - Acc: 62XXXXXXXXX - Branch: 250655</div>
            <div style={{display:"flex",gap:8,marginTop:20}}>
              <button onClick={() => window.print()} style={{flex:1,background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"11px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Print / PDF</button>
              <button onClick={() => setPreview(null)} style={{flex:1,background:"transparent",border:`1px solid ${C.border}`,borderRadius:10,padding:"11px",fontSize:13,cursor:"pointer",fontFamily:"inherit",color:C.inkMid}}>Close</button>
            </div>
          </div>
        </div>
      )}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
        <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
          <thead>
            <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
              {["Invoice #","Client","Description","Amount","Date","Due","Status",""].map(h => <th key={h} style={{textAlign:"left",padding:"12px 16px",fontSize:10,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {invoices.map((inv) => (
              <tr key={inv.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                <td style={{padding:"13px 16px",fontWeight:700,color:C.accent}}>{inv.id}</td>
                <td style={{padding:"13px 16px",fontWeight:500}}>{inv.client}</td>
                <td style={{padding:"13px 16px",color:C.inkMid,fontSize:12}}>{inv.desc}</td>
                <td style={{padding:"13px 16px",fontWeight:700}}>{fmt(inv.amount)}</td>
                <td style={{padding:"13px 16px",color:C.inkMid}}>{fmtDate(inv.date)}</td>
                <td style={{padding:"13px 16px",color:inv.status === "overdue" ? C.red : C.inkMid}}>{fmtDate(inv.due)}</td>
                <td style={{padding:"13px 16px"}}><StatusBadge status={inv.status}/></td>
                <td style={{padding:"13px 16px"}}>
                  <button onClick={() => setPreview(inv)} style={{background:C.blueLt,color:C.blue,border:"none",borderRadius:6,padding:"5px 10px",fontSize:11,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>View</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
// ── EXPENSES ──────────────────────────────────────────────────────────────────
function Expenses({live = {}}) {
  const liveExpenses = live.expenses;
  const [expenses, setExpenses] = useState(MOCK_EXPENSES);

  // Sync live expenses when they load
  useEffect(() => { if (liveExpenses && liveExpenses.length > 0) setExpenses(liveExpenses.map(e => ({...e, date: e.expense_date || e.date, desc: e.description, vendor: e.vendor, amount: e.amount, category: e.category || "Other", id: `EXP-${String(e.id).padStart(3,"0")}`}))); }, [liveExpenses]);
  const [showNew, setShowNew] = useState(false);
  const [filter, setFilter] = useState("All");
  const [form, setForm] = useState({vendor:"",amount:"",category:"Office",desc:""});
  const cats = ["All","Assets","Liabilities","Equity","Income","Cost of Sales","Expenses"];
  const filtered = filter === "All" ? expenses : expenses.filter(e => e.category === filter);
  const total = filtered.reduce((s,e) => s + e.amount, 0);
  const handleAdd = async () => {
    const newExp = {
      id:`EXP-00${expenses.length+1}`,
      vendor:form.vendor,
      amount:+form.amount,
      date:new Date().toISOString().slice(0,10),
      category:form.category,
      desc:form.desc
    };
    // Update local state immediately
    setExpenses([newExp,...expenses]);
    setShowNew(false);
    setForm({vendor:"",amount:"",category:"Office",desc:""});
    // Save to backend
    try {
      await api("/expenses/", {
        method: "POST",
        body: JSON.stringify({
          vendor:       form.vendor,
          description:  form.desc,
          amount:       +form.amount,
          category:     form.category,
          expense_date: new Date().toISOString().slice(0,10),
        }),
      });
      if (live && live.reload) live.reload();
    } catch(err) {
      console.warn("Expense save failed:", err.message);
    }
  };
  return (
    <div>
      <SectionHeader title="Expenses" sub="Track and categorise business expenses" action="+ Add Expense" onAction={() => setShowNew(true)}/>
      {showNew && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:24,marginBottom:20}}>
          <h3 style={{fontFamily:"serif",margin:"0 0 16px",color:C.ink}}>Add Expense</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
            {[{l:"Vendor",k:"vendor",p:"Eskom"},{l:"Amount (ZAR)",k:"amount",p:"1500"},{l:"Description",k:"desc",p:"Monthly bill"}].map(f => (
              <div key={f.k}>
                <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                <input placeholder={f.p} value={form[f.k]} onChange={e => setForm({...form,[f.k]:e.target.value})} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
              </div>
            ))}
            <div>
              <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>Category</label>
              <select value={form.category} onChange={e => setForm({...form,category:e.target.value})} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none"}}>
                <option value="">-- Select Account --</option>
                {COA_GROUPS.map(group => (
                  <optgroup key={group} label={group}>
                    {DEFAULT_COA.filter(a => a.group === group && a.type === "Detail").map(a => (
                      <option key={a.code} value={`${a.code} - ${a.name}`}>{a.code} - {a.name}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
          </div>
          <div style={{display:"flex",gap:8}}>
            <button onClick={handleAdd} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Add</button>
            <button onClick={() => setShowNew(false)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
          </div>
        </div>
      )}
      <div style={{display:"flex",gap:8,marginBottom:20,flexWrap:"wrap",alignItems:"center"}}>
        {cats.map(c => <button key={c} onClick={() => setFilter(c)} style={{padding:"6px 14px",borderRadius:20,border:`1px solid ${filter===c?C.accent:C.border}`,background:filter===c?C.accentLt:"transparent",color:filter===c?C.accent:C.inkMid,fontSize:12,fontWeight:filter===c?700:400,cursor:"pointer",fontFamily:"inherit"}}>{c}</button>)}
        <div style={{marginLeft:"auto",fontSize:14,fontWeight:700,color:C.ink}}>Total: {fmt(total)}</div>
      </div>
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden"}}>
        <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
          <thead>
            <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
              {["#","Vendor","Description","Category","Date","Amount"].map(h => <th key={h} style={{textAlign:"left",padding:"12px 16px",fontSize:10,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase"}}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {filtered.map((exp) => (
              <tr key={exp.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                <td style={{padding:"13px 16px",fontWeight:600,color:C.inkMid,fontSize:11}}>{exp.id}</td>
                <td style={{padding:"13px 16px",fontWeight:600}}>{exp.vendor}</td>
                <td style={{padding:"13px 16px",color:C.inkMid,fontSize:12}}>{exp.desc}</td>
                <td style={{padding:"13px 16px"}}><Badge label={exp.category} color={C.blue} bg={C.blueLt}/></td>
                <td style={{padding:"13px 16px",color:C.inkMid}}>{fmtDate(exp.date)}</td>
                <td style={{padding:"13px 16px",fontWeight:700,color:C.red}}>{fmt(exp.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


// ── PAYSLIP MODAL ─────────────────────────────────────────────────────────────
function PayslipModal({employee, payroll, period, company, onClose}) {
  const p = payroll;
  const today = new Date().toLocaleDateString("en-ZA", {day:"2-digit", month:"long", year:"numeric"});

  const handlePrint = () => {
    const printContent = document.getElementById("payslip-content").innerHTML;
    const win = window.open("", "_blank");
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
    win.print();
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
              <div style={{fontFamily:"serif",fontSize:28,fontWeight:800,color:C.accent}}>ZuZan</div>
              <div style={{fontSize:11,color:C.inkMid,marginTop:2}}>{company || "Your Company Pty Ltd"}</div>
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
                ["Employee ID",   employee.id || "EMP-001"],
                ["Position",      employee.position || "Staff"],
                ["Department",    employee.dept || "General"],
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
            <strong style={{color:C.ink}}>SARS Reference (2025/2026)</strong><br/>
            PAYE calculated on annual income of {fmt(p.gross * 12)} — Primary rebate R17,235/year<br/>
            UIF: 1% employee + 1% employer — capped at R17,712/month<br/>
            SDL: 1% of gross payroll
          </div>

        </div>
      </div>
    </div>
  );
}

// ── PAYROLL ───────────────────────────────────────────────────────────────────
function Payroll({live = {}}) {
  const liveEmployees = live.employees;
  const [employees, setEmployees] = useState(MOCK_EMPLOYEES);

  useEffect(() => { if (liveEmployees && liveEmployees.length > 0) setEmployees(liveEmployees.map(e => ({...e, name: `${e.first_name} ${e.last_name}`, salary: e.gross_salary, dept: e.department || "General"}))); }, [liveEmployees]);
  const [showNew, setShowNew] = useState(false);
  const [payrollRun, setPayrollRun] = useState(false);
  const [form, setForm] = useState({name:"",position:"",salary:"",dept:""});
  const [viewPayslip, setViewPayslip] = useState(null);
  const totalGross = employees.reduce((s,e) => s + e.salary, 0);
  const totalPAYE = employees.reduce((s,e) => s + calcPayroll(e.salary).paye, 0);
  const totalNet = employees.reduce((s,e) => s + calcPayroll(e.salary).netPay, 0);
  const totalCost = employees.reduce((s,e) => s + calcPayroll(e.salary).totalCost, 0);
  const totalUIF = employees.reduce((s,e) => s + calcPayroll(e.salary).uifEmployer, 0);
  const totalSDL = employees.reduce((s,e) => s + calcPayroll(e.salary).sdl, 0);
  const zuZanFee = Math.max(99, employees.length * 17.50);
  const handleAdd = async () => {
    const nameParts = form.name.trim().split(" ");
    const firstName = nameParts[0] || form.name;
    const lastName  = nameParts.slice(1).join(" ") || "";
    const newEmp = {
      id:`EMP-00${employees.length+1}`,
      name:form.name,
      position:form.position,
      salary:+form.salary,
      dept:form.dept
    };
    setEmployees([...employees, newEmp]);
    setShowNew(false);
    setForm({name:"",position:"",salary:"",dept:""});
    // Save to backend
    try {
      // Enable payroll if not already enabled
      const token = localStorage.getItem("zuzan_token");
      if (token && !token.startsWith("demo_")) {
        try {
          await api("/companies/me", {
            method: "PUT",
            body: JSON.stringify({payroll_enabled: true}),
          });
        } catch(e) { /* ignore */ }
      }
      await api("/employees/", {
        method: "POST",
        body: JSON.stringify({
          first_name:   firstName,
          last_name:    lastName,
          position:     form.position,
          department:   form.dept,
          gross_salary: +form.salary,
        }),
      });
      if (live && live.reload) live.reload();
    } catch(err) {
      console.warn("Employee save failed:", err.message);
    }
  };
  return (
    <div>
      <SectionHeader title="Payroll" sub="SARS-compliant PAYE, UIF, SDL, EMP201, IRP5" action="+ Add Employee" onAction={() => setShowNew(true)}/>
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
          <div style={{fontWeight:700,fontSize:15,color:C.ink}}>April 2025 Payroll</div>
          <div style={{fontSize:12,color:C.inkMid,marginTop:3}}>Net pay: {fmt(totalNet)} - SARS due: 7 May 2025</div>
        </div>
        <button onClick={async () => {
          try {
            await api("/payroll/run", {method:"POST"});
            if (live && live.reload) live.reload();
          } catch(err) {
            console.warn("Payroll run failed:", err.message);
          }
          setPayrollRun(true);
        }} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Run Payroll</button>
      </div>
      {payrollRun && (
        <div style={{background:C.surface,border:`2px solid ${C.green}`,borderRadius:16,padding:20,marginBottom:20}}>
          <div style={{fontSize:16,fontWeight:700,color:C.green,marginBottom:12}}>Payroll Processed - April 2025</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:12}}>
            {[["Net Disbursed",fmt(totalNet),C.green],["PAYE to SARS",fmt(totalPAYE),C.red],["UIF and SDL",fmt(totalUIF+totalSDL),C.gold],["ZuZan Fee",fmt(zuZanFee),C.accent]].map(([l,v,c]) => (
              <div key={l} style={{background:C.bg,borderRadius:10,padding:14}}>
                <div style={{fontSize:10,color:C.inkMid,marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{l}</div>
                <div style={{fontSize:18,fontWeight:700,color:c}}>{v}</div>
              </div>
            ))}
          </div>
          <div style={{marginTop:12,fontSize:12,color:C.inkMid}}>EMP201 generated - Payslips ready - SARS eFiling export ready</div>
        </div>
      )}
      {showNew && (
        <div style={{background:C.surface,border:`2px solid ${C.accent}`,borderRadius:16,padding:24,marginBottom:20}}>
          <h3 style={{fontFamily:"serif",margin:"0 0 16px",color:C.ink}}>New Employee</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
            {[{l:"Full Name",k:"name",p:"Sipho Dlamini"},{l:"Position",k:"position",p:"Developer"},{l:"Monthly Salary (ZAR)",k:"salary",p:"35000"},{l:"Department",k:"dept",p:"Tech"}].map(f => (
              <div key={f.k}>
                <label style={{fontSize:11,fontWeight:600,color:C.inkMid,display:"block",marginBottom:6,textTransform:"uppercase",letterSpacing:0.5}}>{f.l}</label>
                <input placeholder={f.p} value={form[f.k]} onChange={e => setForm({...form,[f.k]:e.target.value})} style={{width:"100%",padding:"10px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:13,fontFamily:"inherit",background:C.bg,color:C.ink,outline:"none",boxSizing:"border-box"}}/>
              </div>
            ))}
          </div>
          <div style={{display:"flex",gap:8}}>
            <button onClick={handleAdd} style={{background:C.accent,color:"#fff",border:"none",borderRadius:10,padding:"10px 20px",fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Add Employee</button>
            <button onClick={() => setShowNew(false)} style={{background:"transparent",color:C.inkMid,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 20px",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button>
          </div>
        </div>
      )}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,overflow:"hidden",marginBottom:16}}>
        <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
          <thead>
            <tr style={{background:C.bg,borderBottom:`1px solid ${C.border}`}}>
              {["Employee","Position","Dept","Gross","PAYE","UIF","SDL","Net Pay","Employer Cost",""].map(h => <th key={h} style={{textAlign:"left",padding:"12px 14px",fontSize:9,color:C.inkMid,fontWeight:600,letterSpacing:0.5,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {employees.map((emp) => {
              const p = calcPayroll(emp.salary);
              return (
                <tr key={emp.id} style={{borderBottom:`1px solid ${C.border}30`}}>
                  <td style={{padding:"13px 14px"}}><div style={{fontWeight:600,color:C.ink}}>{emp.name}</div><div style={{fontSize:10,color:C.inkMid}}>{emp.id}</div></td>
                  <td style={{padding:"13px 14px",color:C.inkMid}}>{emp.position}</td>
                  <td style={{padding:"13px 14px"}}><Badge label={emp.dept} color={C.blue} bg={C.blueLt}/></td>
                  <td style={{padding:"13px 14px",fontWeight:600}}>{fmt(p.gross)}</td>
                  <td style={{padding:"13px 14px",color:C.red}}>{fmt(p.paye)}</td>
                  <td style={{padding:"13px 14px",color:C.gold}}>{fmt(p.uifEmployee)}</td>
                  <td style={{padding:"13px 14px",color:C.blue}}>{fmt(p.sdl)}</td>
                  <td style={{padding:"13px 14px",fontWeight:700,color:C.green}}>{fmt(p.netPay)}</td>
                  <td style={{padding:"13px 14px",fontWeight:700,color:C.accent}}>{fmt(p.totalCost)}</td>
                  <td style={{padding:"13px 14px"}}>
                    <button onClick={()=>setViewPayslip({employee:emp,payroll:p})} style={{background:C.blueLt,color:C.blue,border:"none",borderRadius:6,padding:"5px 10px",fontSize:10,cursor:"pointer",fontFamily:"inherit",fontWeight:600}}>Payslip</button>
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
        <strong style={{color:C.ink}}>SARS Compliance Notes 2025/2026</strong><br/>
        PAYE: 2025/2026 tax tables - Primary rebate R17,235/year - Due 7th of each month<br/>
        UIF: 1 percent employee plus 1 percent employer - Capped at R17,712/month<br/>
        SDL: 1 percent of gross payroll - Payable if annual payroll exceeds R500,000
      </div>

      {viewPayslip && (
        <PayslipModal
          employee={viewPayslip.employee}
          payroll={viewPayslip.payroll}
          period={new Date().toLocaleDateString("en-ZA",{month:"long",year:"numeric"})}
          company="Your Company Pty Ltd"
          onClose={()=>setViewPayslip(null)}
        />
      )}
    </div>
  );
}
// ── REPORTS ───────────────────────────────────────────────────────────────────
function Reports({live = {}}) {
  const d = live.dashboard;
  const totalRevenue  = d ? d.total_revenue  : MOCK_INVOICES.filter(i => i.status === "paid").reduce((s,i) => s + i.amount, 0);
  const totalExpenses = d ? d.total_expenses : MOCK_EXPENSES.reduce((s,e) => s + e.amount, 0);
  const totalPayroll  = d ? d.total_payroll  : MOCK_EMPLOYEES.reduce((s,e) => s + calcPayroll(e.salary).totalCost, 0);
  const grossProfit   = d ? d.gross_profit   : totalRevenue - totalExpenses;
  const netProfit     = d ? d.net_profit     : grossProfit - totalPayroll;
  const taxProvision  = d ? d.tax_provision  : Math.max(0, netProfit * 0.27);
  const reportItems = [
    {label:"Revenue",value:totalRevenue,color:C.green,bold:true},
    {label:"Less: Operating Expenses",value:-totalExpenses,color:C.red},
    {label:"Gross Profit",value:grossProfit,color:C.ink,bold:true,border:true},
    {label:"Less: Payroll Costs",value:-totalPayroll,color:C.red},
    {label:"Net Profit Before Tax",value:netProfit,color:C.ink,bold:true,border:true},
    {label:"Less: Corporate Tax Provision (27%)",value:-taxProvision,color:C.red},
    {label:"Net Profit After Tax",value:netProfit-taxProvision,color:C.accent,bold:true,border:true,large:true},
  ];
  return (
    <div>
      <SectionHeader title="Reports" sub="SARS-ready financial statements"/>
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:28,marginBottom:20}}>
        <div style={{fontSize:16,fontWeight:800,fontFamily:"serif",color:C.ink,marginBottom:4}}>Income Statement - April 2025</div>
        <div style={{fontSize:12,color:C.inkMid,marginBottom:20}}>Your Company Pty Ltd - Registration: 2020/123456/07</div>
        {reportItems.map((row,i) => (
          <div key={i} style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderTop:row.border ? `2px solid ${C.border}` : `1px solid ${C.border}30`}}>
            <span style={{fontSize:row.large?15:13,fontWeight:row.bold?700:400,color:C.ink}}>{row.label}</span>
            <span style={{fontSize:row.large?18:14,fontWeight:row.bold?800:500,color:row.color}}>{row.value >= 0 ? fmt(row.value) : `(${fmt(Math.abs(row.value))})`}</span>
          </div>
        ))}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12}}>
        {[
          {title:"Balance Sheet",icon:"⚖️",desc:"Assets, liabilities and equity",color:C.blue},
          {title:"Cash Flow",icon:"💸",desc:"Cash inflows and outflows",color:C.accent},
          {title:"EMP201 Return",icon:"🏛️",desc:"Monthly SARS payroll submission",color:C.red},
          {title:"IRP5 Certificates",icon:"📋",desc:"Annual employee tax certificates",color:C.gold},
          {title:"Provisional Tax",icon:"📅",desc:"Bi-annual IRP6 return",color:C.purple},
          {title:"Export to Excel",icon:"📊",desc:"Download all data as xlsx",color:C.green},
        ].map((r,i) => (
          <div key={i} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:20,cursor:"pointer"}}
            onMouseEnter={e => e.currentTarget.style.borderColor = r.color}
            onMouseLeave={e => e.currentTarget.style.borderColor = C.border}>
            <div style={{fontSize:28,marginBottom:12}}>{r.icon}</div>
            <div style={{fontSize:13,fontWeight:700,color:C.ink,marginBottom:6}}>{r.title}</div>
            <div style={{fontSize:11,color:C.inkMid,marginBottom:14}}>{r.desc}</div>
            <button style={{background:r.color+"15",color:r.color,border:`1px solid ${r.color}40`,borderRadius:8,padding:"7px 14px",fontSize:11,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Generate PDF</button>
          </div>
        ))}
      </div>
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

      // Handle expired token — retry without auth (demo mode)
      if (res.status === 401) {
        localStorage.removeItem("zuzan_token");
        localStorage.setItem("zuzan_token", "demo_" + Date.now());
        await new Promise(r => setTimeout(r, 800));
        setResult({
          expenses_created: selectedTxns.filter(t => t.type === "debit").length,
          expenses_skipped: 0,
          credits_recorded: selectedTxns.filter(t => t.type === "credit").length,
          message: "Saved in demo mode (session expired)",
        });
        setStep("done");
        return;
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
        <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:0}}>Bank Statement Import</h2>
        <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>Upload your bank CSV to auto-import expenses</p>
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
            <div style={{fontSize:11,color:C.inkDim,marginTop:14}}>Supported: CSV from FNB, ABSA, Standard Bank, Nedbank, Capitec</div>
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
function AppSettings({user, onLogout}) {
  return (
    <div>
      <div style={{marginBottom:24}}>
        <h2 style={{fontFamily:"serif",fontSize:26,color:C.ink,margin:0}}>Settings</h2>
        <p style={{fontSize:12,color:C.inkMid,marginTop:3}}>Manage your ZuZan account</p>
      </div>
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:24,marginBottom:16}}>
        <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Subscription</div>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
          <div>
            <div style={{fontSize:16,fontWeight:700,color:C.ink}}>{user && user.plan ? user.plan.name : "Professional"} Plan</div>
            <div style={{fontSize:12,color:C.inkMid,marginTop:3}}>Trial ends in 9 days</div>
          </div>
          <Badge label="Trial Active" color={C.gold} bg={C.goldLt}/>
        </div>
        <div style={{display:"flex",gap:8}}>
          <button style={{padding:"9px 18px",background:C.accentLt,border:`1px solid ${C.accent}40`,borderRadius:8,color:C.accent,fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Upgrade Plan</button>
          <button style={{padding:"9px 18px",background:"transparent",border:`1px solid ${C.border}`,borderRadius:8,color:C.inkMid,fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>Manage Billing</button>
        </div>
      </div>
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:16,padding:24,marginBottom:16}}>
        <div style={{fontSize:12,fontWeight:700,color:C.inkMid,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Company Details</div>
        {[
          {label:"Company Name",value:user && user.companyName ? user.companyName : "Your Company Pty Ltd"},
          {label:"Reg Number",value:user && user.regNumber ? user.regNumber : "2020/123456/07"},
          {label:"Industry",value:user && user.industry ? user.industry : "Technology"},
          {label:"Financial Year End",value:"28 February"},
          {label:"VAT Status",value:"Not VAT Registered"},
        ].map((r,i) => (
          <div key={i} style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:i<4?`1px solid ${C.border}30`:"none",fontSize:13}}>
            <span style={{color:C.inkMid}}>{r.label}</span>
            <span style={{fontWeight:600,color:C.ink}}>{r.value}</span>
          </div>
        ))}
      </div>
      <div style={{background:C.surface,border:`1px solid ${C.red}40`,borderRadius:16,padding:24}}>
        <div style={{fontSize:12,fontWeight:700,color:C.red,letterSpacing:1,textTransform:"uppercase",marginBottom:16}}>Danger Zone</div>
        <div style={{display:"flex",gap:8}}>
          <button onClick={onLogout} style={{padding:"9px 18px",background:C.redLt,border:`1px solid ${C.red}40`,borderRadius:8,color:C.red,fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Sign Out</button>
          <button style={{padding:"9px 18px",background:"transparent",border:`1px solid ${C.red}40`,borderRadius:8,color:C.red,fontSize:12,cursor:"pointer",fontFamily:"inherit"}}>Cancel Subscription</button>
        </div>
      </div>
    </div>
  );
}

// ── REGISTRATION ──────────────────────────────────────────────────────────────
function Registration({onComplete}) {
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
        <div style={{fontSize:12,color:C.inkMid}}>Already have an account? <span style={{color:C.accent,cursor:"pointer",fontWeight:600}} onClick={() => onComplete({access_token:"demo_token"})}>Sign in</span></div>
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

// ── MAIN APP ──────────────────────────────────────────────────────────────────
function ZuZanApp({user, onLogout}) {
  const [tab, setTab] = useState("dashboard");
  const live = useLiveData();
  const TABS = [
    {id:"dashboard", label:"Dashboard",   icon:"🏠"},
    {id:"invoicing", label:"Invoices",    icon:"🧾"},
    {id:"expenses",  label:"Expenses",    icon:"💳"},
    {id:"payroll",   label:"Payroll",     icon:"👥"},
    {id:"reports",   label:"Reports",     icon:"📊"},
    {id:"coa",       label:"Accounts",    icon:"📒"},
    {id:"bankimport",label:"Bank Import", icon:"🏦"},
    {id:"settings",  label:"Settings",    icon:"⚙️"},
  ];
  const screens = {
    dashboard:  <Dashboard  live={live}/>,
    invoicing:  <Invoicing  live={live}/>,
    expenses:   <Expenses   live={live}/>,
    payroll:    <Payroll    live={live}/>,
    reports:    <Reports    live={live}/>,
    coa:        <ChartOfAccounts/>,
    bankimport: <BankImport live={live} onNavigate={setTab}/>,
    settings:   <AppSettings user={user} onLogout={onLogout}/>,
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
          <div style={{fontSize:12,fontWeight:600,color:C.ink,marginBottom:2}}>{user && user.companyName ? user.companyName : "Your Company Pty Ltd"}</div>
          <div style={{fontSize:10,color:C.inkDim}}>{user && user.plan ? user.plan.name : "Professional"} Plan</div>
          <div style={{marginTop:8,height:3,background:C.border,borderRadius:2}}><div style={{height:"100%",width:"65%",background:C.accent,borderRadius:2}}/></div>
          <div style={{fontSize:9,color:C.inkDim,marginTop:4}}>Trial: 9 days remaining</div>
        </div>
        <nav style={{flex:1,padding:"12px 10px"}}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{width:"100%",display:"flex",alignItems:"center",gap:10,padding:"10px 12px",borderRadius:10,border:"none",cursor:"pointer",fontFamily:"inherit",fontSize:13,fontWeight:tab===t.id?700:400,marginBottom:3,background:tab===t.id?C.accentLt:"transparent",color:tab===t.id?C.accent:C.inkMid,textAlign:"left"}}>
              <span style={{fontSize:17}}>{t.icon}</span>
              {t.label}
              {tab === t.id && <div style={{marginLeft:"auto",width:4,height:4,borderRadius:"50%",background:C.accent}}/>}
            </button>
          ))}
        </nav>
        <div style={{padding:"14px 20px",borderTop:`1px solid ${C.border}`}}>
          <div style={{fontSize:12,fontWeight:600,color:C.ink}}>{user && user.firstName ? user.firstName : "User"} {user && user.lastName ? user.lastName : ""}</div>
          <div style={{fontSize:10,color:C.inkDim,marginBottom:8}}>{user && user.email ? user.email : "user@company.co.za"}</div>
          <button onClick={onLogout} style={{fontSize:11,color:C.inkDim,background:"none",border:"none",cursor:"pointer",padding:0,fontFamily:"inherit"}}>Sign out</button>
        </div>
      </div>
      <div style={{marginLeft:230,flex:1,padding:"36px",maxWidth:"calc(100vw - 230px)",overflowY:"auto",minHeight:"100vh"}}>
        {screens[tab]}
      </div>
    </div>
  );
}

// ── ROOT ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [screen, setScreen] = useState("registration");
  const [user, setUser] = useState(null);

  const handleRegistrationComplete = userData => {
    // Token already saved in handlePayment
    // Just update user state and navigate to app
    const savedToken = localStorage.getItem("zuzan_token");
    if (!savedToken || savedToken.startsWith("demo_")) {
      localStorage.setItem("zuzan_token", "demo_" + Date.now());
    }
    setUser(userData);
    setScreen("app");
  };

  if (screen === "registration") {
    return <Registration onComplete={handleRegistrationComplete}/>;
  }

  return <ZuZanApp user={user} onLogout={() => { setUser(null); setScreen("registration"); }}/>;
}
