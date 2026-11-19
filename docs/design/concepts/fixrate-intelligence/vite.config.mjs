import {defineConfig} from '../../../../frontend/node_modules/vite/dist/node/index.js';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('.',import.meta.url));
export default defineConfig({root,resolve:{alias:[{find:'react-dom/client',replacement:path.resolve(root,'../../../../frontend/node_modules/react-dom/client.js')},{find:'react',replacement:path.resolve(root,'../../../../frontend/node_modules/react/index.js')}]},build:{outDir:path.resolve(root,'../../../../var/fixrate-intelligence-dist'),emptyOutDir:false},server:{host:'127.0.0.1',port:9031,strictPort:true,fs:{allow:[path.resolve(root,'../../../..')]}},preview:{host:'127.0.0.1',port:9031,strictPort:true}});
