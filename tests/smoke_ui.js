const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.TEST_BROWSER?{executablePath:process.env.TEST_BROWSER}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.TEST_URL);await page.getByText('Uma biblioteca que permanece.').waitFor();await page.getByText('Local · worker sem sinal').waitFor();
  await page.locator('#url').fill('https://youtu.be/BaW_jenozKc');await page.getByRole('button',{name:'Cadastrar e sincronizar'}).click();await page.getByText('Fonte cadastrada permanentemente com agenda mensal.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Sincronizar agora',exact:true}).waitFor();
  await page.locator('[data-view="library"]').click();await page.getByRole('checkbox').first().check();await page.getByRole('button',{name:'Reprocessar selecionados',exact:true}).click();await page.getByText('1 item(ns) na fila de reprocessamento.',{exact:true}).waitFor();
  await page.locator('[data-view="queue"]').click();await page.getByRole('button',{name:'Pausar',exact:true}).first().click();await page.getByRole('button',{name:'Retomar',exact:true}).first().waitFor();await page.getByRole('button',{name:'Retomar',exact:true}).first().click();await page.getByRole('button',{name:'Cancelar',exact:true}).first().click();
  await page.locator('[data-view="research"]').click();await page.locator('#palace-name').fill('Palácio do teste');await page.locator('#palace-description').fill('Fontes controladas');await page.locator('#palace-sources input').first().check();await page.getByRole('button',{name:'Salvar oráculo',exact:true}).click();await page.getByText('Palácio do teste · Fontes controladas',{exact:true}).waitFor();
  await page.locator('#query').fill('palavra inexistente');await page.locator('#search-form button').click();await page.getByText('Nenhum trecho encontrado no conjunto indexado.',{exact:true}).waitFor();
  await page.locator('[data-view="settings"]').click();await page.getByRole('button',{name:'Criar backup do catálogo'}).click();await page.getByText('Backup do catálogo verificado:',{exact:false}).waitFor();
  await page.getByRole('button',{name:'Pausar automação',exact:true}).click();await page.getByRole('button',{name:'Retomar automação',exact:true}).waitFor();await page.getByRole('button',{name:'Retomar automação',exact:true}).click();
  await page.locator('[data-view="sources"]').click();await page.screenshot({path:process.env.TEST_SCREENSHOT,fullPage:true});
  await page.setViewportSize({width:390,height:844});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);assert.equal(overflow,false);assert.deepEqual(errors,[]);
  await page.locator('[data-view="settings"]').click();await page.getByRole('button',{name:'Encerrar sessão',exact:true}).click();await page.getByText('Sessão encerrada. Reabra o aplicativo para retomar.',{exact:true}).waitFor();
  console.log(JSON.stringify({ui:'passed',checks:['register permanent source','sync controls','bulk reprocess','pause/resume/cancel job','create palace with source','literal search empty result','backup','automation pause/resume','no JS errors','mobile no overflow','shutdown']}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
