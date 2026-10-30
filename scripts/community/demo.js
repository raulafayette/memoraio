const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
(async () => {
 const origin = new URL(process.env.DEMO_URL).origin;
 const browser = await chromium.launch({headless:true, executablePath:process.env.DEMO_BROWSER});
 const context = await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:process.env.DEMO_OUTPUT,size:{width:1440,height:1000}},reducedMotion:'reduce',bypassCSP:true});
 const page=await context.newPage();const failures=[];page.on('pageerror',error=>failures.push(error.message));
 await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
 let simulation=false;
 await page.route('**/api/channels',async route=>{
  const response=await route.fetch();const result=await response.json();
  if(simulation){const channel=result.channels.find(c=>c.id===process.env.DEMO_SOURCE);if(channel&&channel.session&&channel.session.state!=='paused'){
   channel.session.state='downloading';channel.session.counts={ready:1,running:1,queued:1,unavailable:0};channel.session.total=3;
   channel.current_work={title:'Exemplo fictício: uma nova conversa',fraction:.55};
   channel.session.items=[{id:'youtube_demo0000001',title:'Exemplo fictício: organizar referências',state:'ready'},{id:'youtube_demo0000002',title:'Exemplo fictício: uma nova conversa',state:'running'},{id:'youtube_demo0000003',title:'Exemplo fictício: revisão do acervo',state:'queued'}];
  }}await route.fulfill({json:result});
 });
 try {
  await page.goto(process.env.DEMO_URL);
  await page.addStyleTag({content:'#demo-note{pointer-events:none;position:fixed;top:auto;width:auto;height:auto;display:block;bottom:20px;left:240px;right:24px;background:#192135f5;color:white;border:1px solid #8b82ff;border-radius:12px;padding:15px 20px;z-index:99999;font:600 20px system-ui;box-shadow:0 8px 30px #0005}#demo-note small{display:block;color:#b6bfdb;font-size:12px;margin-top:6px;letter-spacing:.5px}body{padding-bottom:100px}'});
  const note=async text=>page.evaluate(text=>{let el=document.getElementById('demo-note');if(!el){el=document.createElement('aside');el.id='demo-note';document.body.append(el);}el.replaceChildren(document.createTextNode(text));const small=document.createElement('small');small.textContent='DEMONSTRAÇÃO · DADOS FICTÍCIOS · PROGRESSO SIMULADO · NENHUM ACERVO PESSOAL';el.append(small);},text);
  await page.locator('#theme-choice').selectOption('dark');
  await note('Memoraio — acompanhe seu acervo e continue de onde parou.');await page.waitForTimeout(3500);
  await page.locator('[data-view="channels"]').click();await page.waitForFunction(()=>document.querySelectorAll('.folder-card').length===3);
  const card=page.locator('.folder-card').filter({has:page.getByRole('button',{name:'Canal de exemplo A',exact:true})});
  await card.scrollIntoViewIfNeeded();await note('1. Veja o que já está guardado e o que ainda falta em cada canal.');await page.waitForTimeout(5500);
  await page.screenshot({path:path.join(process.env.DEMO_OUTPUT,'memoraio-demo-sintetica.png')});
  await card.getByRole('button',{name:'Ver TXT',exact:true}).click();await page.locator('#ready-tab').click();await page.getByRole('button',{name:'Abrir TXT',exact:true}).click();await page.waitForFunction(()=>document.getElementById('txt-content').textContent.includes('demonstração fictícia'));
  await page.locator('#txt-content').evaluate(element=>element.scrollTop=element.scrollHeight);await note('2. Abra uma transcrição com um clique. O texto permanece disponível no acervo.');await page.waitForTimeout(5500);
  await page.locator('#close-txt').click();await page.locator('#back-channels').click();await card.getByRole('button',{name:'Liberar',exact:true}).waitFor();
  await card.scrollIntoViewIfNeeded();await note('3. Você decide quando começar. Novos canais aguardam na fila pausada.');await page.waitForTimeout(4000);
  simulation=true;await card.getByRole('button',{name:'Liberar',exact:true}).click();await page.locator('[data-view="channels"]').click();await page.waitForFunction(()=>document.querySelectorAll('#channels-running .folder-card').length===1);
  await card.scrollIntoViewIfNeeded();await note('4. Acompanhe o lote e a transcrição atual. Aqui, o progresso é simulado.');await page.waitForTimeout(5500);
  simulation=false;await card.getByRole('button',{name:'Pausar',exact:true}).click();await card.getByRole('button',{name:'Liberar',exact:true}).waitFor();
  await note('5. Pause o canal. A fila mantém seu estado para uma próxima utilização.');await page.waitForTimeout(5000);
  await page.locator('[data-view="downloads"]').click();await page.getByRole('heading',{name:'Downloads',exact:true}).waitFor();await page.locator('#download-format').selectOption('mp3');
  await note('6. Vídeo e música têm uma página própria: MP4 ou MP3, unitário ou em lote.');await page.waitForTimeout(5000);
  await page.locator('[data-view="channels"]').click();await note('Ajude a evoluir o Memoraio: testes, acessibilidade, documentação e código.');await page.waitForTimeout(5000);
  assert.deepEqual(failures,[]);
 } finally {await context.close();await browser.close();}
})().catch(error=>{console.error(error.message);process.exit(1);});
