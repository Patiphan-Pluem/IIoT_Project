output "private_key_pem" {
    description = "Save this content to 'cloud.pem' to SSH"
    value = tls_private_key.cloud_pk.private_key_pem
    sensitive = true
}

output "cloud_public_ip" {
    description = "Elastic IP of the Cloud Node"
    value = aws_eip.cloud_eip.public_ip
}

output "get_token_command" {
    description = "Run this to get the JOIN TOKEN"
    value = "ssh -i cloud.pem ubuntu@${aws_eip.cloud_eip.public_ip} 'sudo cat /var/lib/rancher/k3s/server/node-token'"
}