// Successful live history is the retention source, never directory age or build order.
import {readFileSync,readdirSync,readlinkSync,mkdirSync,writeFileSync,renameSync,existsSync} from 'node:fs';
import {join,basename,dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
export const KEEP_LIVE_RELEASES=3;
const safe=value=>typeof value==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(value)&&!value.includes('..');
const read=(file,fallback)=>{try{return readFileSync(file,'utf8');}catch(e){if(e.code==='ENOENT')return fallback;throw e;}};
export function liveHistory(text){
 const history={};
 for(const line of text.split('\n')){
  const m=line.match(/^\S+ (?:PROMOTED|CUTOVER|ROLLED-BACK) ([a-zA-Z0-9_-]+) (?:\S+ )?-> ([a-zA-Z0-9._-]+);/);
  if(m&&safe(m[1])&&safe(m[2]))(history[m[1]]??=[]).push(m[2]);
 }
 return history;
}
export function releaseProtection(root,{extra={}}={}){
 root=resolve(root);const history=liveHistory(read(join(root,'promotions.log'),''));
 const config=JSON.parse(read(join(root,'deploy.json'),'{}'));
 const games=new Set([...Object.keys(config.games||{}),...Object.keys(history),...Object.keys(extra)]);
 let links=[];try{links=readdirSync(join(root,'live'),{withFileTypes:true});}catch(e){if(e.code!=='ENOENT')throw e;}
 for(const f of links)if(f.isSymbolicLink())games.add(f.name);
 const releases={};
 for(const game of games){
  if(!safe(game))throw Error('Invalid game in live release history');
  let current;try{current=basename(readlinkSync(join(root,'live',game)));}catch(e){if(!['ENOENT','EINVAL'].includes(e.code))throw e;}
  const successful=[...new Set([...(history[game]||[])].reverse())].slice(0,KEEP_LIVE_RELEASES);
  // A crash can leave a new pointer before its success log. Keep all three known-good releases as well.
  releases[game]=[...new Set([current,...successful].filter(Boolean))];
  if(extra[game]&&!releases[game].includes(extra[game]))releases[game].push(extra[game]);
  if(releases[game].some(v=>!safe(v)))throw Error('Invalid live release version');
 }
 return {releases,paths:Object.entries(releases).flatMap(([g,vs])=>vs.map(v=>join(root,'releases',g,v)))};
}
export function writeReleaseProtection(root,options){
 const {paths,releases}=releaseProtection(root,options),file=join(root,'protected-releases.json'),tmp=file+'.tmp-'+process.pid;
 mkdirSync(dirname(file),{recursive:true,mode:0o700});writeFileSync(tmp,JSON.stringify({paths})+'\n',{mode:0o600});renameSync(tmp,file);
 return releases;
}
export function previousLiveRelease(root,name,current){
 if(!safe(name)||!safe(current))throw Error('Rollback requires a managed live release');
 const history=liveHistory(read(join(root,'promotions.log'),''));
 const version=[...(history[name]||[])].reverse().find(v=>v!==current);
 if(!version)throw Error('No previous live release recorded');
 if(!existsSync(join(root,'releases',name,version,'.release.json')))throw Error('Previous live release is missing; rollback refused');
 return version;
}
export async function rollbackPrevious({root,name,current,by,reason,apply,log}){
 if(typeof reason!=='string'||!reason.trim()||/[\r\n]/.test(reason)||typeof by!=='string'||!by.trim()||/[\r\n]/.test(by))throw Error('Rollback needs an operator and a one-line reason');
 const previous=previousLiveRelease(root,name,current);
 writeReleaseProtection(root,{extra:{[name]:previous}});
 log(`ROLLBACK-REQUEST ${name} ${current} -> ${previous}; by=${by}; reason=${reason}`);
 if(!await apply(name,previous,'ROLLED-BACK'))throw Error('Rollback failed health checks; original release restored');
 // A pending forward promotion must not silently undo recovery on the next tick.
 const queued=join(root,'queue',name+'.json');
 if(existsSync(queued)){const dest=join(root,'queue','superseded');mkdirSync(dest,{recursive:true});renameSync(queued,join(dest,name+'-'+Date.now()+'.json'));}
 writeReleaseProtection(root);
 return previous;
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
 try{if(process.argv[2]!=='--root'||!process.argv[3])throw Error('usage: release-retention.mjs --root ROOT');console.log(JSON.stringify(releaseProtection(process.argv[3])));}
 catch(error){console.error(error.message);process.exitCode=1;}
}
