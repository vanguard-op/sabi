provider "google" {
  project = var.project_id
  region  = var.region

  default_labels = local.labels
}

locals {
  # Environment naming, identical to the workload root (infra/terraform-gcp).
  # The names computed here are the names the workload root looks up by name
  # through its google_compute_network.main / google_compute_subnetwork.run
  # data sources, so the two states agree without a remote-state reference.
  prefix = "${var.project}-${var.environment}"

  labels = {
    project     = var.project
    environment = var.environment
    managed-by  = "terraform"
  }
}
