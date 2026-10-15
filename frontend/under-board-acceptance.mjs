import {readFile,writeFile} from 'node:fs/promises';import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));process.env.PLAYWRIGHT_BROWSERS_PATH ||= root+'.browsers';const {chromium}=await import('playwright');const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
try{
 const page=await browser.newPage({viewport:{width:1720,height:1200}}),errors=[],posts=[],catalogues=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST'&&/\/api\/(automation|research|visual|autopilot|forensics)/.test(new URL(r.url()).pathname))posts.push(r.url());if(new URL(r.url()).pathname==='/api/evidence')catalogues.push(r.url());});
 await page.goto('http://127.0.0.1:8010',{waitUntil:'domcontentloaded'});const c=JSON.parse(await readFile(root+'data/foundation-secrets/admin-login.json','utf8'));await page.getByLabel('Username',{exact:true}).fill(c.username);await page.getByLabel('Password',{exact:true}).fill(c.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await page.getByRole('heading',{name:'Evidence board',exact:true,level:1}).waitFor({timeout:45000});await page.locator('.react-flow__node').first().waitFor();await page.getByRole('heading',{name:'Which claims have actually been checked?',exact:true}).waitFor({timeout:45000});await page.locator('.under-board .case-thread').first().waitFor();
 const canvas=await page.locator('.board-and-breakdown > .canvas').boundingBox(),below=await page.locator('.under-board').boundingBox();if(canvas.height<300||below.y<canvas.y+canvas.height-2)throw Error('Case breakdown is not underneath the real board');
 if(await page.locator('.content-area textarea:visible,.content-area select:visible,.content-area input:visible').count())throw Error('Manual inputs on the default board');
 await page.screenshot({path:root+'artifacts/board-with-breakdown.png',fullPage:true});
 await page.locator('.scope-audit > summary').click();
 await page.waitForFunction(()=>document.querySelectorAll('.scope-gap-list article').length>=50);
 const readableAudit=await page.locator('.scope-gap-list article').count();
 await page.locator('.scope-audit > summary').click();
 await page.getByRole('button',{name:'Read claim-by-claim verification',exact:true}).click();await page.locator('.dossier-claim').first().scrollIntoViewIfNeeded();
 const visible=await page.locator('.dossier-claim').count();if(visible!==12)throw Error('Dossier claims are missing');
 const supported=page.locator('.dossier-claim').filter({hasText:'Cole Tomas Allen, 31, of Torrance'});await supported.getByRole('button',{name:/supporting passage/}).click();await supported.locator('.dossier-proof blockquote button').first().click();await page.locator('aside.inspector').waitFor();await page.screenshot({path:root+'artifacts/dossier-source-proof.png',fullPage:true});await page.getByRole('button',{name:'Toggle inspector',exact:true}).click();
 await page.getByRole('button',{name:'Has supporting passages',exact:true}).click();await page.locator('.dossier-claim').filter({hasText:'10 times the heat'}).first().scrollIntoViewIfNeeded();await page.screenshot({path:root+'artifacts/dossier-partial-support.png',fullPage:true});
 await page.getByRole('button',{name:'Hide claim list',exact:true}).click();await page.locator('.under-board .case-thread-title').filter({hasText:'EU Time Machine'}).click();await page.getByRole('heading',{name:'EU Time Machine · historical digitisation',exact:true}).waitFor();
 await page.getByRole('navigation',{name:'Case report sections'}).getByRole('button',{name:/^Proof/}).click();const originals=await page.locator('.under-board .case-document').count();if(!originals)throw Error('Official EU originals are missing');
 const gapResponse=await page.request.get('http://127.0.0.1:8010/api/delivery/gaps');const gaps=await gapResponse.json();if(gaps.items.length<50)throw Error('Thread audit is missing');
 if(catalogues.some(u=>!u.includes('summary=true')))throw Error('Board fetched full extracted corpus');if(errors.length||posts.length)throw Error(JSON.stringify({errors,posts}));
 const result={default_view:'Evidence board',breakdown_underneath_canvas:true,canvas_height:canvas.height,visible_dossier_claims:visible,source_passage_opens_inspector:true,eu_original_records:originals,request_audit_groups:gaps.items.length,readable_audit_rows:readableAudit,compact_card_catalogue:true,no_analysis_started_by_reading:true,console_errors:errors,screenshots:['board-with-breakdown.png','dossier-source-proof.png','dossier-partial-support.png']};await writeFile(root+'artifacts/under-board-browser.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
