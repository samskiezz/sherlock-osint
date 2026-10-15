"""Check the deployed private access path using in-memory service credentials."""
import hashlib
import json
from pathlib import Path
import re
import sys
import termios
import httpx

settings=termios.tcgetattr(sys.stdin);settings[3]&=~termios.ECHO;termios.tcsetattr(sys.stdin,termios.TCSANOW,settings)
print('Ready for private verification configuration on hidden stdin',flush=True)
config=json.loads(sys.stdin.readline())
client=httpx.Client(base_url=config['url'],headers={'OAI-Sites-Authorization':'Bearer '+config['service_token'],'X-Sherlock-Relay-Key':config['relay_secret']},timeout=100,follow_redirects=False)
def get(path):
    """Exercise the authenticated service probe through the exact same request relay."""
    response=client.get('/__sherlock_relay/check',params={'path':path})
    if response.status_code!=200:
        print(json.dumps({'path':path,'status':response.status_code,'body':response.text[:300]}),flush=True)
        raise RuntimeError('Private access verification failed')
    return response
html=get('/');assert '<html' in html.text.lower() and 'SHERLOCK' in html.text
scripts=re.findall(r'src="(/assets/[^\"]+\.js)"',html.text)
assert scripts
asset=get(scripts[0]);assert len(asset.content)>10000
items=get('/api/evidence?summary=true').json()
image=next(x for x in items if x.get('mime','').startswith('image/') and x.get('sha256'))
image_bytes=get('/api/evidence/'+image['id']+'/file').content
assert hashlib.sha256(image_bytes).hexdigest()==image['sha256']
pdf=next(x for x in items if x.get('mime')=='application/pdf' and x.get('sha256'))
pdf_bytes=get('/api/evidence/'+pdf['id']+'/file').content
assert pdf_bytes.startswith(b'%PDF') and hashlib.sha256(pdf_bytes).hexdigest()==pdf['sha256']
media=get('/api/media/reports?limit=12').json()
briefing=get('/api/case/briefing').json();assert briefing['documented_count']>=3
breakdown=get('/api/case/breakdown').json();assert len(breakdown['topics'])>=9
dossier=get('/api/dossiers/verification').json()['dossiers'][0];assert dossier['claim_units']==141
assert 'board-and-breakdown' in asset.text


cipher=get('/api/case/workspaces/cipher').json();assert cipher['enabled'] and cipher['results']
assert 'The case, broken down' in asset.text and 'Automatic cipher and gematria analysis' not in html.text

unauth=httpx.get(config['url'],timeout=30,follow_redirects=False)
result={'url':config['url'],'application_html_status':html.status_code,'frontend_script_status':asset.status_code,'frontend_script_bytes':len(asset.content),'image_original':{'id':image['id'],'bytes':len(image_bytes),'sha256_verified':True},'pdf_original':{'id':pdf['id'],'bytes':len(pdf_bytes),'sha256_verified':True},'media_reports_total':media['total'],'briefing_documented_statements':briefing['documented_count'],'case_breakdown_threads':len(breakdown['topics']),'dossier_claim_units':dossier['claim_units'],'dossier_counts':dossier['counts'],'default_board_with_breakdown':True,'automatic_cipher_saved_results':len(cipher['results']),'unauthenticated_status':unauth.status_code,'private_signin_boundary':unauth.status_code in (301,302,303,307,308,401,403),'verification_path':'Owner-private Sites service access plus relay secret; original bytes fetched from the real running backend, not a snapshot.'}
assert result['private_signin_boundary']
Path('/workspace/sherlock-osint/artifacts/private-access-live-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result),flush=True)
