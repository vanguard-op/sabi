# Managed secret store (NFR-024). Terraform creates the container only; real
# values are written out-of-band (console, CLI, or a CI secret), never from the
# repo and never in Terraform state. The runner identity reads this secret at
# boot and injects it into the process environment.

resource "aws_secretsmanager_secret" "app" {
  name        = "${var.project}/${var.environment}/app"
  description = "Application secrets: session signing, recovery pepper, model provider key, provider credentials."

  # Dev secrets are disposable; higher environments keep a recovery window so an
  # accidental delete can be undone.
  recovery_window_in_days = var.environment == "prod" ? 30 : 0
}
