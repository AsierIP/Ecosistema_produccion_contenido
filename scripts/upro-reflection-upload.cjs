// Upload local reference images once, preserving uncertain submissions for reconciliation.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('playwright');
const {acquireProfile}=require('./upro-browser-session.cjs');
const [root,requestPath]=process.argv.slice(2);
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const write=(p,d)=>fs.writeFileSync(p,JSON.stringify(d,null,2));
(async()=>{
 const request=read(requestPath),binding=hash(requestPath);
 if(!/^https:\/\/vibes\.ai\/projects\/[a-f0-9-]+$/.test(request.project_url)||!request.items.length||request.items.length>30)throw Error('Invalid bounded upload request');
 const output=path.resolve(request.output);if(!/^E:\\/i.test(output))throw Error('Local media must stay on E:');fs.mkdirSync(output,{recursive:true});
 const profile=path.join(root,'.runtime/browser-profiles/religion'),release=await acquireProfile(profile,10000);
 let context,page,activeReceipt;
 try{
  context=await chromium.launchPersistentContext(profile,{channel:'chrome',headless:true,locale:'es-ES'});
  page=await context.newPage();
  const cards=()=>page.locator('[data-analytics-id="creation_gallery.thumbnail_click"]');
  async function gallery(){
   await page.goto(request.project_url);
   const login=page.getByRole('button',{name:'Iniciar sesión',exact:true});
   const projectId=new URL(request.project_url).pathname.split('/').pop();
   const projectTile=page.locator('[data-analytics-id="project_thumbnail_click"][data-analytics-media-id="'+projectId+'"]');
   const deadline=Date.now()+60000;let entered=false,opened=false;
   while(Date.now()<deadline){
    if(await cards().count())break;
    if(!entered&&await login.isVisible().catch(()=>false)){
     entered=true;await login.click();await page.getByText('Proyectos',{exact:true}).first().waitFor({timeout:20000});
    }else if(!opened&&await projectTile.isVisible().catch(()=>false)){
     opened=true;await projectTile.click();
    }
    await page.waitForTimeout(750);
   }
   if(!await cards().count())throw Error('Project gallery unavailable after session reconciliation');
   await page.waitForLoadState('networkidle',{timeout:3000}).catch(()=>{});
   return cards().evaluateAll(es=>es.map(e=>({id:e.getAttribute('data-analytics-media-id'),video:!!e.querySelector('video[src]'),label:(e.innerText||'').trim()})));
  }
  for(const item of request.items){
   const file=path.resolve(item.file);if(!/^E:\\/i.test(file)||hash(file)!==item.sha256||!/^[-a-z0-9]+$/.test(item.id))throw Error('Reference binding changed');
   const receipt=path.join(output,item.id+'.json');activeReceipt=receipt;let state=fs.existsSync(receipt)?read(receipt):null;
   if(state&&state.request_sha256!==binding)throw Error('Upload request changed');
   if(state?.state==='uploaded')continue;
   let all=await gallery();
   if(!state||state.state==='failed_confirmed'){
    const attempts=(state?.attempts||0)+1;if(attempts>3)throw Error('Upload failed three times; resolve provider before another attempt');
    const history=state?[...(state.history||[]),{state:state.state,evidence:state.failure_evidence}]:[];
    state={attempts,history,state:'prepared',request_sha256:binding,file,sha256:item.sha256,prior_ids:all.map(x=>x.id)};write(receipt,state);
    await page.getByRole('button',{name:'Upload media',exact:true}).click();
    const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Click to add or drag and drop media',exact:true}).click();await(await chooser).setFiles(file);
    state.state='submitting';write(receipt,state);
    await page.getByRole('button',{name:'Subir',exact:true}).click();
    await page.getByRole('heading',{name:'Cargar imágenes',exact:true}).waitFor({state:'hidden',timeout:60000});
    await page.waitForTimeout(20000);
    all=await gallery();
   }
   if(state.state==='prepared')throw Error('Prepared upload needs reconciliation before retry');
   const newest=all.find(x=>!x.video&&x.label==='Uploaded media');
   if(!newest||state.prior_ids.includes(newest.id))throw Error('Uncertain upload: preserve intent, do not submit again');
   state={...state,state:'uploaded',source_media_id:newest.id,completed_at:new Date().toISOString()};write(receipt,state);
   console.log(JSON.stringify({id:item.id,state:state.state,source_media_id:state.source_media_id}));
  }
 }catch(error){
  if(page){try{const u=new URL(page.url()),body=(await page.locator('body').innerText({timeout:3000})).slice(0,5000),evidence=path.join(output,'failure-'+Date.now()+'.json');write(evidence,{message:error.message,page:u.origin+u.pathname,body,card_count:await page.locator('[data-analytics-id="creation_gallery.thumbnail_click"]').count()});if(activeReceipt&&body.includes('Error de carga')&&fs.existsSync(activeReceipt)){const state=read(activeReceipt);if(state.state==='submitting'){state.state='failed_confirmed';state.failure_evidence=evidence;write(activeReceipt,state);}}}catch{}}
  throw error;
 }finally{if(context)await context.close();await release();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
