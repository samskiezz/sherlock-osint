import {cp,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const frontend=new URL('../',import.meta.url);
for(const folder of ['wasm','standard_fonts','cmaps']){
 const target=new URL(`public/pdf-assets/${folder}/`,frontend);await mkdir(target,{recursive:true});await cp(fileURLToPath(new URL(`node_modules/pdfjs-dist/${folder}/`,frontend)),fileURLToPath(target),{recursive:true});
}
