import { chromium } from 'playwright'

async function testFrontend() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext()
  const page = await context.newPage()

  const errors: string[] = []
  const failedRequests: { url: string; status: number }[] = []

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      errors.push(msg.text())
    }
  })

  page.on('requestfailed', (request) => {
    errors.push(`Request failed: ${request.url()} - ${request.failure()?.errorText}`)
  })

  page.on('response', (response) => {
    if (response.status() >= 400) {
      failedRequests.push({ url: response.url(), status: response.status() })
    }
  })

  console.log('--- Testing frontend at http://localhost:8000/app ---')
  try {
    await page.goto('http://localhost:8000/app', { waitUntil: 'networkidle', timeout: 15000 })
    console.log('Page loaded successfully')
  } catch (e) {
    console.log(`Page load error: ${e}`)
  }

  await page.waitForTimeout(2000)

  // Check page title
  const title = await page.title()
  console.log(`Title: ${title}`)

  // Check if root div has content
  const rootContent = await page.evaluate(() => {
    const root = document.getElementById('root')
    return root ? root.innerHTML.length : 0
  })
  console.log(`Root div content length: ${rootContent}`)

  // Check for visible text
  const bodyText = await page.evaluate(() => document.body.innerText.trim().slice(0, 500))
  console.log(`Body text: ${bodyText}`)

  // Take screenshot
  await page.screenshot({ path: '/tmp/orchestrator-frontend.png', fullPage: true })
  console.log('Screenshot saved to /tmp/orchestrator-frontend.png')

  // Test schema page
  console.log('\n--- Testing schema page ---')
  try {
    await page.goto('http://localhost:8000/app/schema', { waitUntil: 'networkidle', timeout: 10000 })
    const schemaText = await page.evaluate(() => document.body.innerText.trim().slice(0, 300))
    console.log(`Schema text: ${schemaText}`)
    await page.screenshot({ path: '/tmp/orchestrator-schema.png', fullPage: true })
  } catch (e) {
    console.log(`Schema page error: ${e}`)
  }

  // Test API directly
  console.log('\n--- Testing API endpoints ---')
  try {
    const healthResp = await page.evaluate(() => fetch('/health').then(r => r.json()))
    console.log(`Health: ${JSON.stringify(healthResp)}`)
  } catch (e) {
    console.log(`Health error: ${e}`)
  }

  try {
    const schemaResp = await page.evaluate(() => fetch('/schema').then(r => r.json()))
    console.log(`Schema has ${Object.keys(schemaResp).length} keys`)
  } catch (e) {
    console.log(`Schema error: ${e}`)
  }

  // Report
  console.log('\n--- Report ---')
  if (failedRequests.length > 0) {
    console.log(`FAILED REQUESTS (${failedRequests.length}):`)
    failedRequests.forEach(r => console.log(`  ${r.status} ${r.url}`))
  } else {
    console.log('No failed requests')
  }

  if (errors.length > 0) {
    console.log(`CONSOLE ERRORS (${errors.length}):`)
    errors.forEach(e => console.log(`  ${e}`))
  } else {
    console.log('No console errors')
  }

  await browser.close()
}

testFrontend().catch(console.error)
