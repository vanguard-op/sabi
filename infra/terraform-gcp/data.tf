# Cross-state lookups. The network, run subnet, private-services range and
# peering live in the long-lived foundation state (infra/terraform-gcp/foundation,
# D-058); this workload root reads the two it needs by name. Applying the
# foundation before this root guarantees they exist, so no cross-state
# `depends_on` is possible or needed.

data "google_compute_network" "main" {
  name = local.prefix
}

data "google_compute_subnetwork" "run" {
  name   = "${local.prefix}-run"
  region = var.region
}
