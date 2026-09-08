// Use the ordinary provider UI with Upro's own per-channel browser profile.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const {chromium} = require('playwright');
const [root, requestPath, output] = process.argv.slice(2);
const read = p => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''));
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const write = (p, value) => {fs.mkdirSync(path.dirname(p), {recursive:true}); fs.writeFileSync(p, JSON.stringify(value,null,2));};

(async()=>{
  const request = read(requestPath);
  const intentPath = path.join(output,'intent.json');
  const fingerprint = hash(requestPath);
  let intent = fs.existsSync(intentPath) ? read(intentPath) : null;
  if (intent && intent.request_sha256 !== fingerprint) throw Error('Provider request changed');
  if (intent && intent.state === 'downloaded') {console.log(JSON.stringify(intent)); return;}
  if (intent && intent.state !== 'generated') throw Error('Existing Vibes intent requires reconciliation; generation will not be repeated');
  if (intent && (!Array.isArray(intent.media_ids) || intent.media_ids.length !== 4
      || new Set(intent.media_ids).size !== 4 || intent.project_url !== request.project_url))
    throw Error('Saved generated batch lost its identity');
  if (request.kind !== 'vibes_native_batch_v1' || request.channel_id !== 'religion' || request.count !== 4
      || !/^https:\/\/vibes\.ai\/projects\/[a-f0-9-]+$/.test(request.project_url)) throw Error('Invalid native Vibes request');
  for (const source of request.inputs) if (hash(source.path)!==source.sha256) throw Error('Changed provider input');
  const media = path.resolve(request.output_directory);
  if (!/^E:\\/i.test(media)) throw Error('Native MP4s require the authorized E: volume');
  fs.mkdirSync(media,{recursive:true});
  const context = await chromium.launchPersistentContext(path.join(root,'.runtime/browser-profiles/religion'),
    {channel:'chrome',headless:true,chromiumSandbox:true,locale:'es-ES',acceptDownloads:true,downloadsPath:media});
  try {
    const page = await context.newPage();
    await page.goto(request.project_url);
    await page.waitForTimeout(6000);
    await page.getByText(request.project_title,{exact:true}).waitFor();
    const cards = () => page.locator('[data-analytics-id="creation_gallery.thumbnail_click"]');
    if (!intent) {
    const prior = await cards().evaluateAll(elements=>elements.map(e=>e.getAttribute('data-analytics-media-id')));
    await page.getByRole('button',{name:'Start, end frame',exact:true}).click();
    await page.getByRole('button',{name:'Add start frame',exact:true}).click();
    const picker=page.getByRole('dialog');
    await picker.getByRole('button',{name:'Subir',exact:true}).click();
    const chooser = page.waitForEvent('filechooser');
    await page.getByRole('button',{name:'Click to add or drag and drop media',exact:true}).click();
    await (await chooser).setFiles(request.start_reference.path);
    await page.getByRole('button',{name:'Subir',exact:true}).click();
    await page.getByRole('heading',{name:'Cargar imágenes',exact:true}).waitFor({state:'hidden'});
    await picker.getByRole('img',{name:path.basename(request.start_reference.path),exact:true}).last().click();
    await picker.getByRole('button',{name:'Añadir al vídeo',exact:true}).click();
    await picker.waitFor({state:'hidden'});
    await page.getByRole('button',{name:'Opciones avanzadas',exact:true}).click();
    await page.getByRole('button',{name:'720p',exact:true}).click();
    const titleBox=await page.getByText(request.project_title,{exact:true}).boundingBox();
    if (!titleBox) throw Error('Project heading not visible');
    await page.mouse.click(titleBox.x+titleBox.width/2,titleBox.y+titleBox.height/2);
    await page.getByRole('button',{name:'480p',exact:true}).waitFor({state:'hidden'});
    const prompt=fs.readFileSync(request.prompt.path,'utf8');
    await page.getByRole('textbox',{name:'Describe un vídeo…',exact:true}).fill(prompt);
    for (const source of request.inputs) if (hash(source.path)!==source.sha256) throw Error('Provider input changed before submission');
    // Persist before clicking: a crash can never silently submit the same batch twice.
    intent={state:'submitting',request_sha256:fingerprint,project_url:request.project_url,prior_media_ids:prior,
      start_reference_sha256:request.start_reference.sha256,prompt_sha256:request.prompt.sha256,started_at:new Date().toISOString()};
    write(intentPath,intent);
    await page.getByRole('button',{name:'Generar',exact:true}).click();
    intent.state='submitted';write(intentPath,intent);
    let fresh=[];
    const deadline=Date.now()+600000;
    while(Date.now()<deadline){
      fresh=await cards().evaluateAll((elements, old)=>elements.map(e=>({id:e.getAttribute('data-analytics-media-id'),ready:!!e.querySelector('video[src],img[src]')}))
        .filter(v=>v.id && !old.includes(v.id) && v.id.startsWith('batch-')),prior);
      if(fresh.length===4 && fresh.every(v=>v.ready)) break;
      if(fresh.length>4) throw Error('Concurrent media appeared; reconcile the batch identity');
      await page.waitForTimeout(5000);
    }
    if(fresh.length!==4 || fresh.some(v=>!v.ready)) throw Error('Native batch not ready before timeout');
    const batchIds=new Set(fresh.map(v=>v.id.replace(/-content-\d+$/,'')));
    if(batchIds.size!==1) throw Error('New candidates belong to different batches');
    intent.state='generated';intent.media_ids=fresh.map(v=>v.id).sort();write(intentPath,intent);
    }
    const candidates=intent.candidates || [];
    if (candidates.length > 4) throw Error('Invalid saved download count');
    for (const [index,candidate] of candidates.entries()) {
      const expected=path.join(media,`candidate_${String(index+1).padStart(2,'0')}.mp4`);
      if (path.resolve(candidate.path)!==expected || candidate.media_id!==intent.media_ids[index]
          || !fs.existsSync(expected) || hash(expected)!==candidate.sha256) throw Error('Saved download changed');
    }
    for(const [index,id] of intent.media_ids.entries()){
      if (index < candidates.length) continue;
      const target=page.locator(`[data-analytics-id="creation_gallery.thumbnail_click"][data-analytics-media-id="${id}"]`);
      await target.getByRole('button',{name:'More actions',exact:true}).click();
      const download=page.waitForEvent('download');
      await page.getByRole('menuitem',{name:'Descargar',exact:true}).click();
      const file=path.join(media,`candidate_${String(index+1).padStart(2,'0')}.mp4`);
      if(fs.existsSync(file)) throw Error('Native destination already exists');
      const transfer=await download;
      await transfer.saveAs(file);
      if(await transfer.failure()) throw Error('Native download failed');
      candidates.push({path:file,sha256:hash(file),media_id:id});
      await transfer.delete();
      intent.candidates=candidates;write(intentPath,intent);
    }
    intent.state='downloaded';intent.completed_at=new Date().toISOString();write(intentPath,intent);
    console.log(JSON.stringify(intent));
  } finally {await context.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
