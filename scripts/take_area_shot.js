const { chromium } = require('@playwright/test');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('http://localhost:8501/admin', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  // Click on 지역 데이터 tab
  await page.click('text=지역 데이터');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'admin_area_tab.png' });
  await browser.close();
})();
