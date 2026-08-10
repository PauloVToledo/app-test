const reportedErrors = new Set()

function currentPath() {
  return window.location.pathname
}

export function reportFrontendError(kind, error) {
  const message = String(error?.message || error || 'Error de frontend desconocido').slice(0, 500)
  const stack = typeof error?.stack === 'string' ? error.stack.slice(0, 4000) : undefined
  const key = `${kind}:${message}:${currentPath()}`
  if (reportedErrors.has(key)) return
  reportedErrors.add(key)

  const payload = JSON.stringify({ kind, message, stack, path: currentPath() })
  const body = new Blob([payload], { type: 'application/json' })
  navigator.sendBeacon('/api/telemetry/frontend-errors', body)
}
