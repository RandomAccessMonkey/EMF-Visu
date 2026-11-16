import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } })

function webgl2Available(): boolean {
  try {
    return document.createElement('canvas').getContext('webgl2') !== null
  } catch {
    return false
  }
}

const root = createRoot(document.getElementById('root')!)
if (webgl2Available()) {
  root.render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </StrictMode>,
  )
} else {
  // Rendering needs WebGL 2; say so instead of showing an empty canvas.
  const hu = navigator.language.startsWith('hu')
  root.render(
    <p style={{ padding: 24 }}>
      {hu
        ? 'Ez az alkalmazás WebGL 2-t igényel, amely ebben a böngészőben vagy ezen az eszközön nem érhető el.'
        : 'This application requires WebGL 2, which is not available in this browser or on this device.'}
    </p>,
  )
}
