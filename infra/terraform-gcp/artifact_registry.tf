# Artifact Registry: one repository holding the API, AI, payment-module, and
# console images the `up` workflow builds and pushes.

resource "google_artifact_registry_repository" "images" {
  repository_id = var.artifact_registry_repo_id
  location      = var.region
  format        = "DOCKER"
  description   = "Sabi staging service images (api, ai, payments, console)."
  labels        = local.labels

  depends_on = [google_project_service.required]
}
