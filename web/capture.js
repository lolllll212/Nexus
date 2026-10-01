import puppeteer from 'puppeteer-core';
import path from 'path';

const outDir = 'C:\\Users\\Ashut\\.gemini\\antigravity-ide\\brain\\65420e0d-157c-475a-bde1-eacc91dfd469';

async function run() {
  console.log('Launching Chrome...');
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900']
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });

    console.log('Navigating to http://localhost:3000...');
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle2', timeout: 15000 });
    await new Promise(r => setTimeout(r, 2000));

    // 1. Initial State
    const shot1 = path.join(outDir, 'screenshot_1_initial.png');
    await page.screenshot({ path: shot1 });
    console.log('Saved screenshot 1:', shot1);

    // 2. Type "hi" in the command bar
    const cmdInput = await page.$('form input[placeholder*="Message NEXUS"]');
    if (cmdInput) {
      console.log('Typing "hi" in CommandCenter...');
      await cmdInput.click();
      await cmdInput.type('hi');
      await page.keyboard.press('Enter');

      await new Promise(r => setTimeout(r, 2000));
      const shot2 = path.join(outDir, 'screenshot_2_hi_message.png');
      await page.screenshot({ path: shot2 });
      console.log('Saved screenshot 2:', shot2);
    }

    // 3. Test inline input inside the Conversational Stream window
    const streamInput = await page.$('input[placeholder*="Ask NEXUS or dispatch command"]');
    if (streamInput) {
      console.log('Typing "what tools do you have?" inside ConversationalStream input...');
      await streamInput.click();
      await streamInput.type('what tools do you have?');
      await page.keyboard.press('Enter');

      console.log('Waiting for heuristic tool response...');
      await new Promise(r => setTimeout(r, 4500));
      const shot3 = path.join(outDir, 'screenshot_3_tools_message.png');
      await page.screenshot({ path: shot3 });
      console.log('Saved screenshot 3:', shot3);
    }

    // 4. Click Expand button on Conversational Stream
    const expandBtn = await page.$('button[title="Expand view"]');
    if (expandBtn) {
      console.log('Clicking expand view...');
      await expandBtn.click();
      await new Promise(r => setTimeout(r, 1000));
      const shot4 = path.join(outDir, 'screenshot_4_expanded_chat.png');
      await page.screenshot({ path: shot4 });
      console.log('Saved screenshot 4:', shot4);
    }

    // 5. Click the Quick Action Chip "⚡ System Health"
    const healthChip = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const found = btns.find(b => b.textContent && b.textContent.includes('System Health'));
      if (found) {
        found.click();
        return true;
      }
      return false;
    });

    if (healthChip) {
      console.log('Clicked System Health chip, waiting for response...');
      await new Promise(r => setTimeout(r, 4500));
      const shot5 = path.join(outDir, 'screenshot_5_health_message.png');
      await page.screenshot({ path: shot5 });
      console.log('Saved screenshot 5:', shot5);
    }

    console.log('All message screenshots captured successfully!');
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('Capture error:', err);
  process.exit(1);
});
