terraform {
  required_version = ">= 1.6.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 5.0"
    }
  }
}

variable "cloudflare_zone_id" {
  description = "Zone ID de Cloudflare que sirve TASKFLOW_DOMAIN."
  type        = string
  sensitive   = true
}

resource "cloudflare_ruleset" "taskflow_rate_limits" {
  zone_id     = var.cloudflare_zone_id
  name        = "TaskFlow anonymous endpoint rate limits"
  description = "Distributed abuse limits for login and frontend telemetry."
  kind        = "zone"
  phase       = "http_ratelimit"

  rules = [
    {
      ref         = "taskflow_login_per_ip"
      description = "Login: five requests per IP per minute"
      expression  = "(http.request.method eq \"POST\" and http.request.uri.path eq \"/api/auth/login\")"
      action      = "block"
      action_parameters = {
        response = {
          status_code  = 429
          content_type = "application/json"
          content      = "{\"detail\":\"Demasiados intentos de inicio de sesión. Inténtalo más tarde.\"}"
        }
      }
      ratelimit = {
        characteristics     = ["cf.colo.id", "ip.src"]
        period              = 60
        requests_per_period = 5
        mitigation_timeout  = 900
      }
    },
    {
      ref         = "taskflow_frontend_telemetry_per_ip"
      description = "Telemetry: thirty reports per IP per minute"
      expression  = "(http.request.method eq \"POST\" and http.request.uri.path eq \"/api/telemetry/frontend-errors\")"
      action      = "block"
      action_parameters = {
        response = {
          status_code  = 429
          content_type = "application/json"
          content      = "{\"detail\":\"Demasiados reportes de telemetría. Inténtalo más tarde.\"}"
        }
      }
      ratelimit = {
        characteristics     = ["cf.colo.id", "ip.src"]
        period              = 60
        requests_per_period = 30
        mitigation_timeout  = 60
      }
    },
  ]
}
