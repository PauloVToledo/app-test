import { Component } from 'react'
import { reportFrontendError } from './frontendTelemetry.js'

export class FrontendErrorBoundary extends Component {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error) {
    reportFrontendError('error', error)
  }

  render() {
    if (this.state.hasError) {
      return <main className="login-page"><p className="api-error" role="alert">Ocurrió un error inesperado. Intenta recargar la página.</p></main>
    }
    return this.props.children
  }
}
