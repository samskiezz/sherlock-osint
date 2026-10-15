import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
process.env.PLAYWRIGHT_BROWSERS_PATH ||= root+'.browsers';
const {chromium}=await import('playwright');
const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
try {
 const page=await browser.newPage({viewport:{width:1720,height:1100}}), errors=[], analysisPosts=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(r.method()==='POST'&&/\/api\/(automation|autopilot|visual|media|forensics|research)/.test(new URL(r.url()).pathname))analysisPosts.push(r.url());});
 await page.goto('http://127.0.0.1:8010',{waitUntil:'domcontentloaded'});
 const credentials=JSON.parse(await readFile(root+'data/foundation-secrets/admin-login.json','utf8'));
 await page.getByLabel('Username',{exact:true}).fill(credentials.username);
 await page.getByLabel('Password',{exact:true}).fill(credentials.password);
 await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await page.getByRole('heading',{name:'What the evidence tells us',exact:true}).waitFor({timeout:45000}).catch(async e=>{console.log(JSON.stringify({headings:await page.locator('h1,h2').allTextContents(),errors,url:page.url()}));await page.screenshot({path:root+'artifacts/briefing-browser-failure.png'});throw e;});
 await page.locator('.briefing-result').first().waitFor();
 if(await page.locator('.media-review-card:visible').count())throw Error('Gallery still dominates default view');
 if(await page.locator('.content-area textarea:visible,.content-area input:visible').count())throw Error('Home requires manual input');
 const facts=await page.locator('[data-result-kind="DOCUMENTED"]').count();
 if(facts<3)throw Error('Missing documented results');
 await page.screenshot({path:root+'artifacts/case-briefing.png',fullPage:true});
 await page.getByRole('button',{name:'Mark results read',exact:true}).click();
 await page.getByRole('button',{name:'Unread (0)',exact:true}).waitFor();
 await page.reload();
 await page.getByRole('button',{name:'Unread (0)',exact:true}).waitFor();
 await page.locator('.briefing-citation button').first().click();
 await page.locator('aside.inspector').waitFor();
 await page.screenshot({path:root+'artifacts/briefing-source-inspector.png',fullPage:true});
 await page.getByRole('button',{name:'Toggle inspector',exact:true}).click();
 await page.getByRole('button',{name:'Advanced tools',exact:true}).click();
 const labels=['Forensic analysis','Automation control','Evidence retrieval','Patent intelligence','Public photo corpus','Tradecraft & hypotheses','Sources','Onion document browser','Continuous watch','Cipher laboratory','Archive comparison','Investigator'];
 const checked=[];
 for(const label of labels){
  await page.locator('.sidebar nav').getByRole('button',{name:label,exact:true}).click();
  await page.locator('.automatic-results .automatic-status').waitFor({timeout:45000});
  if(await page.locator('.content-area textarea:visible,.content-area input:visible,.content-area select:visible').count())throw Error(label+' still exposes manual input as default');
  const n=await page.locator('.automatic-output .briefing-result').count();
  checked.push({tab:label,default:'automatic saved results',manual_inputs_visible:0,completed_results:n});
  if(label==='Cipher laboratory'){
   await page.screenshot({path:root+'artifacts/automatic-cipher-workspace.png',fullPage:true});
   const response=page.waitForResponse(r=>r.url().includes('/api/case/receipts/')&&r.status()===200);
   await page.locator('.saved-automatic-output > summary').first().click();
   await response;
   await page.locator('.saved-automatic-output table').first().waitFor();
  }
 }
 if(errors.length || analysisPosts.length)throw Error(JSON.stringify({errors,analysisPosts}));
 await writeFile(root+'artifacts/briefing-automatic-browser.json',JSON.stringify({authenticated:true,documented_results: facts,automatic_tabs:checked,no_analysis_enqueued_by_navigation:true,unread_state_survives_reload:true,saved_receipt_opened:true,console_errors:errors,screenshots:['case-briefing.png','briefing-source-inspector.png','automatic-cipher-workspace.png']},null,2));
 console.log(JSON.stringify({documented_results:facts,automatic_tabs_verified:checked.length,console_errors:errors.length,analysis_posts:analysisPosts.length}));
}finally{await browser.close();}
