// Resume bounded, simple reflection animations through the normal Vibes UI.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('playwright');
const {acquireProfile}=require('./upro-browser-session.cjs');
const [root,requestPath]=process.argv.slice(2);
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const write=(p,v)=>fs.writeFileSync(p,JSON.stringify(v,null,2));
(async()=>{
 const r=read(requestPath),fingerprint=hash(requestPath);
 const validCount=r.profile==='religion-reflection-5m-prototype-v1'?r.items.length===10:r.profile==='religion-reflection-5m-library-v2'&&r.items.length>=1&&r.items.length<=9;
 if(!validCount||!/^https:\/\/vibes\.ai\/projects\/[a-f0-9-]+$/.test(r.project_url))throw Error('Invalid reflection request');
 const output=path.resolve(r.output);if(!/^E:\\/i.test(output))throw Error('Media must stay on E:');fs.mkdirSync(output,{recursive:true});
 const profile=path.join(root,'.runtime/browser-profiles/religion');
 const releaseProfile=await acquireProfile(profile,10000);
 let context,page;
 try{
  context=await chromium.launchPersistentContext(profile,{channel:'chrome',headless:true,locale:'es-ES',acceptDownloads:true,downloadsPath:output});
  page=await context.newPage();
  const cards=()=>page.locator('[data-analytics-id="creation_gallery.thumbnail_click"]');
  const gallery=async()=>{
   await page.goto(r.project_url);await page.waitForTimeout(1500);
   const login=page.getByRole('button',{name:'Iniciar sesión',exact:true});
   await Promise.any([login.waitFor({state:'visible',timeout:30000}),cards().first().waitFor({state:'attached',timeout:30000})]);
   if(await login.isVisible()){
    // Re-enter the already authenticated SSO session; never fill credentials here.
    await login.click();await page.getByText('Proyectos',{exact:true}).first().waitFor({timeout:20000});
    await page.goto(r.project_url);
   }
   await cards().first().waitFor({state:'attached',timeout:30000});await page.waitForLoadState('networkidle',{timeout:10000}).catch(()=>{});
   return cards().evaluateAll(es=>es.map(e=>({id:e.getAttribute('data-analytics-media-id'),video:!!e.querySelector('video[src]'),label:(e.innerText||'').trim()})));
  };
  for(const [i,item] of r.items.entries()){
   const receipt=path.join(output,`animation-${String(i+1).padStart(2,'0')}.json`),file=path.join(output,`native-${String(i+1).padStart(2,'0')}.mp4`);
   let intent=fs.existsSync(receipt)?read(receipt):null;
   if(intent&&intent.request_sha256!==fingerprint)throw Error('Request changed');
   if(intent?.state==='downloaded'){if(hash(file)!==intent.sha256)throw Error('Native changed');continue;}
   let all=await gallery();
   if(!intent){
    if(item.existing_media_id){
     if(!all.some(v=>v.id===item.existing_media_id&&v.video))throw Error('Existing video not present');
     intent={state:'generated',media_id:item.existing_media_id,request_sha256:fingerprint};write(receipt,intent);
    }else{
     if(!/^[A-Za-z0-9_-]+$/.test(item.source_media_id))throw Error('Invalid source identity');
     await page.goto(r.project_url+'/content/'+item.source_media_id);
     await page.getByRole('button',{name:'Manual animate',exact:true}).click();
     const dialog=page.getByRole('dialog');await dialog.getByRole('textbox',{name:'Animate',exact:true}).fill(item.prompt);
     intent={state:'submitting',request_sha256:fingerprint,source_media_id:item.source_media_id,prompt:item.prompt,prior_media_ids:all.map(v=>v.id),started_at:new Date().toISOString()};write(receipt,intent);
     await dialog.getByRole('button',{name:'Animate',exact:true}).click();intent.state='submitted';write(receipt,intent);
     // Keep the editor alive until it commits the animation to the project.
     // Navigating immediately can abandon the editor's asynchronous save.
     await dialog.waitFor({state:'hidden',timeout:15000});
     await page.waitForTimeout(20000);
     await page.getByText('Animating...',{exact:true}).waitFor({state:'hidden',timeout:180000});
     await page.waitForTimeout(2000);
    }
   }
   if(['submitted','submitting'].includes(intent.state)){
    const deadline=Date.now()+180000;let fresh=[];
    do{
     all=await gallery();fresh=all.filter(v=>v.video&&!intent.prior_media_ids.includes(v.id));
     if(item.source_filename) fresh=fresh.filter(v=>v.label===item.source_filename);
     if(fresh.length>1)throw Error('Ambiguous animation identity');
     if(fresh.length===1)break;await page.waitForTimeout(5000);
    }while(Date.now()<deadline);
    if(fresh.length!==1)throw Error('Animation remains unresolved; do not repeat submission');
    intent.state='generated';intent.media_id=fresh[0].id;write(receipt,intent);
   }
   if(intent.state!=='generated')throw Error('Unexpected state');
   if(fs.existsSync(file))throw Error('Reconcile existing file before download');
   const selected=cards().and(page.locator(`[data-analytics-media-id="${intent.media_id}"]`));
   // Download the exact media URL exposed by this identified gallery video.
   // The site's download button can close headless Chrome before emitting its event.
   const source=await selected.locator('video').getAttribute('src');
   if(!source||new URL(source).protocol!=='https:')throw Error('Missing HTTPS video source');
   const response=await context.request.get(source,{timeout:120000});
   if(!response.ok()||!/^video\//i.test(response.headers()['content-type']||''))throw Error('Media transfer did not return video');
   const bytes=await response.body();if(bytes.length<10000)throw Error('Incomplete media transfer');
   fs.writeFileSync(file,bytes,{flag:'wx'});await response.dispose();
   intent={...intent,state:'downloaded',path:file,sha256:hash(file),completed_at:new Date().toISOString()};write(receipt,intent);
   console.log(JSON.stringify({block:i+1,state:intent.state,path:file}));
  }
 }catch(error){
  if(page){try{const u=new URL(page.url());write(path.join(output,'failure-'+Date.now()+'.json'),{message:error.message,page:u.origin+u.pathname,body:(await page.locator('body').innerText({timeout:3000})).slice(0,5000),card_count:await page.locator('[data-analytics-id="creation_gallery.thumbnail_click"]').count()});}catch{}}
  throw error;
 }finally{if(context)await context.close();await releaseProfile();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
