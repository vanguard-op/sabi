output "network_name" {
  description = "VPC name the workload root looks up with data.google_compute_network.main."
  value       = google_compute_network.main.name
}

output "run_subnet_name" {
  description = "Serverless subnet name the workload root looks up with data.google_compute_subnetwork.run."
  value       = google_compute_subnetwork.run.name
}
