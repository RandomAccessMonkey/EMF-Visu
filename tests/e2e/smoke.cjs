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

  const valueIs = async (locator, expected) => {
    const deadline = Date.now() + 5000
    let got = await locator.inputValue()
    while (got !== expected && Date.now() < deadline) {
      await page.waitForTimeout(50)
      got = await locator.inputValue()
    }
    assert.equal(got, expected)
  }
  const rows = () => page.locator('aside li button[aria-pressed]')
  const rowCount = (n) => page.waitForFunction((k) => document.querySelectorAll('aside li button[aria-pressed]').length === k, n)
  const quiet = async (label, action) => {
    await settled()
    const before = solves
    await action()
    await page.waitForTimeout(700)
    assert.equal(solves, before, `visual-only change "${label}" triggered a physics request`)
  }
  const solved = async (label, action) => {
    const before = solves
    await action()
    const deadline = Date.now() + 10000
    while (solves === before && Date.now() < deadline) await page.waitForTimeout(50)
    assert.ok(solves > before, `physical change "${label}" did not trigger a physics request`)
    await page.waitForTimeout(150)
    await settled()
  }

  await page.goto(BASE)
  await page.getByRole('button', { name: /Electric dipole/ }).click()
  await settled()
  await page.waitForTimeout(500)
  await rowCount(3) // dipole group + its two point charges
  await shot('01-dipole-2d')
  step('preset loads and the engine field is displayed')

  // Unavailable presets are disabled, not fake.
  assert.ok(await page.getByRole('button', { name: /Solenoid/ }).isDisabled())
  step('unimplemented presets are disabled')

  // Derived products are present and labelled separately from the exact field.
  await page.getByRole('tab', { name: 'Results' }).click()
  assert.ok(await page.getByText('Exact analytical solution', { exact: true }).isVisible())
  assert.ok(await page.getByText('Numerical integration', { exact: true }).isVisible())
  assert.ok(await page.getByText('Numerical geometric extraction', { exact: true }).first().isVisible())
  const terminations = page.getByRole('table', { name: 'Field-line start and end reasons' })
  assert.ok(await terminations.getByRole('row', { name: /positive charge negative charge \d+/ }).isVisible())
  assert.equal(await terminations.getByText(/numerical\)/).count(), 0)
  step('field lines run from + to −; products carry their own method metadata')

  // Visual-only changes must not trigger a solve.
  await page.getByRole('tab', { name: 'Display' }).click()
  await quiet('colour map', () => page.getByLabel('Colour map').selectOption('E'))
  await shot('02-field-magnitude')
  await quiet('arrow length', () => page.getByLabel('Arrow length').selectOption('log'))
  await quiet('vector density', async () => { await page.getByLabel('Arrow density').focus(); await page.keyboard.press('ArrowRight') })
  await quiet('vector scale', async () => { await page.getByLabel('Arrow size').focus(); await page.keyboard.press('ArrowRight') })
  await quiet('vector field D', () => page.getByLabel('Vector field').selectOption('D'))
  assert.ok(await page.getByText('Arrows |D| [C/m²]').isVisible())
  await quiet('vectors off', () => page.getByLabel('Field vectors on the slice').click())
  await quiet('field-line density', async () => { await page.getByLabel('Line density').focus(); await page.keyboard.press('ArrowRight') })
  await quiet('field lines off', () => page.getByLabel('Show field lines').click())
  await quiet('contours off', () => page.getByLabel('Contour lines on the slice').click())
  await quiet('grid off', () => page.getByLabel('Coordinate grid and axes').click())
  await quiet('zoom', () => page.mouse.wheel(0, -300))
  for (const label of ['Show field lines', 'Contour lines on the slice', 'Field vectors on the slice', 'Coordinate grid and axes']) await page.getByLabel(label).click()
  await page.getByLabel('Vector field').selectOption('E')
  await page.getByLabel('Colour map').selectOption('phi')
  await page.getByLabel('Arrow length').selectOption('uniform')
  await page.getByRole('button', { name: 'Reset view' }).click()
  step('eleven visual-only changes reuse the cached result (no physics request)')

  // Dipole editing: q and d change both charges, and each change re-solves.
  await rows().first().click()
  await page.getByRole('tab', { name: 'Parameters' }).click()
  await solved('dipole separation', () => page.getByLabel('Separation', { exact: true }).last().fill('1.6'))
  await solved('dipole charge', () => page.getByLabel('Charge magnitude', { exact: true }).last().fill('2'))
  await rows().nth(1).click()
  await valueIs(page.getByLabel('Position x'), '-0.8')
  await valueIs(page.getByLabel('Charge', { exact: true }).last(), '2')
  await rows().nth(2).click()
  await valueIs(page.getByLabel('Position x'), '0.8')
  await valueIs(page.getByLabel('Charge', { exact: true }).last(), '-2')
  await rows().first().click()
  // Restore q = 1 nC, d = 1 m. No request is asserted: the two quick edits may be debounced into
  // one, and the original state is still cached.
  await page.getByLabel('Separation', { exact: true }).last().fill('1')
  await page.getByLabel('Charge magnitude', { exact: true }).last().fill('1')
  await page.waitForTimeout(600)
  await settled()
  step('dipole magnitude and separation edit both point charges')

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
  await valueIs(page.getByLabel('Position x'), '-1')
  await valueIs(page.getByLabel('Position y'), '0.5')
  step('dragging a charge in 2D updates the shared scene state (snapped to 0.1 m)')

  // Magnitude (numeric, beyond the slider range is allowed) and polarity are physical changes.
  await solved('charge magnitude', () => page.getByLabel('Charge', { exact: true }).last().fill('250'))
  await solved('charge magnitude', () => page.getByLabel('Charge', { exact: true }).last().fill('3'))
  await solved('polarity', () => page.getByRole('button', { name: 'Flip sign' }).click())
  await valueIs(page.getByLabel('Charge', { exact: true }).last(), '-3')
  // Flipping back returns to a physical state that was already solved: served from the cache.
  await quiet('return to a solved state', () => page.getByRole('button', { name: 'Flip sign' }).click())
  await valueIs(page.getByLabel('Charge', { exact: true }).last(), '3')
  await solved('add charge', () => page.getByRole('button', { name: 'Charge', exact: true }).first().click())
  await rowCount(4)
  await solved('coordinates', () => page.getByLabel('Position y').fill('-1.2'))
  await shot('03-three-charges-2d')
  // Removing it returns to the previous physical state, which is still cached.
  await quiet('remove charge (back to a solved state)', () => rows().nth(3).locator('xpath=..').getByRole('button', { name: /^Delete/ }).click())
  await rowCount(3)
  step('magnitude, polarity, position and number of charges each trigger a new solve')

  // The same scene in 3D, with field lines and equipotential surfaces.
  await rows().nth(1).click()
  await page.getByRole('radio', { name: '3D' }).click()
  await settled()
  await page.waitForTimeout(1200)
  await valueIs(page.getByLabel('Position x'), '-1')
  await valueIs(page.getByLabel('Charge', { exact: true }).last(), '3')
  await page.getByRole('tab', { name: 'Display' }).click()
  await shot('04-3d-lines-and-isosurfaces')
  await quiet('isosurfaces off', () => page.getByLabel('Equipotential surfaces').click())
  await quiet('volume vectors off', () => page.getByLabel('Field vectors in the volume').click())
  await quiet('orbit', async () => { await page.mouse.move(cx, cy + 200); await page.mouse.down(); await page.mouse.move(cx + 120, cy + 160, { steps: 5 }); await page.mouse.up() })
  await shot('05-3d-field-lines')
  await page.getByLabel('Equipotential surfaces').click()
  await page.getByRole('tab', { name: 'Results' }).click()
  assert.ok(await page.getByText('Equipotential surfaces', { exact: true }).isVisible())
  step('the same scene and parameters are shown in 3D with field lines and isosurfaces')

  // Probe: exact values from the engine, with each charge's contribution.
  await page.getByRole('radio', { name: '2D' }).click()
  await settled()
  await page.getByRole('radio', { name: /Probe/ }).click()
  await page.mouse.click(cx + 1.2 * zoom, cy - 0.9 * zoom)
  await page.getByText(/\|E\| = [\d.]+ (k|m)?V\/m/).waitFor({ timeout: 10000 })
  assert.ok(await page.getByText('Superposition: contribution of each charge').isVisible())
  assert.ok(await page.getByText(/\|D\| = /).isVisible())
  await shot('06-probe-results')
  step('probe returns E, φ, D and the superposition terms')

  // Equations with statuses, usage and explanation dialog.
  await page.getByRole('tab', { name: 'Equations' }).click()
  await page.getByRole('button', { name: /Superposition principle/ }).click()
  await page.getByText('Symbols and SI units').waitFor()
  assert.ok((await page.locator('.katex').count()) > 3)
  assert.ok(await page.getByRole('dialog').getByText('Evaluated by the solver').isVisible())
  await shot('07-equation-dialog')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: /Gauss's law in vacuum/ }).click()
  assert.ok(await page.getByRole('dialog').getByText('Satisfied, not solved').isVisible())
  assert.ok(await page.getByRole('dialog').getByText('Integral form').isVisible())
  await page.keyboard.press('Escape')
  step('equation registry distinguishes evaluated equations from satisfied laws')

  // Advanced level: solver status and a queued high-resolution job with progress.
  await page.getByRole('radio', { name: 'Advanced' }).click()
  await page.getByText('Not evaluated by the current solver').first().waitFor()
  await page.getByRole('tab', { name: 'Display' }).click()
  await page.getByRole('button', { name: 'Run high-resolution solve' }).click()
  await page.getByText('High resolution', { exact: true }).waitFor({ timeout: 60000 })
  await page.getByRole('tab', { name: 'Results' }).click()
  assert.ok(await page.getByText('heat.phi').isVisible())
  assert.ok(await page.getByText('769×769').first().isVisible())
  await shot('08-advanced-high-resolution')
  step('high-resolution job ran on the worker queue and its result is displayed')

  // Hungarian UI.
  await page.getByRole('radio', { name: 'HU' }).click()
  await page.getByRole('tab', { name: 'Eredmények' }).waitFor()
  assert.ok(await page.getByText('Egzakt analitikus megoldás', { exact: true }).isVisible())
  assert.ok(await page.getByText('Numerikus integrálás', { exact: true }).isVisible())
  await shot('09-hungarian')
  await page.getByRole('radio', { name: 'EN' }).click()
  step('UI switches to Hungarian, including backend-provided text')

  // Persistence: save, reload, load.
  const name = `e2e ${Date.now()}`
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.getByLabel('Project name').fill(name)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByText(name).first().waitFor()
  await page.reload()
  assert.equal(await rows().count(), 0)
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: name }).getByRole('button', { name: 'Load' }).click()
  await rowCount(3)
  await settled()
  await rows().nth(1).click()
  await page.getByRole('tab', { name: 'Parameters' }).click()
  await valueIs(page.getByLabel('Position x'), '-1')
  await valueIs(page.getByLabel('Charge', { exact: true }).last(), '3')
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: name }).getByRole('button', { name: 'Delete' }).click()
  await page.keyboard.press('Escape')
  step('project saved to the database and restored after a page reload')

  // Add a dipole with the button; keyboard delete removes the whole group.
  await page.getByRole('button', { name: 'Add dipole (+q, −q)' }).click()
  await rowCount(6)
  await settled()
  await page.locator('canvas').click({ position: { x: 5, y: box.height - 5 }, button: 'right' })
  await rows().nth(3).click()
  await rows().nth(3).blur()
  await page.keyboard.press('Delete')
  await rowCount(3)
  step('a dipole can be added; keyboard delete removes the selected group')

  // Other presets still load (Phase 1 behaviour).
  await page.getByRole('button', { name: /Multiple interacting point charges/ }).click()
  await rowCount(4)
  await settled()
  await page.waitForTimeout(600)
  await shot('10-multiple-charges')
  await page.getByRole('button', { name: /Single negative point charge/ }).click()
  await rowCount(1)
  await settled()
  await page.getByRole('tab', { name: 'Results' }).click()
  const rowsNeg = page.getByRole('table', { name: 'Field-line start and end reasons' })
  assert.ok(await rowsNeg.getByRole('row', { name: /edge of the region.*negative charge \d+/ }).isVisible())
  step('presets 1–4 load; a lone negative charge receives its lines from the boundary')

  assert.deepEqual(errors, [], 'browser console errors')
  step('no browser console errors')
  await browser.close()
}

main().catch((e) => {
  console.error('FAILED:', e.message ?? e)
  process.exit(1)
})
