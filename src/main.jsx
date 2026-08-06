import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { FrontendErrorBoundary } from './FrontendErrorBoundary.jsx'
import { reportFrontendError } from './frontendTelemetry.js'

window.addEventListener('error', (event) => reportFrontendError('error', event.error || event.message))
window.addEventListener('unhandledrejection', (event) => reportFrontendError('unhandledrejection', event.reason))

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <FrontendErrorBoundary>
      <App />
    </FrontendErrorBoundary>
  </StrictMode>,
)
