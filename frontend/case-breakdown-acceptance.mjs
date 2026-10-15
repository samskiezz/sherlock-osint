import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));process.env.PLAYWRIGHT_BROWSERS_PATH ||= root+'.browsers';
const {chromium}=await import('playwright');const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
try{
 const page=await browser.newPage({viewport:{width:1720,height:1200}}),errors=[],posts=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST'&&/\/api\/(automation|research|visual|autopilot|forensics)/.test(new URL(r.url()).pathname))posts.push(r.url());});
 await page.goto('http://127.0.0.1:8010',{waitUntil:'domcontentloaded'});
 const c=JSON.parse(await readFile(root+'data/foundation-secrets/admin-login.json','utf8'));
 await page.getByLabel('Username',{exact:true}).fill(c.username);await page.getByLabel('Password',{exact:true}).fill(c.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await page.getByRole('heading',{name:'The case, broken down',exact:true}).waitFor({timeout:45000});await page.locator('.case-thread').first().waitFor({timeout:45000});
 const count=await page.locator('.case-thread').count();if(count!==9)throw Error('Missing case threads');
 if(await page.locator('.content-area input:visible,.content-area select:visible,.content-area textarea:visible').count())throw Error('Manual forms on the default case breakdown');
 await page.screenshot({path:root+'artifacts/case-breakdown-home.png',fullPage:true});
 const tabs=[];
 for(let i=0;i<count;i++){
  const card=page.locator('.case-thread').nth(i);const title=await card.locator('h3').innerText();await card.locator('.case-thread-title').click();
  await page.getByRole('navigation',{name:'Case report sections'}).waitFor();
  const connections=await page.locator('.case-connection').count();
  await page.getByRole('navigation',{name:'Case report sections'}).getByRole('button',{name:/^Proof/}).click();
  const records=await page.locator('.case-document').count();
  await page.getByRole('navigation',{name:'Case report sections'}).getByRole('button',{name:/^Analysis/}).click();
  const analyses=await page.locator('.case-analysis-card').count();
  tabs.push({title,connections,preserved_records:records,saved_analyses:analyses});
  await page.getByRole('button',{name:'All case threads',exact:true}).click();
 }
 await page.locator('.case-thread-title').filter({hasText:'Mondaloy'}).click();
 await page.locator('.connection-proof blockquote button').first().click();await page.locator('aside.inspector').waitFor();await page.screenshot({path:root+'artifacts/case-breakdown-proof.png',fullPage:true});await page.getByRole('button',{name:'Toggle inspector',exact:true}).click();
 await page.reload();await page.getByRole('heading',{name:'Mondaloy · inventors & patents',exact:true}).waitFor({timeout:45000});
 await page.getByRole('button',{name:'All case threads',exact:true}).click();
 await page.locator('.case-thread-title').filter({hasText:'Images'}).click();await page.getByRole('navigation',{name:'Case report sections'}).getByRole('button',{name:/^Analysis/}).click();
 await page.locator('.case-analysis-card').first().getByRole('button',{name:'Read full analysis',exact:true}).click();await page.getByRole('heading',{name:'How the analysis reached this result',exact:true}).waitFor({timeout:45000});
 await page.locator('.case-image-sequence img').first().waitFor();await page.screenshot({path:root+'artifacts/case-breakdown-analysis.png',fullPage:true});
 if(errors.length||posts.length)throw Error(JSON.stringify({errors,posts}));
 const out={case_threads:count,sections_verified:tabs,source_passage_opens_inspector:true,chapter_link_survives_reload:true,full_visual_analysis_opened:true,no_manual_analysis_requests:true,console_errors:errors,screenshots:['case-breakdown-home.png','case-breakdown-proof.png','case-breakdown-analysis.png']};await writeFile(root+'artifacts/case-breakdown-browser.json',JSON.stringify(out,null,2));console.log(JSON.stringify(out));
}finally{await browser.close();}
