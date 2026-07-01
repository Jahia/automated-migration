import { chromium } from 'playwright'

const RUN_ID = 'run_1781670881781'
const BASE = 'http://localhost:8001'

async function sleep(ms: number) {
  return new Promise(r => setTimeout(r, ms))
}

interface StepInfo {
  id: string
  story_id: string
  status: string
  task_type: string
  agent: string
  streaming_text: string
}

interface StoryInfo {
  id: string
  title: string
  status: string
  steps: StepInfo[]
}

interface EpicInfo {
  id: string
  title: string
  status: string
  stories: StoryInfo[]
}

interface RunInfo {
  run_id: string
  status: string
  epics: EpicInfo[]
}

async function fetchRun(): Promise<RunInfo> {
  const resp = await fetch(`${BASE}/runs/${RUN_ID}`)
  return resp.json()
}

async function pauseRun() {
  await fetch(`${BASE}/runs/${RUN_ID}/pause`, { method: 'POST' })
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage()
  page.on('console', msg => {
    if (msg.type() === 'error') console.log('  [CONSOLE ERROR]', msg.text())
  })
  page.on('pageerror', err => console.log('  [PAGE ERROR]', err.message))

  console.log(`Navigating to run ${RUN_ID}...`)
  await page.goto(`${BASE}/app/runs/${RUN_ID}`, { waitUntil: 'networkidle', timeout: 15000 })
  await sleep(3000)
  console.log('Page loaded')

  // Wait for story 1 to complete (all steps done)
  console.log('\n--- Waiting for story 1 to complete ---')
  let story1Done = false
  let story2Running = false
  let paused = false

  while (!paused) {
    const run = await fetchRun()
    const epic1 = run.epics[0]
    if (!epic1) {
      console.log('  No epics found, waiting...')
      await sleep(5000)
      continue
    }

    const story1 = epic1.stories[0]
    const story2 = epic1.stories[1]

    if (story1) {
      const doneSteps = story1.steps.filter(s => s.status === 'done').length
      const totalSteps = story1.steps.length
      const failedSteps = story1.steps.filter(s => s.status === 'failed').length
      const activeStep = story1.steps.find(s => s.status === 'running' || s.status === 'verifying')

      if (!story1Done && doneSteps === totalSteps) {
        story1Done = true
        console.log(`  ✅ Story 1 complete! (${doneSteps}/${totalSteps} steps done)`)
      } else if (failedSteps > 0 && !story1Done) {
        console.log(`  ❌ Story 1: ${failedSteps} steps failed out of ${totalSteps}`)
      }

      if (!story1Done && activeStep) {
        console.log(`  Story 1 active: ${activeStep.task_type}@${activeStep.agent} (${activeStep.streaming_text.length} chars)`)
      }
    }

    if (story1Done && story2) {
      const runningStep = story2.steps.find(s => s.status === 'running' || s.status === 'verifying' || s.status === 'ready')
      const doneSteps = story2.steps.filter(s => s.status === 'done').length

      if (runningStep || doneSteps > 0) {
        if (!story2Running) {
          story2Running = true
          console.log(`  ✅ Story 2 started!`)
        }
        console.log(`  Story 2: ${doneSteps}/${story2.steps.length} done, active: ${runningStep?.task_type || 'none'}`)

        // Pause after story 2 starts
        console.log('\n--- Pausing run ---')
        await pauseRun()
        paused = true
        console.log('  ⏸ Run paused')

        // Verify the pause
        await sleep(2000)
        const check = await fetchRun()
        console.log(`  Status after pause: ${check.status}`)
        break
      }
    }

    if (run.status === 'failed' || run.status === 'aborted' || run.status === 'completed') {
      console.log(`  Run terminated: ${run.status}`)
      break
    }

    await sleep(5000)
  }

  // Take a screenshot
  await page.screenshot({ path: '/tmp/orchestrator-test-result.png', fullPage: true })
  console.log('\nScreenshot saved to /tmp/orchestrator-test-result.png')

  // Print final state summary
  const final = await fetchRun()
  console.log(`\n--- Final state: ${final.status} ---`)
  for (const epic of final.epics.slice(0, 1)) {
    console.log(`Epic ${epic.id}: ${epic.status}`)
    for (const story of epic.stories.slice(0, 3)) {
      const stepStatuses = story.steps.map(s => `${s.task_type}[${s.status}]`).join(', ')
      console.log(`  ${story.id}: ${story.status} → ${stepStatuses}`)
    }
  }

  await browser.close()
  console.log('\nDone')
}

main().catch(console.error)
