import {spawn} from 'node:child_process';
import {mkdir} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const video=resolve(dirname(fileURLToPath(import.meta.url)),'..'),temporary=resolve(video,'../.codex/video/tmp');
await mkdir(temporary,{recursive:true});
const child=spawn(process.execPath,[resolve(video,'node_modules/@remotion/cli/remotion-cli.js'),'studio','src/index.ts','--port=17680','--no-open'],{cwd:video,stdio:'inherit',windowsHide:true,env:{...process.env,TEMP:temporary,TMP:temporary,TMPDIR:temporary}});
child.on('exit',code=>process.exit(code??1));
