# Networking for Cloud Run private egress and the private-IP Cloud SQL
# instance. No load balancer, no static IP, no Memorystore: Cloud Run serves
# directly and TLS comes from Cloud Run domain mapping (D-032).
#
# This root is the long-lived foundation of D-058: a whole-stack `destroy` was
# unreliable because Cloud Run Direct VPC egress leaves a Google-managed
# `serverless-ipv4-cloudrun-*` reservation that is released asynchronously and
# blocks deletion of both the run subnet and the service-networking connection.
# The network and peering cost nothing, so they persist here while
# `gcp-destroy` tears down only the workload root.

resource "google_compute_network" "main" {
  name                    = local.prefix
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  # The compute and service-networking APIs must be live before the network and
  # its peering are created (services.tf).
  depends_on = [google_project_service.required]
}

# Serverless subnet used by the Cloud Run direct VPC egress interfaces. The
# subnet is only reachable from Cloud Run; it has no public address space.
resource "google_compute_subnetwork" "run" {
  name          = "${local.prefix}-run"
  region        = var.region
  network       = google_compute_network.main.id
  ip_cidr_range = "10.20.0.0/24"

  private_ip_google_access = true
}

# Private services access: the reserved range and peering that give the Cloud SQL
# instance a private IP reachable from the Cloud Run subnet. No public IP is
# attached to the instance (NFR-022: database traffic never crosses the internet).
resource "google_compute_global_address" "private_services" {
  name          = "${local.prefix}-sql-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}

# Firewall for the database port from the Cloud Run egress subnet only. The
# instance has no public address, so this rule is the only path to Postgres.
resource "google_compute_firewall" "database" {
  name      = "${local.prefix}-db"
  network   = google_compute_network.main.id
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }

  source_ranges = [google_compute_subnetwork.run.ip_cidr_range]

  target_tags = ["${local.prefix}-db"]
}
