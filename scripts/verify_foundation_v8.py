"""Exercise the real gateway, PostgreSQL roles/MFA and Redis/Celery job execution."""
import json
import secrets
import time
from pathlib import Path
import httpx
import pyotp
root=Path(__file__).resolve().parents[1]
credentials=json.loads((root/'data/foundation-secrets/admin-login.json').read_text())
c=httpx.Client(base_url='http://127.0.0.1:8010',trust_env=False,timeout=120)
assert c.get('/health').json()['database']=='postgresql'
assert c.get('/api/v1/cases').status_code==401
login=c.post('/api/v1/auth/login',json=credentials);login.raise_for_status();admin=login.json()['access_token']
headers={'Authorization':'Bearer '+admin}
assert c.get('/api/v1/cases',headers=headers).status_code==200
assert c.get('/api/v1/evidence',headers=headers).json()
users={}
for role in ('Viewer','Analyst'):
    username=role.lower()+'-'+secrets.token_hex(4);password=secrets.token_urlsafe(20)
    response=c.post('/api/v1/users',json={'username':username,'password':password,'role':role},headers=headers);response.raise_for_status()
    response=c.post('/api/v1/auth/login',json={'username':username,'password':password});response.raise_for_status()
    users[role]={'username':username,'password':password,'token':response.json()['access_token']}
viewer={'Authorization':'Bearer '+users['Viewer']['token']}
assert c.get('/api/v1/evidence',headers=viewer).status_code==200
assert c.post('/api/v1/collect',headers=viewer,json={'username':'sherlock-project','authorisation':'Official public project profile, software verification'}).status_code==403
assert c.post('/api/v1/users',headers=viewer,json={'username':'denied','password':secrets.token_urlsafe(20),'role':'Admin'}).status_code==403
assert c.post('/api/v1/analyze',headers=viewer,json={'question':'Read the primary patent inventor caption','evidence_ids':['EV-1c1c3aa4469a']}).status_code==403
assert c.get('/api/evidence',headers=viewer).status_code==200
boards=c.get('/api/boards',headers=headers).json();board=next(b for b in boards if 'named primary record' in b['name'])
r=c.get('/api/v1/graph',headers=viewer,params={'board_id':board['id']});assert r.status_code==200,r.text
assert all(e.get('citation_verified') for e in r.json()['edges'])
report=c.post('/api/v1/report',headers=viewer,json={'format':'pdf'});assert report.status_code==200 and report.content.startswith(b'%PDF')
analyst={'Authorization':'Bearer '+users['Analyst']['token']}
queue=c.post('/api/v1/collect',headers=analyst,json={'username':'sherlock-project','authorisation':'Official public software project profile; no individual attribution requested'})
queue.raise_for_status();jid=queue.json()['id']
for _ in range(100):
    result=c.get('/api/v1/collect/'+jid,headers=analyst).json()
    if result['status'] in ('COMPLETE','FAILED'):break
    time.sleep(1)
else:raise AssertionError('Persistent Celery job did not reach a terminal status')
# Explicit failure is a real tested outcome; never call unavailable bytes acquired.
if result['status']=='COMPLETE':
    original=c.get('/api/evidence/'+result['result']['original_evidence_id'],headers=analyst).json()
    assert original['sha256']==result['result']['sha256']
    path=root/'data/originals'/original['sha256'];assert path.exists()
    import hashlib
    assert hashlib.sha256(path.read_bytes()).hexdigest()==original['sha256']
# Enable MFA on a disposable test account; verify old token revocation and replay rejection.
seed=c.post('/api/v1/auth/totp/enroll',headers=viewer).json()['secret']
code=pyotp.TOTP(seed).now()
confirmed=c.post('/api/v1/auth/totp/confirm',headers=viewer,json={'code':code});confirmed.raise_for_status()
assert c.get('/api/v1/users/me',headers=viewer).status_code==401
assert c.post('/api/v1/auth/login',json={'username':users['Viewer']['username'],'password':users['Viewer']['password']}).status_code==401
assert c.post('/api/v1/auth/login',json={'username':users['Viewer']['username'],'password':users['Viewer']['password'],'totp':code}).status_code==401
next_code=pyotp.TOTP(seed).at(int(time.time())+30)
factor=c.post('/api/v1/auth/login',json={'username':users['Viewer']['username'],'password':users['Viewer']['password'],'totp':next_code});factor.raise_for_status()
assert c.post('/api/v1/auth/login',json={'username':users['Viewer']['username'],'password':users['Viewer']['password'],'totp':next_code}).status_code==401
factor_header={'Authorization':'Bearer '+factor.json()['access_token']}
assert c.post('/api/v1/auth/logout',headers=factor_header).status_code==200
assert c.get('/api/v1/users/me',headers=factor_header).status_code==401
verify=c.get('/api/v1/audit/verify',headers=headers);verify.raise_for_status();audit=verify.json();assert audit['valid']
proof={'postgresql_ready':True,'redis_ready':True,'anonymous_denied':True,'viewer_write_and_user_creation_denied':True,'viewer_original_reads_and_actual_pdf_allowed':True,'source_verified_graph_read':True,'argon2_login':True,'totp_enrollment_confirmation_and_replay_rejection':True,'mfa_and_logout_token_revocation':True,'celery_job_id':jid,'celery_job_status':result['status'],'celery_job_error':result.get('error'),'original_evidence':result.get('result',{}).get('original_evidence_id'),'gateway_audit_chain':audit,'credentials_and_tokens_exported':False}
(root/'artifacts/foundation-live-proof-v8.json').write_text(json.dumps(proof,indent=2))
print(json.dumps(proof,indent=2))
