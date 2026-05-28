from main import app 
from fastapi.testclient import TestClient 
client = TestClient(app) 
res = client.post('/auth/register', json={'company_name':'Test','first_name':'Test','last_name':'User','email':'abc@test.co.za','password':'Test1234','plan':'starter','billing_cycle':'monthly','payroll_enabled':False,'employee_count':0}) 
print(res.status_code, res.text) 
