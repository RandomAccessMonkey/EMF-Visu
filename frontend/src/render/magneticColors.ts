// Visual encodings of magnetic quantities, kept distinct from the electric ones so E and B are
// never confused. Colours only: no physical value is derived here.
export const MAGNETIC_SOURCE_COLOR = '#c084fc' // current-carrying wires and loops
export const MAGNET_COLOR = '#f87171' // permanent magnets (body outline, north end)
export const MAGNET_SOUTH_COLOR = '#60a5fa' // south end of a magnet
export const CORE_COLOR = '#94a3b8' // ideal toroid core
export const AMPERE_PATH_COLOR = '#34d399' // Ampère paths (mathematical, not physical)
export const MAGNETIC_LINE_COLOR = '#d8b4fe' // B field lines
export const MAGNETIC_NUMERICAL_LINE_COLOR = '#fbbf24' // numerically ended B lines (as for E)
/** Per-source colours for individual contributions (cycled). */
export const CONTRIBUTION_COLORS = ['#f472b6', '#34d399', '#fbbf24', '#60a5fa', '#f87171', '#a3e635', '#22d3ee', '#e879f9']
