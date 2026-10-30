const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.TEST_BROWSER});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.TEST_URL);await page.getByText('Local · worker sem sinal').waitFor();
  await page.locator('[data-view="library"]').click();await page.locator('#select-all').click();await page.waitForFunction(()=>document.getElementById('selection-summary').textContent.startsWith('1 selecionado'));
  await page.locator('#archive').click();await page.locator('#notice').getByText('1 tarefa(s) registrada(s).',{exact:true}).waitFor();
  await page.locator('[data-view="library"]').click();await page.locator('#filter').fill('Não existe');await page.locator('#apply-filters').click();await page.locator('#select-all').click();await page.waitForFunction(()=>document.getElementById('selection-summary').textContent.startsWith('0 selecionado'));
  await page.locator('[data-view="settings"]').click();await page.locator('#cpu-threads').fill('3');await page.locator('#preferences-form button').click();await page.getByText('Ajustes salvos para as próximas tarefas.',{exact:true}).waitFor();
  await page.locator('[data-view="sources"]').click();await page.emulateMedia({colorScheme:'dark',reducedMotion:'reduce'});await page.screenshot({path:process.env.TEST_SCREENSHOT.replace('.png','-dark.png'),fullPage:true});
  await page.emulateMedia({colorScheme:'light'});await page.screenshot({path:process.env.TEST_SCREENSHOT.replace('.png','-light.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.locator('[data-view="library"]').click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);console.log(JSON.stringify({ui_v3:'passed',checks:['server-side filtered selection','independent transcript operation','saved CPU preference','light and dark','reduced motion','narrow window','no JS errors']}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
