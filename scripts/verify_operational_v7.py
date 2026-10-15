"""Verify live originals, new analytics, graph monitors and reports across a real restart."""
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import time
import zipfile
from pathlib import Path
import httpx
import fitz

root=Path(__file__).resolve().parents[1]
c=httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,timeout=60)
before=c.get('/api/export/json').json(); monitors=c.get('/api/analysis-monitors').json()
audit_before=c.get('/api/audit/verify').json(); assert audit_before['valid']
assert monitors and all(m['data']['fingerprint'] for m in monitors)
pid=int((root/'data/service-v2.pid').read_text())
assert 'uvicorn backend.app:app' in subprocess.check_output(['ps','-p',str(pid),'-o','args='],text=True)
os.kill(pid,signal.SIGTERM)
for _ in range(80):
    try:c.get('/api/health');time.sleep(.1)
    except httpx.RequestError:break
else:raise AssertionError('Old service did not stop')
with (root/'data/service-v2.log').open('ab') as output:
    service=subprocess.Popen([str(root/'start.sh')],cwd=root,stdout=output,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
(root/'data/service-v2.pid').write_text(str(service.pid))
for _ in range(100):
    try:
        response=c.get('/api/health')
        if response.status_code==200:break
    except httpx.RequestError:pass
    time.sleep(.2)
else:raise AssertionError('Service did not restart')
after=c.get('/api/export/json').json()
assert all(b in after['boards'] for b in before['boards']), 'Board layout/content changed during restart'
assert {r['id'] for r in before['analytic_records']} <= {r['id'] for r in after['analytic_records']}
current=c.get('/api/analysis-monitors').json()
for old in monitors:
    restored=next(m for m in current if m['id']==old['id'])
    assert restored['enabled']==old['enabled'] and restored['data']['fingerprint']==old['data']['fingerprint']
    assert restored['next_due']==old['next_due']
    unchanged=c.post('/api/analysis-monitors/'+old['id']+'/run').json()
    assert unchanged['data']['status']=='UNCHANGED'
audit=c.get('/api/audit/verify').json();assert audit['valid']
assert audit['legacy_records_through']==audit_before['legacy_records_through']
originals=[]
for e in after['evidence']:
    if e.get('sha256'):
        path=root/'data/originals'/e['sha256']
        valid=hashlib.sha256(path.read_bytes()).hexdigest()==e['sha256'];ro=not(path.stat().st_mode & 0o222)
        assert valid and ro
        originals.append({'id':e['id'],'sha256':e['sha256'],'bytes':path.stat().st_size,'hash_verified':valid,'read_only':ro})
for format in ('pdf','docx'):
    response=c.get('/api/export/'+format);response.raise_for_status()
    path=root/f'artifacts/looking-glass-report-v7.{format}';path.write_bytes(response.content)
with fitz.open(root/'artifacts/looking-glass-report-v7.pdf') as d:
    pages=d.page_count;text=''.join(p.get_text() for p in d)
    assert 'EV-32234078df6a' in text and 'NOT IMPLEMENTED' in text and 'PROVISIONAL' in text
with zipfile.ZipFile(root/'artifacts/looking-glass-report-v7.docx') as z:
    assert b'EV-32234078df6a' in z.read('word/document.xml')
methods=c.get('/api/tradecraft').json()['methods']
from collections import Counter
report={'version':response.headers.get('content-type'),'service_version':c.get('/api/health').json()['version'], 'actual_restart':True,
    'board_layouts_preserved':True,'analysis_records_preserved':True,'monitor_state_and_schedule_preserved':True,'unchanged_graph_deduplicated':True,
    'method_counts':dict(Counter(m['implementation'] for m in methods)), 'original_files_verified':len(originals),
    'original_bytes':sum(e['bytes'] for e in originals),'originals':originals,'audit_chain':audit,'pdf_pages':pages,'pdf_and_docx_opened':True,
    'research_campaigns':len(after['research_campaigns']), 'onion_status':c.get('/api/onion/status').json()}
(root/'artifacts/operational-restart-v7.json').write_text(json.dumps(report,indent=2))
anchor=c.get('/api/audit/anchor');anchor.raise_for_status();(root/'artifacts/looking-glass-audit-anchor-v7.json').write_bytes(anchor.content)
print(json.dumps({k:v for k,v in report.items() if k not in ('originals','onion_status')},indent=2))
