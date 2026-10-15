"""Exercise real stored originals, hash-preserving image checks and durable screening."""
import hashlib,json,time
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1]
c=httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,timeout=90)
evidence=c.get('/api/evidence').json()
images=[e for e in evidence if e['fileUrl'] and e['mime'].startswith('image/')]
checks=[]
for e in images:
    original=c.get(e['fileUrl']).content
    response=c.post(f"/api/evidence/{e['id']}/process");response.raise_for_status(); enriched=response.json()
    assert hashlib.sha256(original).hexdigest()==enriched['sha256']
    assert c.get(enriched['fileUrl']).content==original
    assert (root/'data/originals'/enriched['sha256']).stat().st_mode & 0o222==0
    meta=enriched['metadata']; assert meta['sandbox']['network']=='none'
    views=[]
    for kind in meta['image_forensics']['views']:
        r=c.get(f"/api/evidence/{e['id']}/diagnostic/{kind}");r.raise_for_status()
        assert hashlib.sha256(r.content).hexdigest()==meta['derivative_hashes'][kind+'.png'];views.append(kind)
    run=c.post(f"/api/forensics/{e['id']}/screen");run.raise_for_status(); second=c.post(f"/api/forensics/{e['id']}/screen").json(); assert second['id']==run.json()['id']
    checks.append({'id':e['id'],'title':e['title'],'original_sha256':enriched['sha256'],'original_unchanged':True,'read_only':True,'views':views,'anomaly_indicators':meta['image_forensics']['anomaly_indicators'],'run_id':second['id'],'attempts':second['data']['attempt_count']})
exp=c.post('/api/cipher',json={'input':'LXFOPVEFRNHR','method':'vigenere','parameters':{'key':'LEMON'},'control':'ABCDEFGHIJKL','holdout_input':'DSE','holdout_expected':'SOS'});exp.raise_for_status()
assert exp.json()['output']=='ATTACKATDAWN'; assert exp.json()['holdout']['status']=='MATCH';assert exp.json()['validation']=='UNVALIDATED'
word=c.post('/api/cipher',json={'input':'listen','method':'scrabble','parameters':{'exact':True}});word.raise_for_status();assert 'silent' in word.json()['output']
result={'live_service':c.get('/api/health').json()['version'],'real_original_images':checks,'vigenere':exp.json(),'scrabble':word.json(),'automatic_screening':c.get('/api/forensics').json()['settings']}
(root/'artifacts/digital-forensics-live-v5.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'images_verified':len(checks),'originals_unchanged':True,'cipher_holdout':'MATCH','word_puzzle':'passed'}))
