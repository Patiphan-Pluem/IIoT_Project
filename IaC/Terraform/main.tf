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
    
    dynamic "ingress" {
    for_each = [
      { port = 0,     proto = "icmp", desc = "Allow ICMP" },
      { port = 22,    proto = "tcp",  desc = "SSH" },
      { port = 53,    proto = "tcp",  desc = "DNS TCP" },
      { port = 53,    proto = "udp",  desc = "DNS UDP" },
      { port = 80,    proto = "tcp",  desc = "HTTP" },
      { port = 443,   proto = "tcp",  desc = "HTTPS" },
      { port = 3000,  proto = "tcp",  desc = "Grafana/App" },
      { port = 4240,  proto = "tcp",  desc = "Cilium Health" },
      { port = 4244,  proto = "tcp",  desc = "Cilium Hubble" },
      { port = 4245,  proto = "tcp",  desc = "Cilium Hubble Relay" },
      { port = 4789,  proto = "udp",  desc = "VXLAN Overlay" },
      { port = 6443,  proto = "tcp",  desc = "K8s API Server" },
      { port = 8472,  proto = "udp",  desc = "Cilium VXLAN" },
      { port = 9090,  proto = "tcp",  desc = "Prometheus" },
      { port = 10250, proto = "tcp",  desc = "Kubelet API" },
      { port = 15010, proto = "tcp",  desc = "Istio Control Plane" },
      { port = 15012, proto = "tcp",  desc = "Istio Control Plane TLS" },
      { port = 15021, proto = "tcp",  desc = "Istio Health Check" },
      { port = 32494, proto = "tcp",  desc = "K8s NodePort Service" },
      { port = 51871, proto = "udp",  desc = "Wireguard Tunnel" }
    ]
    content {
      description      = ingress.value.desc
      from_port        = ingress.value.port
      to_port          = ingress.value.port
      protocol         = ingress.value.proto
      cidr_blocks      = ["0.0.0.0/0"]
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      security_groups  = []
      self             = false
        }
    }
    egress {
        from_port   = 0
        to_port     = 0
        protocol    = "-1" # Allow all traffic out
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
data "aws_ami" "my_custom_ubuntu" {
    most_recent = true
    owners      = ["self"] 
    filter {
        name   = "name"
        values = ["iiot-backup-before-scale"] 
    }
}

resource "aws_instance" "cloud_node" {
    ami = data.aws_ami.my_custom_ubuntu.id
    instance_type = "t3a.xlarge"  #"m7i-flex.large"
    subnet_id = aws_subnet.cloud_subnet.id
    vpc_security_group_ids = [aws_security_group.cloud_sg.id]
    key_name = aws_key_pair.cloud_key.key_name

    root_block_device {
        volume_size = 60 #30
        volume_type = "gp3"
        delete_on_termination = true
    }

    instance_market_options {
    market_type = "spot"
    spot_options {
      max_price = "0.12" # ตั้งราคาเพดานไว้เหนือจุดพีค 3 เดือน 0.07
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
    lifecycle {
        ignore_changes = [ami]
    }
    tags = { Name = "cloud-server", NodeType = "cloud" }
}

# --- Elastic IP ---
resource "aws_eip" "cloud_eip" {
  instance = aws_instance.cloud_node.id
  domain   = "vpc"
  tags     = { Name = "${var.project_name}-cloud-eip" }
}