// Visual encodings of magnetic quantities, kept distinct from the electric ones so E and B are
// never confused. Colours only: no physical value is derived here.
export const MAGNETIC_SOURCE_COLOR = '#c084fc' // current-carrying wires and loops
export const MAGNET_COLOR = '#f87171' // permanent magnets (body outline, north end)
export const MAGNET_SOUTH_COLOR = '#60a5fa' // south end of a magnet
export const CORE_COLOR = '#94a3b8' // ideal toroid core
export const INDUCED_E_COLOR = '#fb923c' // induced electric field E_ind (Phase 4A)
export const FLUX_SURFACE_COLOR = '#22d3ee' // Faraday measurement surfaces (Phase 4A)
export const AMPERE_PATH_COLOR = '#34d399' // Ampère paths (mathematical, not physical)
export const MAGNETIC_LINE_COLOR = '#d8b4fe' // B field lines
export const MAGNETIC_NUMERICAL_LINE_COLOR = '#fbbf24' // numerically ended B lines (as for E)
/** Per-source colours for individual contributions (cycled). */
export const CONTRIBUTION_COLORS = ['#f472b6', '#34d399', '#fbbf24', '#60a5fa', '#f87171', '#a3e635', '#22d3ee', '#e879f9']
// Phase 4B: moving conductors and the test charge.
export const CONDUCTOR_VELOCITY_COLOR = '#e5e7eb' // material velocity u of a conductor
export const MOTIONAL_COLOR = '#f472b6' // motional term u × B (not an electric field)
export const STATIONARY_SEGMENT_COLOR = '#64748b' // rails and other stationary segments
export const MOVING_SEGMENT_COLOR = '#22d3ee' // the moving rod / moving loop
export const PARTICLE_COLOR = '#facc15' // test charge
export const PARTICLE_VELOCITY_COLOR = '#f8fafc' // particle velocity v
export const FORCE_E_COLOR = '#fb923c' // electric force qE
export const FORCE_B_COLOR = '#a78bfa' // magnetic force q v × B
export const FORCE_TOTAL_COLOR = '#ef4444' // total Lorentz force
export const TRAJECTORY_COLOR = '#fde047' // particle path
