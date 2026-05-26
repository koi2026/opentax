const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto('http://localhost:8501/admin', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(4000);
  await page.click('button:has-text("법령 데이터")', { timeout: 5000 });
  await page.waitForTimeout(3000);
  await page.evaluate(() => window.scrollTo(0, 99999));
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'admin_rulings_section.png', fullPage: false });
  await browser.close();
})();
