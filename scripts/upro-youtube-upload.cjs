const fs = require('node:fs');
const crypto = require('node:crypto');

function save(file, value) {
  fs.writeFileSync(file + '.tmp', JSON.stringify(value, null, 2));
  fs.renameSync(file + '.tmp', file);
}
async function snapshot(page, request) {
  const controls = await page.locator('button,[role="button"],[role="radio"],[role="checkbox"],input,textarea,[contenteditable="true"],a')
    .evaluateAll(es => es.filter(e => e.getClientRects().length).map(e => ({tag:e.tagName,id:e.id,
      role:e.getAttribute('role'),label:e.getAttribute('aria-label'),type:e.getAttribute('type'),
      text:(e.innerText||'').slice(0,200),href:e.getAttribute('href'),
      parentTag:e.parentElement?.tagName,parentId:e.parentElement?.id})));
  save(request.snapshot_path, {url:page.url(),text:(await page.locator('body').innerText()).slice(0,22000),controls});
}
async function verifyPrivate(page, request, journal) {
  await page.goto('https://studio.youtube.com/channel/'+request.expected_account_id+'/videos/short',{waitUntil:'domcontentloaded'});
  const compatibility=page.getByRole('link',{name:/Cambiar a la nueva versión de Studio/i});
  if(await compatibility.isVisible()) await compatibility.click();
  const title=page.locator('a#video-title[href="/video/'+journal.video_id+'/edit"]');
  await title.waitFor({state:'visible',timeout:30000});
  const row=await title.evaluate(e=>{
    for(let p=e;p;p=p.parentElement) if(p.tagName==='YTCP-VIDEO-ROW') return p.innerText;
    return null;
  });
  await snapshot(page,request);
  if(!row || !row.includes(request.metadata.title) || !/\bPrivado\b/.test(row) || /Borrador|Programado/.test(row)) {
    throw new Error('Private saved video is not verified in the exact channel inventory');
  }
  if(!journal.upload_completed_at) throw new Error('Missing completed upload observation');
  const result={master_sha256:request.master_sha256,account_id:request.expected_account_id,
    video_id:journal.video_id,privacyStatus:'private',upload_complete:true,never_public:true,
    upload_completed_at:journal.upload_completed_at,evidence:{method:'Upro own browser file selection, private save and fresh exact-channel Studio row',
      source_filename:require('node:path').basename(request.master_path),journal_path:request.journal_path,
      observed_row:row,observed_at:new Date().toISOString(),snapshot_path:request.snapshot_path}};
  save(request.result_path,result);
  save(request.journal_path,{...journal,stage:'private_verified'});
  console.log(JSON.stringify({status:'PRIVATE_VERIFIED',video_id:journal.video_id}));
}
async function upload(page, request) {
  const hash = crypto.createHash('sha256').update(fs.readFileSync(request.master_path)).digest('hex');
  if(hash !== request.master_sha256) throw new Error('Master hash mismatch');
  let journal = fs.existsSync(request.journal_path) ? JSON.parse(fs.readFileSync(request.journal_path,'utf8')) : null;
  if(journal && (journal.intent_id !== request.intent_id || journal.master_sha256 !== hash)) throw new Error('Upload journal mismatch');
  if(journal && ['private_save_started','private_saved','private_verified'].includes(journal.stage)) {
    return verifyPrivate(page,request,journal);
  }
  if(journal) {
    if(['file_selection_started','draft_created'].includes(journal.stage)) {
      await page.getByRole('menuitem',{name:'Contenido',exact:true}).click();
      await page.getByRole('tab',{name:'Shorts',exact:true}).click();
      await page.getByRole('button',{name:request.metadata.title,exact:true}).click();
    } else {
      await page.goto(journal.draft_url || 'https://studio.youtube.com/video/'+journal.video_id+'/edit',{waitUntil:'domcontentloaded'});
    }
    await page.waitForLoadState('networkidle',{timeout:20000}).catch(()=>{});
  } else {
    await page.getByRole('button',{name:'Subir vídeos',exact:true}).click();
    const file = page.locator('input[type="file"]');
    await file.waitFor({state:'attached'});
    journal={intent_id:request.intent_id,master_sha256:hash,account_id:request.expected_account_id,
             stage:'file_selection_started',started_at:new Date().toISOString()};
    save(request.journal_path,journal);
    await file.setInputFiles(request.master_path);
    await snapshot(page,request);
    let videoId;
    try {
      await page.waitForFunction(() => /(?:youtu\.be\/|youtube\.com\/shorts\/)[\w-]{11}/.test(document.body.innerText), null, {timeout:30000});
      videoId=(await page.locator('body').innerText()).match(/(?:youtu\.be\/|youtube\.com\/shorts\/)([\w-]{11})/)[1];
    } finally { await snapshot(page,request); }
    if(!/^[\w-]{11}$/.test(videoId)) throw new Error('Invalid new video ID');
    journal={...journal,video_id:videoId,stage:'draft_created'};
    save(request.journal_path,journal);
    await page.waitForLoadState('networkidle',{timeout:20000}).catch(()=>{});
  }
  const visibleLink=page.locator('a#video-link');
  if(await visibleLink.count()) {
    const id=(await visibleLink.getAttribute('href')).match(/(?:youtu\.be\/|youtube\.com\/shorts\/)([\w-]{11})/)?.[1];
    if(!id || journal.video_id && journal.video_id!==id) throw new Error('Draft video identity mismatch');
    journal={...journal,video_id:id,stage:'draft_created',draft_url:page.url()};save(request.journal_path,journal);
  }
  await page.getByRole('textbox',{name:'Añade un título que describa tu vídeo (escribe @ seguido del nombre de un canal para mencionarlo)',exact:true}).fill(request.metadata.title);
  await page.getByRole('textbox',{name:'Cuenta a los usuarios de qué va tu vídeo (escribe @ seguido del nombre de un canal para mencionarlo)',exact:true}).fill(request.metadata.description);
  await page.getByRole('radio',{name:'No, no está creado para niños',exact:true}).click();
  await page.getByRole('button',{name:'Mostrar configuración avanzada',exact:true}).click();
  await page.getByRole('radio',{name:'Sí, se ha usado IA',exact:true}).click();
  for(let i=0;i<3;i++) await page.getByRole('button',{name:'Siguiente',exact:true}).click();
  await page.getByRole('radio',{name:'Privado',exact:true}).click();
  if(await page.getByRole('radio',{name:'Privado',exact:true}).getAttribute('aria-checked')!=='true') throw new Error('Private visibility was not selected');
  await page.getByText('Comprobaciones completadas. No se han encontrado problemas.',{exact:true}).waitFor({state:'visible',timeout:300000});
  await snapshot(page,request);
  journal={...journal,stage:'private_save_started',upload_completed_at:new Date().toISOString()};
  save(request.journal_path,journal);
  await page.getByRole('button',{name:'Guardar',exact:true}).click();
  await page.getByRole('button',{name:'Guardar',exact:true}).waitFor({state:'hidden',timeout:30000});
  journal={...journal,stage:'private_saved'};save(request.journal_path,journal);
  return verifyPrivate(page,request,journal);
}
module.exports={upload:async(page,request)=>{
  try { return await upload(page,request); }
  catch(error) { await snapshot(page,request).catch(()=>{}); throw error; }
}};
