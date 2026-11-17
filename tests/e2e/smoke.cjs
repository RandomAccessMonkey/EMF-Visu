// End-to-end smoke test against a running stack (frontend + API + Redis worker + database).
//   node tests/e2e/smoke.cjs [baseUrl] [screenshotDir]
// Exits non-zero on the first failed check.
// EMF_E2E_NO_WORKER=1: the stack deliberately runs without Redis and the solver worker (native
// run without a queue). The high-resolution job check then verifies that the job is reported as
// unavailable instead of running it; every other check is unchanged.
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const path = require('node:path')

const BASE = process.argv[2] ?? 'http://localhost:5173'
const SHOTS = process.argv[3] ?? null
const NO_WORKER = process.env.EMF_E2E_NO_WORKER === '1'

async function main() {
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: SHOTS ? 2 : 1, locale: 'en-US' })
  const errors = []
  let solves = 0
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('request', (r) => r.url().endsWith('/api/v1/simulations') && solves++)
  // Electric and magnetic solves are counted separately (Phase 3A: independent requests).
  let eSolves = 0
  let mSolves = 0
  page.on('request', (r) => {
    if (!r.url().endsWith('/api/v1/simulations')) return
    try {
      const q = JSON.parse(r.postData()).request.quantities
      if (q.includes('B')) mSolves++
      else eSolves++
    } catch { /* ignore */ }
  })
  let fluxes = 0
  const fluxQualities = []
  page.on('request', (r) => {
    if (!r.url().endsWith('/api/v1/flux')) return
    fluxes++
    try { fluxQualities.push(JSON.parse(r.postData()).flux.quality) } catch { /* ignore */ }
  })
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
    const beforeFlux = fluxes
    await action()
    await page.waitForTimeout(700)
    assert.equal(solves, before, `visual-only change "${label}" triggered a physics request`)
    assert.equal(fluxes, beforeFlux, `visual-only change "${label}" triggered a flux request`)
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
  // (Phase 3B made the solenoid preset and Phase 4A the Faraday preset available; a
  // still-planned preset is checked instead.)
  assert.ok(await page.getByRole('button', { name: /Dielectric material inside a capacitor/ }).isDisabled())
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

  // Phase 2B-1: exact divergence and curl at an ordinary point, while E is nonzero.
  const calc = page.getByRole('table', { name: 'Divergence and curl' })
  await calc.getByRole('row', { name: /∇·E\s*scalar\s*0 V\/m²/ }).waitFor()
  assert.ok(await calc.getByRole('row', { name: /∇·D\s*scalar\s*0 C\/m³/ }).isVisible())
  assert.ok(await calc.getByRole('row', { name: /∇×E\s*vector\s*\|∇×E\| = 0 V\/m²\s*\(0, 0, 0\) V\/m²/ }).isVisible())
  assert.ok(await calc.getByRole('row', { name: /∇×D\s*vector.*\(0, 0, 0\) C\/m³/ }).isVisible())
  assert.ok(await page.getByRole('table', { name: 'Field values' }).getByText(/\|E\| = [\d.]+ (k|m)?V\/m/).isVisible())
  step('probe shows ∇·E = ∇·D = 0 and ∇×E = ∇×D = (0, 0, 0) with units, while |E| is nonzero')

  // At a charge: singular field values, no pointwise div/curl, the distributional statement.
  await page.getByRole('radio', { name: /Select/ }).click()
  await rows().nth(1).click() // q₊ of the dipole, +3 nC
  await page.getByRole('tab', { name: 'Results' }).click()
  await page.getByRole('button', { name: 'Place probe on the selected charge' }).click()
  await page.getByText('Distributional interpretation').waitFor({ timeout: 10000 })
  assert.equal(await page.getByText('singular — undefined').count(), 3)
  assert.equal(await page.getByText('not evaluated (the field is undefined here)').count(), 4)
  assert.ok(await page.getByText('∇·E ∋ (339 V·m) · δ³(r − rᵢ)').isVisible())
  assert.ok(await page.getByText('∇·D ∋ (3.00 nC) · δ³(r − rᵢ)').isVisible())
  assert.ok(await page.getByText('∇×E = (0, 0, 0) · ∇×D = (0, 0, 0)').isVisible())
  assert.ok(await page.getByRole('table', { name: 'Distributional sources' }).getByText('339 V·m').isVisible())
  await shot('06b-probe-at-charge')
  step('probe at a charge: E, φ, D singular; div/curl not evaluated; δ weights and zero distributional curl')

  // Divergence and curl layers, source markers: all visual-only.
  await page.getByRole('tab', { name: 'Display' }).click()
  await quiet('colour map ∇·E', () => page.getByLabel('Colour map').selectOption('div_E'))
  assert.ok(await page.getByTestId('zero-legend').getByText(/exactly 0 at all 2401 defined samples/).isVisible())
  await quiet('curl vectors on', () => page.getByLabel('Curl vectors').click())
  assert.ok(await page.getByText('∇×E = 0 exactly at this sample (zero vector)').isVisible())
  await shot('06c-divergence-and-curl-2d')
  await quiet('colour map ∇·D', () => page.getByLabel('Colour map').selectOption('div_D'))
  await quiet('colour map |∇×E|', () => page.getByLabel('Colour map').selectOption('curl_E'))
  await quiet('colour map |∇×D|', () => page.getByLabel('Colour map').selectOption('curl_D'))
  assert.ok(await page.getByTestId('zero-legend').getByText('|∇×D| [C/m³]').isVisible())
  await quiet('curl of D', () => page.getByLabel('Curl of').selectOption('D'))
  assert.ok(await page.getByText('∇×D = 0 exactly at this sample (zero vector)').isVisible())
  assert.equal(await page.getByTestId('source-label').count(), 2)
  await quiet('source markers off', () => page.getByLabel('Point-charge source markers').click())
  assert.equal(await page.getByTestId('source-label').count(), 0)
  await quiet('source markers on', () => page.getByLabel('Point-charge source markers').click())
  await page.getByTestId('source-label').nth(1).waitFor()
  step('divergence/curl colour maps, curl glyphs and source markers are visual-only; legend states exact zeros')

  // An off-slice charge is a projected ghost with its offset, never a singularity of the slice.
  await rows().nth(2).click() // q₋ of the dipole
  await page.getByRole('tab', { name: 'Parameters' }).click()
  await solved('move a charge off the slice', () => page.getByLabel('Position z').fill('0.4'))
  await page.getByTestId('source-label').filter({ hasText: 'Δz = +0.400 m' }).waitFor()
  await shot('06d-off-slice-ghost')
  await page.getByLabel('Position z').fill('0')
  await settled()
  await page.waitForFunction(() => ![...document.querySelectorAll('[data-testid=source-label]')].some((e) => e.textContent.includes('Δz')))
  step('a charge moved off the slice is shown as a projection with Δz; back in the slice it is normal again')

  // 3D: divergence values at the volume samples, curl glyphs in the volume.
  await page.getByRole('radio', { name: '3D' }).click()
  await settled()
  await page.getByRole('tab', { name: 'Display' }).click()
  await page.getByLabel('Colour map').selectOption('div_E')
  await quiet('volume vectors on', () => page.getByLabel('Field vectors in the volume').click())
  await quiet('volume scalars on', () => page.getByLabel('Colour-map values at volume samples').click())
  await page.waitForTimeout(600)
  await shot('06e-divergence-and-curl-3d')
  await quiet('volume scalars off', () => page.getByLabel('Colour-map values at volume samples').click())
  await page.getByLabel('Field vectors in the volume').click()
  await page.getByLabel('Curl vectors').click()
  await page.getByLabel('Curl of').selectOption('E')
  await page.getByLabel('Colour map').selectOption('phi')
  await page.getByRole('radio', { name: '2D' }).click()
  await settled()
  step('3D: divergence at volume samples and zero-curl glyphs, visual-only')

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
  await page.getByRole('button', { name: /Divergence of E for point charges/ }).click()
  assert.ok(await page.getByRole('dialog').getByText('Evaluated by the solver').isVisible())
  assert.ok(await page.getByRole('dialog').getByText('Derivation').isVisible())
  await shot('07b-divergence-equation')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: /Curl of the electrostatic field/ }).click()
  assert.ok(await page.getByRole('dialog').getByText(/distributional curl is still zero/).isVisible())
  await page.keyboard.press('Escape')
  step('equation registry distinguishes evaluated equations from satisfied laws')

  // Advanced level: solver status and a queued high-resolution job with progress.
  await page.getByRole('radio', { name: 'Advanced' }).click()
  await page.getByText('Not evaluated by the current solver').first().waitFor()
  // Finite-difference check of the exact zeros, with uncertainties (advanced level only).
  await page.getByRole('radio', { name: /Probe/ }).click()
  await page.mouse.click(cx + 1.2 * zoom, cy - 0.9 * zoom)
  await page.getByRole('tab', { name: 'Results' }).click()
  const diag = page.getByRole('table', { name: 'Numerical check (finite differences)' })
  await diag.waitFor({ timeout: 10000 })
  assert.equal(await diag.getByText('consistent with 0').count(), 4)
  assert.ok(await diag.getByText(/±/).first().isVisible())
  await page.getByRole('radio', { name: /Select/ }).click()
  step('advanced: finite-difference estimates are labelled numerical and consistent with exact 0')
  await page.getByRole('tab', { name: 'Display' }).click()
  if (NO_WORKER) {
    await page.getByText(/No solver worker is online/).waitFor({ timeout: 15000 })
    assert.ok(await page.getByRole('button', { name: 'Run high-resolution solve' }).isDisabled())
    assert.ok(await page.getByText('worker offline').first().isVisible())
    await page.getByRole('tab', { name: 'Results' }).click()
    step('no worker (EMF_E2E_NO_WORKER=1): high-resolution solve is disabled and reported unavailable')
  } else {
    await page.getByRole('button', { name: 'Run high-resolution solve' }).click()
    await page.getByText('High resolution', { exact: true }).waitFor({ timeout: 60000 })
    await page.getByRole('tab', { name: 'Results' }).click()
    assert.ok(await page.getByText('heat.phi').isVisible())
    assert.ok(await page.getByText('769×769').first().isVisible())
    await shot('08-advanced-high-resolution')
    step('high-resolution job ran on the worker queue and its result is displayed')
  }

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


  // ---------------------------------------------------------------- Phase 2B-2: Gauss
  const fluxSettled = () => page.waitForFunction(() => !document.body.innerText.includes('…'), null, { timeout: 15000 })
  const fluxed = async (label, action) => {
    const before = fluxes
    await action()
    const deadline = Date.now() + 10000
    while (fluxes === before && Date.now() < deadline) await page.waitForTimeout(50)
    assert.ok(fluxes > before, `change "${label}" did not trigger a flux request`)
    await page.waitForTimeout(400)
    await settled()
  }
  const fluxTable = () => page.getByRole('table', { name: 'Flux results' })
  const fluxRow = (label) => fluxTable().getByRole('row', { name: label })
  await page.getByRole('tab', { name: 'Gauss' }).click()
  await fluxed('load situation 5', () => page.getByRole('button', { name: /One enclosed charge plus several external charges/ }).click())
  const explanation = page.getByTestId('gauss-explanation')
  await explanation.getByText('This surface encloses 1 positive and 0 negative charge(s): Q_enc = 1.00 nC.').waitFor()
  assert.ok(await explanation.getByText(/3 external charge\(s\) change the field/).isVisible())
  await page.getByRole('tab', { name: 'Results' }).click()
  await fluxRow(/Φ_E = ∮ E·dA\s*112\.941 V·m\s*Exact for the triangulated surface/).waitFor()
  assert.ok(await fluxRow(/Φ_D = ∮ D·dA\s*1000\.00 pC/).isVisible())
  assert.ok(await fluxRow(/Volume integral ∫ ∇·E dV\s*112\.941 V·m\s*Exact analytical/).isVisible())
  assert.ok(await fluxRow(/External charges\s*3/).isVisible())
  assert.ok(await page.getByText('Final', { exact: true }).first().isVisible())
  const contributions = page.getByRole('table', { name: 'Charges and their contributions' })
  assert.equal(await contributions.getByText('outside').count(), 3)
  await shot('11-gauss-results')
  step('Gauss: enclosed + external charges; Φ_E = Q/ε₀ and the volume integral agree; external charges counted')

  // Visual-only surface settings: no field and no flux request.
  await page.getByRole('tab', { name: 'Gauss' }).click()
  await quiet('surface opacity', async () => { await page.getByLabel('Opacity').focus(); await page.keyboard.press('ArrowRight') })
  await quiet('surface normals', () => page.getByLabel('Show normals').click())
  await quiet('colour by flux off', () => page.getByLabel('Colour by local flux density E·n').click())
  await quiet('colour by flux on', () => page.getByLabel('Colour by local flux density E·n').click())
  await quiet('surface hidden', () => page.getByLabel('Show surface').click())
  await quiet('surface shown', () => page.getByLabel('Show surface').click())
  await quiet('rename surface', () => page.getByLabel('Surface name').fill('Gauss box'))
  step('surface opacity, normals, colouring, visibility and name are visual-only')

  // Physical changes: charge position, surface size, orientation.
  await rows().first().click() // q₁, the enclosed charge
  await page.getByRole('tab', { name: 'Parameters' }).click()
  await fluxed('move charge outside', () => page.getByLabel('Position x').fill('0.8'))
  await page.getByRole('tab', { name: 'Gauss' }).click()
  await explanation.getByText('This surface encloses 0 positive and 0 negative charge(s): Q_enc = 0 C.').waitFor()
  await page.getByRole('tab', { name: 'Results' }).click()
  assert.ok(await fluxRow(/Enclosed charge Q_enc\s*0 C/).isVisible())
  step('moving the charge out of the box changes Q_enc and the flux to 0')
  await page.getByRole('tab', { name: 'Gauss' }).click()
  await page.getByRole('button', { name: /^Gauss box Φ_E/ }).click()
  await fluxed('enlarge box', () => page.getByLabel('Size x').fill('2'))
  await page.getByRole('tab', { name: 'Results' }).click()
  await fluxRow(/Φ_E = ∮ E·dA\s*112\.941 V·m/).waitFor()
  step('enlarging the surface re-encloses the charge: Φ_E = Q/ε₀ again')
  await page.getByRole('tab', { name: 'Gauss' }).click()
  await fluxed('reverse orientation', () => page.getByRole('button', { name: 'Reverse' }).click())
  await page.getByRole('tab', { name: 'Results' }).click()
  await fluxRow(/Φ_E = ∮ E·dA\s*-112\.941 V·m/).waitFor()
  assert.ok(await fluxRow(/Orientation\s*inward normals \(reversed\)/).isVisible())
  await page.getByRole('tab', { name: 'Gauss' }).click()
  // Back to outward: a state already computed, served from the cache.
  await page.getByRole('button', { name: 'Reverse' }).click()
  await page.getByText('outward normals', { exact: true }).first().waitFor()
  step('reversing the orientation flips the sign of the flux')

  // Subdivision: shared faces cancel; per-cell face fluxes shown in 3D.
  await fluxed('subdivide', () => page.getByLabel('Subdivide into cells').click())
  await page.getByRole('tab', { name: 'Results' }).click()
  const subd = page.getByTestId('subdivision-results')
  // q₁ sits at y = z = 0, on internal planes of the 4×4×4 grid: no cell owns it.
  await subd.getByText('cell-wise assignment ambiguous').waitFor()
  assert.ok(await subd.getByText(/q₁ lies on an internal cell boundary/).isVisible())
  assert.ok(await subd.getByRole('row', { name: /∫_V ∇·E dV\s*112\.941 V·m/ }).isVisible())
  await page.getByRole('tab', { name: 'Gauss' }).click()
  await fluxed('3 cells along y', () => page.getByLabel('Cells along y').selectOption('3'))
  await fluxed('3 cells along z', () => page.getByLabel('Cells along z').selectOption('3'))
  await page.getByRole('tab', { name: 'Results' }).click()
  await subd.getByText('cell-wise comparison valid').waitFor()
  assert.ok(await subd.getByRole('row', { name: /Shared internal faces\s*75/ }).isVisible())
  assert.ok(await subd.getByRole('row', { name: /Σ ∫_cell ∇·E dV\s*112\.941 V·m/ }).isVisible())
  assert.ok(await subd.getByRole('row', { name: /Largest \|Φ_A \+ Φ_B\| on a shared face\s*0 V·m/ }).isVisible())
  await page.getByRole('radio', { name: '3D' }).click()
  await settled()
  await page.getByTestId('cell-face-label').nth(5).waitFor()
  assert.equal(await page.getByTestId('cell-face-label').count(), 6)
  await page.waitForTimeout(800)
  await shot('12-gauss-subdivision-3d')
  step('subdivision: a charge on an internal plane is ambiguous; with 4×3×3 cells 75 shared faces cancel exactly')

  // Patch inspection: click the selected surface in 3D.
  await page.getByRole('tab', { name: 'Gauss' }).click()
  await page.getByLabel('Subdivide into cells').click()
  await settled()
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
  await page.getByRole('tab', { name: 'Results' }).click()
  await page.getByTestId('patch-inspector').waitFor({ timeout: 10000 })
  assert.ok(await page.getByTestId('patch-inspector').getByText(/integrated over the triangle/).isVisible())
  assert.ok(await page.getByTestId('patch-inspector').getByText(/at the centroid/).first().isVisible())
  step('a surface patch shows pointwise E·n at its centroid and its integrated flux separately')

  // Preview while dragging, final after release (2D charge drag).
  await page.getByRole('radio', { name: '2D' }).click()
  await settled()
  await page.getByRole('tab', { name: 'Gauss' }).click()
  await fluxed('situation 1', () => page.getByRole('button', { name: /One positive charge inside a sphere/ }).click())
  fluxQualities.length = 0
  await page.mouse.move(cx, cy)
  await page.mouse.down()
  for (let k = 1; k <= 8; k++) {
    await page.mouse.move(cx + 0.05 * k * zoom, cy, { steps: 2 })
    await page.waitForTimeout(60)
  }
  await page.mouse.up()
  await settled()
  await page.waitForTimeout(800)
  assert.ok(fluxQualities.includes('preview'), `no preview flux request during drag: ${fluxQualities}`)
  assert.equal(fluxQualities[fluxQualities.length - 1], 'final')
  assert.ok(await page.getByText('Final mesh resolution.').isVisible())
  assert.ok(await page.getByTestId('gauss-legend').getByText(/2D: lines are where the 3D surfaces cross this slice/).isVisible())
  await shot('13-gauss-2d-cross-section')
  step('dragging uses the preview mesh; the final mesh result follows on release; 2D shows the cross-section')

  // A charge on the surface; the same charges in three shapes.
  await fluxed('situation 8', () => page.getByRole('button', { name: /A charge exactly on the surface/ }).click())
  await explanation.getByText(/lie exactly on the surface/).waitFor()
  await page.getByRole('tab', { name: 'Results' }).click()
  assert.ok(await fluxRow(/Φ_E = ∮ E·dA\s*undefined\s*Undefined \(charge on boundary\)/).isVisible())
  assert.ok(await page.getByRole('alert').getByText(/A charge lies on this surface/).isVisible())
  step('a charge exactly on the surface: classification "on the surface", flux undefined')
  await page.getByRole('tab', { name: 'Gauss' }).click()
  await fluxed('situation 9', () => page.getByRole('button', { name: /Same enclosed charges: sphere, box and cylinder/ }).click())
  const list = page.getByRole('list', { name: 'Gaussian surfaces' })
  await list.getByText(/Φ_E = 56\.4705 V·m/).nth(2).waitFor()
  assert.equal(await list.getByText(/Φ_E = 56\.4705 V·m/).count(), 3)
  step('sphere, box and cylinder around the same charges give the same flux')

  // Equations reflect the surfaces.
  await page.getByRole('tab', { name: 'Equations' }).click()
  await page.getByRole('button', { name: /Gauss's law \(closed surface, E\)/ }).click()
  assert.ok(await page.getByRole('dialog').getByText('Both sides computed and compared').isVisible())
  await page.keyboard.press('Escape')
  step('equation registry: Gauss and divergence-theorem equations marked as computed and compared')

  // Saved with the project.
  const gname = `gauss ${Date.now()}`
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.getByLabel('Project name').fill(gname)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByText(gname).first().waitFor()
  await page.reload()
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: gname }).getByRole('button', { name: 'Load' }).click()
  await page.getByRole('tab', { name: 'Gauss' }).click()
  await list.getByText(/Φ_E = 56\.4705 V·m/).nth(2).waitFor({ timeout: 15000 })
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: gname }).getByRole('button', { name: 'Delete' }).click()
  await page.keyboard.press('Escape')
  step('Gaussian surfaces are saved and restored with the project')

  // Hungarian.
  await page.getByRole('radio', { name: 'HU' }).click()
  await page.getByRole('tab', { name: 'Eredmények' }).click()
  await page.getByText('Fluxus a Gauss-felületen át').waitFor()
  assert.ok(await page.getByText('Egzakt a háromszögelt felületre').first().isVisible())
  await shot('14-gauss-hungarian')
  await page.getByRole('radio', { name: 'EN' }).click()
  step('Gauss results in Hungarian')

  // ---------------------------------------------------------------- Phase 3A: magnetostatics
  await page.getByRole('radio', { name: 'Advanced' }).click()
  await page.getByRole('button', { name: /Straight current-carrying wire/ }).click()
  await settled()
  await page.getByTestId('magnetic-legend').waitFor()
  assert.ok(await page.getByText(/B field lines: \d+ closed, 0 truncated/).isVisible())
  await page.getByRole('tab', { name: 'Results' }).click()
  assert.ok(await page.getByText('Magnetic field model').isVisible())
  assert.ok(await page.getByText(/closed-form Biot–Savart solutions/).isVisible())
  await shot('15-wire')
  step('preset 9: B of an infinite wire, closed field lines, separate magnetic legend and model')

  // Visual-only magnetic changes reuse the cached result.
  await page.getByRole('tab', { name: 'Display' }).click()
  const toggle = (name) => page.getByRole('switch', { name }).click()
  await quiet('B arrows', () => toggle('Magnetic vectors'))
  await quiet('B arrows back', () => toggle('Magnetic vectors'))
  await quiet('B lines', () => toggle('Magnetic field lines'))
  await quiet('B lines back', () => toggle('Magnetic field lines'))
  await quiet('H instead of B', () => page.getByRole('combobox', { name: 'Magnetic vector field' }).selectOption('H'))
  await quiet('|B| colour map', () => page.getByRole('combobox', { name: 'Colour map' }).selectOption('B'))
  await quiet('current direction', () => toggle('Current direction'))
  await quiet('current direction back', () => toggle('Current direction'))
  await quiet('fields shown: magnetic only', () => page.getByRole('combobox', { name: 'Fields shown' }).selectOption('magnetic'))
  await quiet('fields shown: both', () => page.getByRole('combobox', { name: 'Fields shown' }).selectOption('both'))
  await page.getByRole('combobox', { name: 'Magnetic vector field' }).selectOption('B')
  step('ten magnetic visual-only changes reuse the cached result (no physics request)')

  // Preset 10: variants, superposition and individual contributions.
  await page.getByRole('button', { name: /Two parallel current-carrying wires/ }).click()
  await settled()
  await page.getByRole('button', { name: 'Opposite directions' }).click()
  await settled()
  await quiet('each source separately', () => page.getByRole('combobox', { name: 'Source contribution' }).selectOption('all'))
  assert.ok(await page.getByText(/Each source's own field in its colour/).isVisible())
  await quiet('one source only', () => page.getByRole('combobox', { name: 'Source contribution' }).selectOption({ label: 'Only I₁' }))
  await quiet('total field', () => page.getByRole('combobox', { name: 'Source contribution' }).selectOption('total'))
  await shot('16-two-wires-opposite')
  step('preset 10 variants; individual and total contributions are visual-only')

  // Probe: total equals the sum of the two contributions (shown separately), B = mu0 H.
  await page.getByRole('radio', { name: /Probe/ }).click()
  await page.mouse.click(cx, cy - 0.7 * zoom)
  await page.getByRole('tab', { name: 'Results' }).click()
  const mprobe = page.getByTestId('magnetic-probe')
  await mprobe.waitFor({ timeout: 10000 })
  assert.ok(await mprobe.getByText(/B = μ₀H, μ₀ = 1\.2566370621/).isVisible())
  assert.ok(await mprobe.getByText('Magnetic superposition terms').isVisible())
  assert.equal(await mprobe.getByRole('table', { name: 'Magnetic superposition terms' }).locator('tbody tr').count(), 2)
  assert.ok(await mprobe.getByText(/∇·B and ∇·H are exactly zero here/).isVisible())
  assert.ok(await mprobe.getByText(/Nearest current source: I₁|Nearest current source: I₂/).isVisible())
  step('probe: B, H, B = μ₀H, ∇·B = 0 and both contributions')

  // Physical changes: reversing a current triggers a magnetic solve only.
  await page.getByRole('radio', { name: /Select/ }).click()
  await rows().filter({ hasText: 'I₂' }).click()
  await page.getByRole('tab', { name: 'Parameters' }).click()
  const eBefore = eSolves
  // A new magnitude first: reversing −10 A would give the already-solved "same direction"
  // configuration, which the client cache serves without a request (as it should).
  await solved('current magnitude', async () => {
    await page.getByRole('spinbutton', { name: 'Current' }).fill('-7')
    await page.getByRole('spinbutton', { name: 'Current' }).press('Enter')
  })
  await solved('reverse current', () => page.getByRole('button', { name: 'Reverse current' }).click())
  await valueIs(page.getByRole('spinbutton', { name: 'Current' }), '7')
  assert.equal(eSolves, eBefore, 'a magnetic change re-solved the electric field')
  step('changing and reversing a current re-solves the magnetic field only')

  // Mixed scene: a charge and a wire; moving the charge re-solves only E, the wire only B.
  await page.getByRole('button', { name: /Single positive point charge/ }).click()
  await settled()
  await page.getByRole('button', { name: /^Wire$/ }).click()
  await settled()
  await page.getByRole('spinbutton', { name: 'Position x' }).fill('0.8')
  await page.getByRole('spinbutton', { name: 'Position x' }).press('Enter')
  await settled()
  await rows().filter({ hasText: 'q₁' }).click()
  const mBefore = mSolves
  await solved('move the charge', async () => {
    await page.getByRole('spinbutton', { name: 'Position y' }).fill('0.3')
    await page.getByRole('spinbutton', { name: 'Position y' }).press('Enter')
  })
  assert.equal(mSolves, mBefore, 'moving a charge re-solved the magnetic field')
  await page.getByRole('radio', { name: /Probe/ }).click()
  await page.mouse.click(cx - 0.5 * zoom, cy + 0.5 * zoom)
  await page.getByRole('tab', { name: 'Results' }).click()
  await page.getByTestId('magnetic-probe').waitFor({ timeout: 10000 })
  assert.ok(await page.getByRole('table', { name: 'Field values' }).getByText('V/m').first().isVisible())
  assert.ok(await page.getByRole('table', { name: 'Magnetic field values at the probe' }).getByText(/T$/).first().isVisible())
  assert.ok(await page.getByText('Electric field', { exact: true }).isVisible())
  await shot('17-mixed-probe')
  step('a charge and a wire: E and B solved, cached and probed separately, with their own units')

  if (!NO_WORKER) {
    // One high-resolution job per field: both layers are replaced by the job results.
    await page.getByRole('tab', { name: 'Display' }).click()
    assert.ok(await page.getByText(/queues one job for the electric and one for the magnetic field/).isVisible())
    await page.getByRole('button', { name: 'Run high-resolution solve' }).click()
    await page.getByText('High resolution', { exact: true }).waitFor({ timeout: 90000 })
    await settled()
    await page.getByRole('tab', { name: 'Results' }).click()
    step('high-resolution solve of a charge and a wire: one job per field, both shown')
  }

  // Probe on the wire: singular, the source is identified.
  await page.getByRole('radio', { name: /Select/ }).click()
  await rows().filter({ hasText: 'Wire' }).click()
  await page.getByRole('tab', { name: 'Results' }).click()
  await page.getByRole('button', { name: 'Place probe on the selected wire or loop' }).click()
  await page.getByText('On an ideal current filament').waitFor({ timeout: 10000 })
  assert.ok(await page.getByText(/The probe lies on the axis of wire/).isVisible())
  step('probe on an ideal wire: B and H singular, source identified, explanation shown')

  // Equations: the magnetostatic equations and their statuses follow the scene.
  await page.getByRole('tab', { name: 'Equations' }).click()
  await page.getByRole('button', { name: /Field of an infinite straight wire/ }).first().waitFor({ timeout: 10000 })
  assert.ok(await page.getByRole('button', { name: /Biot–Savart law \(integral form\)/ }).first().isVisible())
  assert.ok(await page.getByRole('button', { name: /Magnetic flux density in vacuum/ }).first().isVisible())
  step('equation registry lists the magnetostatic equations for this scene')

  // Preset 11: the loop opens on the xz cross-section; 3D shows its closed field lines.
  await page.getByRole('button', { name: /Circular current loop/ }).click()
  await settled()
  assert.ok(await page.getByText(/Plane y = 0\.00 m/).isVisible())
  assert.ok(await page.getByText(/B field lines: \d+ closed, \d+ truncated/).isVisible())
  await shot('18-loop-xz')
  await page.getByRole('radio', { name: '3D' }).click()
  await settled()
  await page.waitForTimeout(500)
  await shot('19-loop-3d')
  await page.getByRole('radio', { name: '2D' }).click()
  step('preset 11 opens on the cross-section through the loop axis; 3D view solved')

  // Hungarian magnetic labels.
  await page.getByRole('radio', { name: 'HU' }).click()
  await page.getByText('Mágneses mező (külön skála)').waitFor()
  await page.getByRole('radio', { name: 'EN' }).click()
  step('magnetic legend in Hungarian')

  // ------------------------------------------- Phase 3B: solenoids, toroids, magnets, Ampère
  let amperes = 0
  page.on('request', (r) => r.url().endsWith('/api/v1/ampere') && amperes++)
  const ampereVerified = async (enclosed) => {
    await page.getByRole('tab', { name: 'Ampère' }).click()
    const result = page.getByTestId('ampere-result')
    await result.getByText('verified', { exact: true }).waitFor({ timeout: 20000 })
    assert.ok(await result.getByText(enclosed).first().isVisible(), `enclosed current ${enclosed}`)
  }

  // Preset 12: a finite solenoid, its Ampère rectangle (12 turns) and the ideal comparison.
  await page.getByRole('button', { name: /^12\s*Finite solenoid/ }).click()
  await settled()
  assert.ok(await page.getByText(/Plane y = 0\.00 m/).isVisible())
  await ampereVerified(/^12(\.0+)? A$/)
  await shot('20-solenoid-ampere')
  await page.getByRole('tab', { name: 'Results' }).click()
  const sprobe = page.getByTestId('magnetic-probe')
  await sprobe.waitFor({ timeout: 10000 })
  assert.ok(await page.getByTestId('probe-comparisons').getByText('Ideal long solenoid').isVisible())
  await rows().first().click()
  await page.getByText('Field along the axis').waitFor({ timeout: 10000 })
  await shot('21-solenoid-profile')
  step('preset 12: finite solenoid solved; Ampère path verified (12 A); ideal comparison and axis profile')

  // Display-only Ampère settings: no field solve and no new Ampère evaluation.
  await page.getByRole('tab', { name: 'Ampère' }).click()
  const amperesBefore = amperes
  await quiet('Ampère normal hidden', () => page.getByRole('switch', { name: 'Show normal' }).click())
  await quiet('Ampère surface shown', () => page.getByRole('switch', { name: 'Show spanning surface' }).click())
  await page.waitForTimeout(500)
  assert.equal(amperes, amperesBefore, 'a display-only path setting re-evaluated Ampère')
  // Reversing the path is physical: a new evaluation with the opposite sign.
  await page.getByRole('button', { name: 'Counter-clockwise about local +z' }).click()
  await ampereVerified(/^−12(\.0+)? A$|^-12(\.0+)? A$/)
  step('Ampère display settings are visual-only; reversing the path flips the enclosed current')

  // Persistence of Ampère paths.
  const pname = `e2e 3B ${Date.now()}`
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.getByLabel('Project name').fill(pname)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByText(pname).first().waitFor()
  await page.reload()
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: pname }).getByRole('button', { name: 'Load' }).click()
  await rowCount(1)
  await page.getByRole('tab', { name: 'Ampère' }).click()
  assert.equal(await page.getByRole('list', { name: 'Ampère paths' }).locator('li').count(), 1)
  await page.getByTestId('ampere-result').getByText('verified', { exact: true }).waitFor({ timeout: 20000 })
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: pname }).getByRole('button', { name: 'Delete' }).click()
  await page.keyboard.press('Escape')
  step('a solenoid project with its Ampère path is saved and restored')

  // Preset 13: finite and ideal toroid; the model switch keeps both radii.
  await page.getByRole('button', { name: /^13\s*Toroidal solenoid/ }).click()
  await settled()
  await ampereVerified(/^24(\.0+)? A$/)
  await shot('22-toroid-finite')
  await page.getByRole('button', { name: 'Ideal continuous winding' }).click()
  await settled()
  await ampereVerified(/^24(\.0+)? A$/)
  await page.getByRole('tab', { name: 'Results' }).click()
  await page.getByTestId('magnetic-probe').getByText('inside the ideal toroid core').waitFor({ timeout: 10000 })
  assert.ok(await page.getByTestId('magnetic-probe').getByText(/B = μ₀μᵣH/).isVisible())
  await shot('23-toroid-ideal')
  await rows().first().click()
  await page.getByRole('tab', { name: 'Parameters' }).click()
  await solved('core radius', async () => {
    await page.getByRole('spinbutton', { name: 'Core radius' }).fill('0.025')
    await page.getByRole('spinbutton', { name: 'Core radius' }).press('Enter')
  })
  await solved('finite model', () => page.getByRole('combobox', { name: 'Toroid model' }).selectOption('toroid_finite'))
  await valueIs(page.getByRole('spinbutton', { name: 'Winding radius' }), '0.03')
  await valueIs(page.getByRole('spinbutton', { name: 'Core radius' }), '0.025')
  step('preset 13: finite and ideal toroid verified (24 A); probe in the core; model switch keeps both radii')

  // Preset 14: permanent magnet; H = B/μ0 − M inside, no free current, bound current shown.
  await page.getByRole('button', { name: /^14\s*Uniformly magnetized/ }).click()
  await settled()
  await ampereVerified(/^0 A$/)
  assert.ok(await page.getByTestId('ampere-result').getByText(/Bound current/).isVisible())
  await page.getByRole('tab', { name: 'Results' }).click()
  const magProbe = page.getByTestId('magnetic-probe')
  await magProbe.getByText('inside a permanent magnet').waitFor({ timeout: 10000 })
  assert.ok(await magProbe.getByText(/H = B\/μ₀ − M/).isVisible())
  await shot('24-magnet')
  // Probe on the side wall: the sheet is reported with one-sided limits.
  await rows().first().click()
  await page.getByRole('button', { name: 'Place probe on the selected wire or loop' }).click()
  await page.getByTestId('probe-boundary').getByText("On the magnet's current sheet").waitFor({ timeout: 10000 })
  assert.equal(await page.getByRole('table', { name: 'One-sided limits' }).locator('tbody tr').count(), 2)
  step("preset 14: magnet solved; Ampère H-circulation 0 with bound current; H = B/μ₀ − M; sheet one-sided limits")

  // A new solenoid with N = 1 disables the winding length (the magnet is removed first: a coil
  // added at the origin would lie exactly on its side wall).
  await page.getByRole('radio', { name: /Select/ }).click()
  await rows().first().click()
  await rows().first().blur()
  await page.keyboard.press('Delete')
  await rowCount(0)
  await page.getByRole('button', { name: 'Solenoid', exact: true }).click()
  await rowCount(1)
  await settled()
  await page.getByRole('tab', { name: 'Parameters' }).click()
  await solved('one turn', async () => {
    await page.getByRole('spinbutton', { name: 'Turns' }).fill('1')
    await page.getByRole('spinbutton', { name: 'Turns' }).press('Enter')
  })
  assert.ok(await page.getByRole('spinbutton', { name: 'Winding length' }).isDisabled())
  step('a solenoid can be added; with N = 1 the winding length is disabled')

  // Hungarian Ampère labels.
  await page.getByRole('radio', { name: 'HU' }).click()
  await page.getByRole('tab', { name: 'Ampère' }).click()
  await page.getByText('Ampère-féle gerjesztési törvény').waitFor()
  await page.getByRole('radio', { name: 'EN' }).click()
  step('Ampère panel in Hungarian')

  // ------------------------------------------------------- Phase 4A: induction (Faraday, Lenz)
  const faradayVerified = async () => {
    await page.getByRole('tab', { name: 'Faraday' }).click()
    await page.getByTestId('faraday-result').getByText('verified', { exact: true }).waitFor({ timeout: 20000 })
  }
  await page.getByRole('button', { name: /^15\s*Sinusoidally driven circular loop/ }).click()
  await settled()
  await page.getByTestId('time-bar').waitFor()
  await faradayVerified()
  const lenz = page.getByTestId('lenz-explanation')
  assert.ok(await lenz.getByText(/is increasing/).isVisible())
  assert.ok(await lenz.getByText(/against the boundary's traversal/).isVisible())
  await shot('25-faraday-loop')
  step('preset 15: time bar shown; ∮E_ind·dl = −dΦ/dt verified at t = 0; Lenz: increasing flux, E_ind against the traversal')

  // E_ind arrows and the |E_ind| map are display choices over the cached result.
  await page.getByRole('tab', { name: 'Display' }).click()
  await quiet('E_ind arrows', () => page.getByRole('combobox', { name: 'Magnetic vector field' }).selectOption('E_ind'))
  await quiet('|E_ind| colour map', () => page.getByRole('combobox', { name: 'Colour map' }).selectOption('E_ind'))
  await shot('26-e-ind')
  await quiet('dB/dt arrows', () => page.getByRole('combobox', { name: 'Magnetic vector field' }).selectOption('dB_dt'))
  await page.getByRole('combobox', { name: 'Magnetic vector field' }).selectOption('B')
  step('E_ind and dB/dt arrows and maps are visual-only (no new solve)')

  // Time is physics: a new instant re-solves; at the current's peak the flux is steady.
  const tField = page.getByRole('spinbutton', { name: 'Time', exact: true })
  await solved('time 0.25 s', async () => { await tField.fill('0.25'); await tField.press('Enter') })
  await faradayVerified()
  await page.getByTestId('lenz-explanation').getByText(/momentarily not changing/).waitFor({ timeout: 10000 })
  await solved('step forward', () => page.getByRole('button', { name: 'Step forward' }).click())
  await valueIs(tField, '0.26') // 0.25 is between grid points; the next one is 13·0.02
  step('changing the time re-solves; at the current peak (t = 0.25 s) the flux is steady; stepping uses the exact grid')

  // Deterministic playback: every displayed time is on the grid t = k·Δt.
  await page.getByRole('button', { name: 'Play' }).click()
  await page.waitForTimeout(1500)
  await page.getByRole('button', { name: 'Pause' }).click()
  await page.waitForTimeout(300)
  const played = Number(await tField.inputValue())
  assert.ok(played > 0.26, `playback did not advance (${played})`)
  assert.ok(Math.abs(played / 0.02 - Math.round(played / 0.02)) < 1e-6, `off-grid time ${played}`)
  step('playback advances on the deterministic time grid and pauses')

  // Probe at the simulation time: dB/dt and E_ind with the source current and its rate.
  await page.getByRole('tab', { name: 'Results' }).click()
  const ptime = page.getByTestId('probe-time')
  await ptime.waitFor({ timeout: 10000 })
  assert.ok(await ptime.getByRole('table', { name: 'Time-dependent field values' }).getByText(/V\/m/).first().isVisible())
  assert.ok(await ptime.getByRole('table', { name: 'Time-dependent field values' }).getByText(/T\/s/).first().isVisible())
  assert.ok(await ptime.getByText(/not the electrostatic field/).isVisible())
  step('probe shows t, ∂B/∂t, E_ind (labelled as the induced part) and I(t), dI/dt')

  // Preset 16: ramp; at the ramp start dI/dt jumps and both one-sided values are reported.
  await page.getByRole('button', { name: /^16\s*Ramping finite solenoid/ }).click()
  await settled()
  await faradayVerified()
  assert.ok(await page.getByTestId('lenz-explanation').getByText(/against the boundary's traversal/).isVisible())
  await solved('ramp start', async () => { await tField.fill('0'); await tField.press('Enter') })
  await page.getByText(/dI\/dt jumps at this instant/).first().waitFor({ timeout: 10000 })
  await shot('27-ramp-solenoid')
  step('preset 16: ramped solenoid verified; the corner at t = 0 is reported')

  // Preset 21: toroid and passive measurement loop: mutual inductance and reciprocity.
  await page.getByRole('button', { name: /^21\s*Finite-turn toroid and mutual induction/ }).click()
  await settled()
  await faradayVerified()
  await page.getByTestId('mutual').getByText(/reciprocity M₁₂ = M₂₁ verified/).waitFor({ timeout: 20000 })
  await shot('28-toroid-mutual')
  step('preset 21: toroid and measurement loop verified; M12 = M21 (reciprocity)')

  // Persistence: profiles, measurement surfaces and the time survive a reload.
  await solved('time 0.003', async () => { await tField.fill('0.003'); await tField.press('Enter') })
  const iname = `e2e 4A ${Date.now()}`
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.getByLabel('Project name').fill(iname)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByText(iname).first().waitFor()
  await page.reload()
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: iname }).getByRole('button', { name: 'Load' }).click()
  await rowCount(1)
  await valueIs(page.getByRole('spinbutton', { name: 'Time', exact: true }), '0.003')
  await faradayVerified()
  assert.equal(await page.getByRole('list', { name: 'Measurement surfaces' }).locator('li').count(), 1)
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: iname }).getByRole('button', { name: 'Delete' }).click()
  await page.keyboard.press('Escape')
  step('a toroid project with its profile, measurement surface and time is saved and restored')

  // Profile editor: a new loop becomes time-dependent with a sinusoidal profile, and back.
  await page.getByRole('button', { name: /^11\s*Circular current loop/ }).click()
  await settled()
  await page.getByRole('radio', { name: /Select/ }).click()
  await rows().first().click()
  await page.getByRole('tab', { name: 'Parameters' }).click()
  await solved('sinusoidal profile', () => page.getByRole('combobox', { name: 'Current profile' }).selectOption('sinusoidal'))
  await page.getByTestId('time-bar').waitFor()
  await page.getByTestId('profile-editor').getByRole('img').waitFor({ timeout: 10000 })
  await solved('constant again', () => page.getByRole('combobox', { name: 'Current profile' }).selectOption('none'))
  // No longer time-dependent: the waveform is gone. (The time bar stays while measurement
  // surfaces exist; preset 21's surface is kept, like Gaussian surfaces and Ampère paths.)
  assert.equal(await page.getByTestId('profile-editor').getByRole('img').count(), 0)
  step('profile editor: sinusoidal profile makes the scene time-dependent (waveform from the engine); constant restores it')

  // ------------------------------------------- Phase 4B: moving conductors and the Lorentz force
  await page.getByRole('button', { name: /^22\s*Sliding-rod generator/ }).click()
  await settled()
  await page.getByTestId('time-bar').waitFor()
  await faradayVerified()
  const moving = page.getByTestId('moving-result')
  await moving.waitFor({ timeout: 20000 })
  assert.match(await page.getByTestId('emf-total').innerText(), /µV/)
  await page.getByTestId('uniform-reference').getByText(/Uniform-field approximation/).waitFor()
  await page.getByTestId('legend-motion').waitFor()
  await shot('29-sliding-rod')
  step('preset 22: sliding rod verified (motional EMF = −dΦ/dt from flux values); BLv shown as labelled reference')
  await tField.fill('0.3')
  await tField.press('Enter')
  await page.getByTestId('faraday-result').getByText('Motion undefined', { exact: true }).waitFor({ timeout: 20000 })
  await page.getByRole('combobox', { name: 'Velocity at a jump' }).selectOption('left')
  await faradayVerified()
  await page.getByRole('combobox', { name: 'Velocity at a jump' }).selectOption('undefined')
  step('at the rod stop (t = 0.3 s) the EMF is undefined; a one-sided convention evaluates it')

  await page.getByRole('button', { name: /^23\s*Generator principle/ }).click()
  await settled()
  await faradayVerified()
  for (let k = 0; k < 3; k++) {
    await page.getByRole('button', { name: 'Step forward' }).click()
    await faradayVerified()
    await page.waitForTimeout(300)
  }
  await page.getByTestId('waveforms').waitFor({ timeout: 20000 })
  await page.getByTestId('motion-editor').waitFor()
  await shot('30-rotating-coil')
  step('preset 23: rotating coil verified at successive times; waveform built from computed results')

  await page.getByRole('button', { name: /^25\s*Combined transformer and motional/ }).click()
  await settled()
  await faradayVerified()
  assert.ok(await moving.getByText(/Transformer EMF/).isVisible())
  assert.ok(await moving.getByText(/Motional EMF/).isVisible())
  step('preset 25: transformer and motional EMF shown separately; generalized law verified')

  await page.getByRole('button', { name: /^24\s*Charged particle in a magnetic field/ }).click()
  await settled()
  await page.getByRole('tab', { name: 'Lorentz' }).click()
  const lres = page.getByTestId('lorentz-result')
  await lres.getByText('Complete', { exact: true }).waitFor({ timeout: 20000 })
  const fBefore = await page.getByTestId('force-magnitude').innerText()
  await page.getByTestId('trajectory-result').getByText('Completed', { exact: true }).waitFor({ timeout: 60000 })
  const dK = Math.abs(Number(await page.getByTestId('energy-change').innerText()))
  assert.ok(dK < 1e-10, `kinetic energy changed in a magnetic-only field: ${dK}`)
  await page.getByTestId('legend-lorentz').waitFor()
  await shot('31-proton-helix')
  // An alpha particle (2e) doubles |F|; an electron (−e) keeps |F| but reverses F.
  await page.getByRole('button', { name: 'Alpha' }).click()
  await page.waitForFunction((b) => {
    const el = document.querySelector('[data-testid="force-magnitude"]')
    return el && el.textContent !== b
  }, fBefore, { timeout: 20000 })
  await page.getByRole('button', { name: 'Electron' }).click()
  await page.waitForFunction((b) => {
    const el = document.querySelector('[data-testid="force-magnitude"]')
    return el && el.textContent === b
  }, fBefore, { timeout: 20000 })
  step('preset 24: Lorentz force complete, P_B = 0; proton trajectory completed with constant kinetic energy; species change updates the force')

  // Persistence of the test charge and moving surfaces.
  const bname = `e2e 4B ${Date.now()}`
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.getByLabel('Project name').fill(bname)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByText(bname).first().waitFor()
  await page.reload()
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: bname }).getByRole('button', { name: 'Load' }).click()
  await page.getByRole('tab', { name: 'Lorentz' }).click()
  await page.getByTestId('lorentz-result').getByText('Complete', { exact: true }).waitFor({ timeout: 20000 })
  await valueIs(page.getByRole('spinbutton', { name: 'Charge', exact: true }), '-1.6021766e-19')
  await page.getByRole('button', { name: 'Projects' }).click()
  await page.locator('li', { hasText: bname }).getByRole('button', { name: 'Delete' }).click()
  await page.keyboard.press('Escape')
  step('the test charge (electron) and its trajectory settings are saved and restored with the project')

  // Hungarian Faraday labels.
  await page.getByRole('radio', { name: 'HU' }).click()
  await page.getByRole('tab', { name: 'Faraday' }).click()
  await page.getByText('Faraday-törvény és mágneses fluxus').waitFor()
  await page.getByRole('tab', { name: 'Lorentz' }).click()
  await page.getByText('Próbatöltés', { exact: true }).first().waitFor()
  await page.getByRole('radio', { name: 'EN' }).click()
  step('Faraday panel in Hungarian')

  assert.deepEqual(errors, [], 'browser console errors')
  step('no browser console errors')
  await browser.close()
}

main().catch((e) => {
  console.error('FAILED:', e.message ?? e)
  process.exit(1)
})
