output "urls" {
  description = "Mapped service URLs. Reachable once the DNS records below are added at Namecheap."
  value = {
    for k, v in local.services : k => "https://${v.host}"
  }
}

output "cloud_run_urls" {
  description = "Cloud Run service URLs (the *.run.app addresses behind the mappings)."
  value = merge(
    { for k, v in google_cloud_run_v2_service.public_services : k => v.uri },
    { for k, v in google_cloud_run_v2_service.private_services : k => v.uri },
  )
}

output "dns_records" {
  description = <<-EOT
    The exact DNS records to add at Namecheap for managed TLS. Each mapping
    reports its required records; add every record shown, then wait for the
    certificates to move to ACTIVE.
  EOT
  value = {
    for k, mapping in google_cloud_run_domain_mapping.services : k => {
      hostname = mapping.name
      records = [
        for rr in mapping.status[0].resource_records : {
          type   = rr.type
          name   = rr.name
          rrdata = rr.rrdata
        }
      ]
    }
  }
}

output "database_private_ip" {
  description = "Private IP of the Postgres instance (no public address)."
  value       = google_sql_database_instance.main.private_ip_address
}

output "database_connection_name" {
  description = "Cloud SQL instance connection name, for the Cloud SQL connector."
  value       = google_sql_database_instance.main.connection_name
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository the `up` workflow pushes images to."
  value       = google_artifact_registry_repository.images.repository_id
}

output "image_repository_prefix" {
  description = "Image prefix the `up` workflow appends an image key and tag to."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "service_accounts" {
  description = "Runtime service accounts, one per Cloud Run service."
  value = {
    api      = google_service_account.api.email
    ai       = google_service_account.ai.email
    payments = google_service_account.payments.email
    console  = google_service_account.console.email
  }
}
