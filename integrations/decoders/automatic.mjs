// Apache-2.0 CyberChef API, fixed automatic Magic operation. No caller recipes or code.
import chef from 'cyberchef';
import log from 'loglevel'; log.disableAll();
let diagnosticCount=0; console.log=console.warn=console.error=()=>{diagnosticCount++};
let input='';for await(const b of process.stdin){input+=b;if(input.length>20000)throw Error('Input exceeds 20 KB')}
const v=JSON.parse(input);if(typeof v.text!=='string'||v.text.length>8000)throw Error('Use at most 8,000 characters');
const depth=Math.min(3,Math.max(1,v.depth||3));
const dish=await chef.magic(v.text,{depth,intensiveMode:false,extensiveLanguageSupport:false,crib:''});
const raw=Array.isArray(dish.value)?dish.value:[dish.value];
const candidates=raw.map(c=>({recipe:c.recipe,data:typeof c.data==='string'?c.data.slice(0,8000):c.data, useful:!!c.useful, entropy:c.entropy,
    language_heuristics:(c.languageScores||[]).slice(0,3)}));
candidates.sort((a,b)=>Number(b.useful)-Number(a.useful));
const result={engine:'GCHQ CyberChef',version:'11.5.0',operation:'Magic',depth,returned_candidates:raw.length,
 candidates:candidates.slice(0,60),truncated:raw.length>60,diagnostics_suppressed:diagnosticCount,
 validation:'CANDIDATE TRANSFORMS ONLY; Magic language scores are heuristics, not probabilities of an intentional message, a prediction or authenticity.'};
process.stdout.write(JSON.stringify(result));
