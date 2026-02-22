terraform {
  required_providers {
    aws = {
        source = "hashicorp/aws"
        version = "~> 5.0"
    }
  }
}

provider "aws" {
    region = var.aws_region
}

# --- VPC 1: Cloud Network ---
resource "aws_vpc" "cloud_vpc" {
    cidr_block = "172.16.0.0/16"
    enable_dns_hostnames = true
    tags = { Name = "${var.project_name}-cloud-vpc" }
}

resource "aws_internet_gateway" "cloud_igw" {
    vpc_id = aws_vpc.cloud_vpc.id
    tags = { Name = "${var.project_name}-cloud-igw" }
}

resource "aws_route_table" "cloud_rt" {
    vpc_id = aws_vpc.cloud_vpc.id
    route {
        cidr_block = "0.0.0.0/0"
        gateway_id = aws_internet_gateway.cloud_igw.id
    }
    tags = { Name = "cloud-public-rt" }
}

resource "aws_subnet" "cloud_subnet" {
    vpc_id = aws_vpc.cloud_vpc.id
    cidr_block = "172.16.1.0/24"
    availability_zone = var.cloud_az
    map_public_ip_on_launch = true
    tags = { Name = "cloud-subnet-1a" }
}

resource "aws_route_table_association" "cloud_assoc" {
    subnet_id = aws_subnet.cloud_subnet.id
    route_table_id = aws_route_table.cloud_rt.id
}

# --- Security Group (Cloud) ---
resource "aws_security_group" "cloud_sg" {
    vpc_id = aws_vpc.cloud_vpc.id
    name = "${var.project_name}-cloud-sg"
    
    # SSH
    ingress {
        from_port = 22
        to_port = 22
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"] 
    }
    # K3s API
    ingress {
        from_port = 6443
        to_port = 6443
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }
    # WireGuard / VXLAN
    ingress {
        from_port = 51820
        to_port = 51820
        protocol = "udp"
        cidr_blocks = ["0.0.0.0/0"]
    }
    ingress {
        from_port = 4789
        to_port = 4789
        protocol = "udp"
        cidr_blocks = ["0.0.0.0/0"]
    }
    # Cilium Health Check
    ingress {
        from_port = 4240
        to_port = 4240
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }
    # Hubble seerver
    ingress {
        from_port = 4244
        to_port = 4244
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }
    # Hubble Relay
    ingress {
        from_port = 4245
        to_port = 4245
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }
    # Ingress HTTP/HTTPS
    ingress {
        from_port = 80
        to_port = 80
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }
    ingress {
        from_port = 443
        to_port = 443
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }
    #ICMP
    ingress {
        from_port = 0
        to_port = 0
        protocol = "icmp"
        cidr_blocks = ["0.0.0.0/0"]
    }
    
    egress {
        from_port = 0
        to_port = 0
        protocol = "-1"
        cidr_blocks = ["0.0.0.0/0"]
    }
    tags = { Name = "cloud-sg" }
}

# --- Key Pair ---
resource "tls_private_key" "cloud_pk" { algorithm = "ED25519" }
resource "aws_key_pair" "cloud_key" {
    key_name = "${var.project_name}-cloud-key"
    public_key = tls_private_key.cloud_pk.public_key_openssh
}

# --- Cloud Instance ---
data "aws_ami" "ubuntu" {
    most_recent = true
    filter { 
        name = "name"
        values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"] 
        }
    owners = ["099720109477"]
}

resource "aws_instance" "cloud_node" {
    ami = data.aws_ami.ubuntu.id
    instance_type = "m7i-flex.large"
    subnet_id = aws_subnet.cloud_subnet.id
    vpc_security_group_ids = [aws_security_group.cloud_sg.id]
    key_name = aws_key_pair.cloud_key.key_name

    root_block_device {
        volume_size = 30
        volume_type = "gp3"
        delete_on_termination = true
    }

    instance_market_options {
    market_type = "spot"
    spot_options {
      max_price = "0.07" # ตั้งราคาเพดานไว้เหนือจุดพีค 3 เดือน
      spot_instance_type = "persistent" # พยายามเปิดเครื่องใหม่ให้ทันทีถ้าโดนดึงคืน
      instance_interruption_behavior = "stop"
        }
    }

    # ปิด Source/Dest Check สำหรับ Cilium
    source_dest_check = false
    user_data = <<-EOF
              #!/bin/bash
              apt-get update
              EOF

    tags = { Name = "cloud-server", NodeType = "cloud" }
}

# --- Elastic IP ---
resource "aws_eip" "cloud_eip" {
  instance = aws_instance.cloud_node.id
  domain   = "vpc"
  tags     = { Name = "${var.project_name}-cloud-eip" }
}