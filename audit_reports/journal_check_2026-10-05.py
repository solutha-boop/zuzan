import sqlite3,sys,json
c=sqlite3.connect("file:zuzan.db?mode=ro",uri=True)
def q(s): return c.execute(s).fetchall()
print("status vals inv",q("select distinct status from invoices"))
print("po status",q("select distinct status from purchase_orders"))
print("counts",q("select count(*) from invoices"),q("select count(*) from expenses"),q("select count(*) from purchase_orders"),q("select source,count(*) from journal_entries group by source"))
def chk(name,sql):
    r=q(sql); print("CHECK",name,len(r)); print(json.dumps(r))
J=lambda src,t:f"not exists (select 1 from journal_entries j where j.source='{src}' and j.source_id={t}.id)"
chk(1,f"select id,company_id,status from invoices where lower(status)!='draft' and {J('invoice','invoices')}")
chk(2,f"select id,company_id,status from invoices where lower(status)='paid' and {J('invoice_payment','invoices')}")
chk(3,f"select id,company_id from expenses where {J('expense','expenses')}")
chk(4,f"select id,company_id,status from purchase_orders where lower(status) in ('received','partial','paid') and {J('purchase_order','purchase_orders')}")
chk(5,f"select id,company_id,status from purchase_orders where lower(status)='paid' and {J('po_payment','purchase_orders')}")
