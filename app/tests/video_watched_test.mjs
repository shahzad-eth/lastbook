// Exercise the shipped progress/watched storage together. Browser checks separately
// distinguish actual playback, paused scrubbing and saved-moment navigation.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(process.argv[2] || new URL('../../web/app.js', import.meta.url), 'utf8');
const start = app.indexOf('// Video watch progress:');
const end = app.indexOf('\n/* ', start);
assert.ok(start >= 0 && end > start, 'shipped progress storage is present');
const source = app.slice(start, end);
let checks = 0, failures = 0;

function open(progress = {}, watched = {}) {
  const saved = JSON.stringify([{key:'m:video-a:85',kind:'video-moment',videoId:'video-a',time:85,title:'Final detail'}]);
  const memory = new Map([['vprog',JSON.stringify(progress)],['vwatched',JSON.stringify(watched)],['saved',saved]]);
  const writes = [];
  const context = vm.createContext({store:{
    get(key, fallback) { return JSON.parse(memory.get(key) || 'null') ?? fallback },
    set(key, value) { writes.push(key);memory.set(key,JSON.stringify(value)) },
  }});
  vm.runInContext(source, context, {filename:'progress storage from app.js'});
  return {context,memory,writes,saved};
}

function test(name, run) {
  try { run();checks++;console.log('PASS '+name) }
  catch(e) { failures++;console.error('FAIL '+name+'\n'+e.message) }
}

for (const t of [85,90]) {
  test('a fresh paused seek to '+t+' does not imply completion', () => {
    const page=open();
    page.context.setVprog('video-a',{t,d:90,title:'Workshop demonstration'});
    assert.equal(page.context.isWatched('video-a',null,{duration:90}),false);
    assert.equal(JSON.parse(page.memory.get('vprog'))['video-a'].t,t);
  });
}
test('legacy completed progress survives replaying an earlier moment', () => {
  const page=open({'video-a':{t:85,d:90}});
  assert.equal(page.context.isWatched('video-a',null,{duration:90}),true);
  page.context.setVprog('video-a',{t:31,d:90});
  assert.equal(page.context.isWatched('video-a',null,{duration:90}),true);
});
test('legacy incomplete progress stays unwatched after a near-end seek', () => {
  const page=open({'video-a':{t:31,d:90}});
  page.context.setVprog('video-a',{t:85,d:90});
  assert.equal(page.context.isWatched('video-a',null,{duration:90}),false);
});
test('resolved media duration can preserve legacy completion', () => {
  const page=open({'video-a':{t:85}});
  page.context.setVprog('video-a',{t:31,d:90});
  assert.equal(page.context.isWatched('video-a',null,{duration:90}),true);
});
test('an explicit unwatched choice wins over high progress', () => {
  const page=open({'video-a':{t:85,d:90}},{'video-a':false});
  page.context.setVprog('video-a',{t:89,d:90});
  assert.equal(page.context.isWatched('video-a',null,{duration:90}),false);
});
test('an explicit watched choice survives rewinding', () => {
  const page=open({}, {'video-a':true});
  page.context.setVprog('video-a',{t:31,d:90});
  assert.equal(page.context.isWatched('video-a',null,{duration:90}),true);
});
test('explicit completion survives pruning the resume list', () => {
  const page=open({'video-a':{t:31,d:90,at:1}}, {'video-a':true});
  for(let i=0;i<61;i++)page.context.setVprog('other-'+i,{t:20,d:90});
  assert.equal(Object.keys(JSON.parse(page.memory.get('vprog'))).length,60);
  assert.equal(JSON.parse(page.memory.get('vprog'))['video-a'],undefined);
  assert.equal(page.context.isWatched('video-a',null,{duration:90}),true);
});
test('progress updates preserve saved moments and another video choice', () => {
  const page=open({}, {'video-b':true});
  page.context.setVprog('video-a',{t:85,d:90});
  assert.equal(page.memory.get('saved'),page.saved);
  assert.equal(page.context.isWatched('video-b'),true);
  assert.ok(!page.writes.includes('saved'));
});
console.log(JSON.stringify({checks,failures}));
if(failures)process.exitCode=1;
