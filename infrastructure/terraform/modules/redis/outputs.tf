output "replication_group_id" {
  description = "The ID of the ElastiCache replication group"
  value       = aws_elasticache_replication_group.main.id
}

output "primary_endpoint_address" {
  description = "The address of the primary endpoint for read/write Redis operations"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "reader_endpoint_address" {
  description = "The address of the reader endpoint for read-only Redis queries"
  value       = aws_elasticache_replication_group.main.reader_endpoint_address
}

output "port" {
  description = "The port number on which the cache accepts connections"
  value       = aws_elasticache_replication_group.main.port
}
