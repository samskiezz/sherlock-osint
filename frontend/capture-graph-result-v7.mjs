import {chromium} from 'playwright';
const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
try {
 const page=await browser.newPage({viewport:{width:1800,height:1200}});
 await page.goto('http://127.0.0.1:8000',{waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:'Tradecraft & hypotheses',exact:true}).click();
 const data=await (await page.request.get('http://127.0.0.1:8000/api/tradecraft')).json();
 const record=data.records.find(r=>r.data.output?.library==='NetworkX 3.7');
 if(!record)throw Error('No saved real graph calculation');
 await page.locator('.experiment-history').filter({hasText:record.id}).click();
 await page.locator('.experiment-result').scrollIntoViewIfNeeded();
 await page.screenshot({path:'../artifacts/source-graph-result-v7.png',fullPage:true});
} finally {await browser.close();}
