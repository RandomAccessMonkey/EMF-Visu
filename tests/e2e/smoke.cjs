// End-to-end smoke test against a running stack (frontend + API + Redis worker + database).
//   node tests/e2e/smoke.cjs [baseUrl] [screenshotDir]
// Exits non-zero on the first failed check.
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const path = require('node:path')

const BASE = process.argv[2] ?? 'http://localhost:5173'
const SHOTS = process.argv[3] ?? null

async function main() {
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: SHOTS ? 2 : 1, locale: 'en-US' })
  const errors = []
  let solves = 0
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('request', (r) => r.url().endsWith('/api/v1/simulations') && solves++)
  const shot = async (name) => SHOTS && page.screenshot({ path: path.join(SHOTS, `${name}.png`) })
  const settled = () => page.getByText('Field is up to date').waitFor({ timeout: 15000 })
  const step = (msg) => console.log(`ok  ${msg}`)

  await page.goto(BASE)
  await page.getByRole('button', { name: /Electric dipole/ }).click()
  await settled()
  await page.waitForTimeout(400)
  assert.equal(await page.locator('aside li button[aria-pressed]').count(), 2)
  await shot('01-dipole-2d')
  step('preset loads and the engine field is displayed')

  // Unavailable presets are disabled, not fake.
  assert.ok(await page.getByRole('button', { name: /Solenoid/ }).isDisabled())
  step('unimplemented presets are disabled')

  // Visual-only change must not trigger a new solve.
  await page.getByRole('tab', { name: 'Display' }).click()
  const before = solves
  await page.getByLabel('Colour map').selectOption('E')
  await page.getByLabel('Arrow length').selectOption('log')
  await page.waitForTimeout(600)
  assert.equal(solves, before, 'visual-only changes re-solved the physics')
  await shot('02-field-magnitude')
  step('visual-only changes reuse the cached result (no new solve)')

  // Physics change triggers exactly a new solve.
  await page.getByLabel('Arrow density').focus()
  await page.keyboard.press('ArrowRight')
  await settled()
  await page.waitForTimeout(300)
  assert.ok(solves > before, 'sampling change did not re-solve')
  await page.getByLabel('Colour map').selectOption('phi')
  await page.getByLabel('Arrow length').selectOption('uniform')

  // Drag the positive charge (at x = -0.5 m) to x ≈ -1.0 m, y ≈ +0.5 m in the 2D view.
  const box = await page.locator('canvas').boundingBox()
  const zoom = 0.92 * Math.min(box.width / 4, box.height / 4)
  const cx = box.x + box.width / 2
  const cy = box.y + box.height / 2
  await page.mouse.move(cx - 0.5 * zoom, cy)
  await page.mouse.down()
  await page.mouse.move(cx - 0.8 * zoom, cy - 0.3 * zoom, { steps: 6 })
  await page.mouse.move(cx - 1.0 * zoom, cy - 0.5 * zoom, { steps: 6 })
  await page.mouse.up()
  await settled()
  await page.getByRole('tab', { name: 'Parameters' }).click()
  assert.equal(await page.getByLabel('Position x').inputValue(), '-1')
  assert.equal(await page.getByLabel('Position y').inputValue(), '0.5')
  step('dragging a charge in 2D updates the shared scene state (snapped to 0.1 m)')

  // Edit the charge numerically, then inspect the same scene in 3D.
  await page.getByLabel('Charge', { exact: true }).last().fill('3')
  await settled()
  await page.getByRole('radio', { name: '3D' }).click()
  await settled()
  await page.waitForTimeout(800)
  assert.equal(await page.getByLabel('Position x').inputValue(), '-1')
  await shot('03-dipole-3d')
  step('the same scene and parameters are shown in 3D')

  // Probe: exact values from the engine.
  await page.getByRole('radio', { name: '2D' }).click()
  await page.getByRole('radio', { name: /Probe/ }).click()
  await page.mouse.click(cx + 1.2 * zoom, cy - 0.9 * zoom)
  await page.getByRole('tab', { name: 'Results' }).click()
  await page.getByText(/\|E\| = [\d.]+ (k|m)?V\/m/).waitFor({ timeout: 10000 })
  assert.ok(await page.getByText('Exact analytical solution', { exact: true }).isVisible())
  await shot('04-probe-results')
  step('probe returns engine values; result is labelled as exact analytical')

  // Equations with statuses and explanation dialog.
  await page.getByRole('tab', { name: 'Equations' }).click()
  await page.getByRole('button', { name: /Coulomb field of point charges/ }).click()
  await page.getByText('Symbols and SI units').waitFor()
  assert.ok((await page.locator('.katex').count()) > 3)
  await shot('05-equation-dialog')
  await page.keyboard.press('Escape')
  step('equation registry is displayed with status and explanation')

  // Advanced level: solver status and a queued high-resolution job with progress.
  await page.getByRole('radio', { name: 'Advanced' }).click()
  await page.getByText('Not evaluated by the current solver').first().waitFor()
  await page.getByRole('tab', { name: 'Display' }).click()
  await page.getByRole('button', { name: 'Run high-resolution solve' }).click()
  await page.getByText('High resolution', { exact: true }).waitFor({ timeout: 30000 })
  await page.getByRole('tab', { name: 'Results' }).click()
  assert.ok(await page.getByText('heat.phi').isVisible())
  assert.ok(await page.getByText('768×768').first().isVisible())
  await shot('06-advanced-high-resolution')
  step('high-resolution job ran on the worker queue and its result is displayed')

  // Hungarian UI.
  await page.getByRole('radio', { name: 'HU' }).click()
  await page.getByRole('tab', { name: 'Eredmények' }).waitFor()
  assert.ok(await page.getByText('Egzakt analitikus megoldás', { exact: true }).isVisible())
  await shot('07-hungarian')
  await page.getByRole('radio', { name: 'EN' }).click()
  step('UI switches to Hungarian, including backend-provided text')

  // Persistence: save, reload, load.
  const name = `e2e ${Date.now()}`
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.getByLabel('Project name').fill(name)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByText(name).first().waitFor()
  await page.reload()
  assert.equal(await page.locator('aside li button[aria-pressed]').count(), 0)
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: name }).getByRole('button', { name: 'Load' }).click()
  await page.waitForFunction(() => document.querySelectorAll('aside li button[aria-pressed]').length === 2)
  await settled()
  await page.locator('aside li button[aria-pressed]').first().click()
  await page.getByRole('tab', { name: 'Parameters' }).click()
  assert.equal(await page.getByLabel('Position x').inputValue(), '-1')
  assert.equal(await page.getByLabel('Charge', { exact: true }).last().inputValue(), '3')
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: name }).getByRole('button', { name: 'Delete' }).click()
  await page.keyboard.press('Escape')
  step('project saved to the database and restored after a page reload')

  // Keyboard: delete the selected object.
  await page.locator('canvas').click({ position: { x: 5, y: box.height - 5 }, button: 'right' })
  await page.locator('aside li button[aria-pressed]').first().click()
  await page.locator('aside li button[aria-pressed]').first().blur()
  await page.keyboard.press('Delete')
  await page.waitForFunction(() => document.querySelectorAll('aside li button[aria-pressed]').length === 1)
  step('keyboard delete removes the selected object')

  assert.deepEqual(errors, [], 'browser console errors')
  step('no browser console errors')
  await browser.close()
}

main().catch((e) => {
  console.error('FAILED:', e.message ?? e)
  process.exit(1)
})
