# Cloud Run domain mapping: the sole TLS terminator for the environment (D-032).
# Each mapped hostname gets a managed certificate automatically; the DNS records
# the operator must add at Namecheap are the mapping's resource records, output
# for the operator to copy (see outputs.tf).
#
# The apex ahmadkhidir.com is never touched: only subdomains of
# sabi.ahmadkhidir.com are mapped.

resource "google_cloud_run_domain_mapping" "services" {
  for_each = local.services

  location = var.region
  name     = each.value.host

  metadata {
    namespace = var.project_id
  }

  spec {
    # The Cloud Run service this hostname routes to. The service must exist.
    route_name = local.service_names[each.key]

    # Managed certificate: Google provisions and renews the TLS certificate for
    # the verified hostname. No manual certificate is uploaded.
    certificate_mode = "AUTOMATIC"
  }
}
