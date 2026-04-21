# AWS Terraform Configuration - GWS-Model Project
# Region: ap-southeast-1 (Singapore)

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "ap-southeast-1"
}

# --- VPC & Networking ---

resource "aws_vpc" "gws_model" {
  cidr_block           = "172.18.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "GWS-Model"
  }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.gws_model.id

  tags = {
    Name = "IGW-testbed"
  }
}

# Subnet 1: PublicSN
resource "aws_subnet" "public_sn" {
  vpc_id                  = aws_vpc.gws_model.id
  cidr_block              = "172.18.0.0/24"
  availability_zone       = "ap-southeast-1a"
  map_public_ip_on_launch = true

  tags = {
    Name = "PublicSN"
  }
}

# Subnet 2: LAN_SN
resource "aws_subnet" "lan_sn" {
  vpc_id            = aws_vpc.gws_model.id
  cidr_block        = "172.18.1.0/24"
  availability_zone = "ap-southeast-1a"

  tags = {
    Name = "LAN_SN"
  }
}

# --- Key Pair ---

resource "tls_private_key" "global_key" {
  algorithm = "ED25519"
}

resource "aws_key_pair" "deployer" {
  key_name   = "gws-shared-key"
  public_key = tls_private_key.global_key.public_key_openssh
}

# Local file for the private key (to be used for SSH)
resource "local_file" "private_key" {
  content         = tls_private_key.global_key.private_key_pem
  filename        = "gws-shared-key.pem"
  file_permission = "0600"
}

# --- Security Groups ---

# SG 1: Tailscale-IP (Using standard Tailscale range 100.64.0.0/10)
resource "aws_security_group" "tailscale_sg" {
  name        = "Tailscale-IP"
  description = "Allow all traffic from Tailscale"
  vpc_id      = aws_vpc.gws_model.id

  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["100.64.0.0/10"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# SG 2: Firewall-SG
resource "aws_security_group" "firewall_sg" {
  name        = "Firewall-SG"
  description = "Main Firewall Security Group"
  vpc_id      = aws_vpc.gws_model.id

  # All traffic from SG 1 (Tailscale)
  ingress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.tailscale_sg.id]
  }

  # HTTPS
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTP
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # ICMP Echo (Ping)
  ingress {
    from_port   = -1
    to_port     = -1
    protocol    = "icmp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # All traffic from Subnet 1 & 2
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["172.18.0.0/24", "172.18.1.0/24"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# SG 3: Edge-FW
resource "aws_security_group" "edge_fw_sg" {
  name        = "Edge-FW"
  description = "Edge Security Group"
  vpc_id      = aws_vpc.gws_model.id

  # All traffic from SG 2
  ingress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.firewall_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Instances ---

# Data to get latest Ubuntu 22.04 AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# 1. Firewall Instance
resource "aws_instance" "firewall" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = "t3.nano"
  subnet_id                   = aws_subnet.public_sn.id
  vpc_security_group_ids      = [aws_security_group.firewall_sg.id]
  key_name                    = aws_key_pair.deployer.key_name
  associate_public_ip_address = true
  source_dest_check           = false # Important for NAT/Firewall routing

  tags = {
    Name = "firewall"
  }
}

# 2. Edge-D (Spot Instance)
resource "aws_spot_instance_request" "edge_d" {
  ami                  = data.aws_ami.ubuntu.id
  instance_type        = "c5.xlarge"
  subnet_id              = aws_subnet.lan_sn.id
  vpc_security_group_ids = [aws_security_group.edge_fw_sg.id]
  key_name               = aws_key_pair.deployer.key_name

  root_block_device {
    volume_size = 60
    volume_type = "gp3"
  }

  tags = {
    Name = "edge-d"
  }
}

# 3. PMU-C
resource "aws_instance" "pmu_d" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.lan_sn.id
  vpc_security_group_ids = [aws_security_group.edge_fw_sg.id]
  key_name               = aws_key_pair.deployer.key_name

  tags = {
    Name = "pmu-d"
  }
}

# --- Route Tables ---

# Public RT for PublicSN
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.gws_model.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "Public_RT"
  }
}

resource "aws_route_table_association" "public_assoc" {
  subnet_id      = aws_subnet.public_sn.id
  route_table_id = aws_route_table.public_rt.id
}

# LAN RT for LAN_SN (Routes through Firewall instance)
resource "aws_route_table" "lan_rt" {
  vpc_id = aws_vpc.gws_model.id

  route {
    cidr_block           = "0.0.0.0/0"
    network_interface_id = aws_instance.firewall.primary_network_interface_id
  }

  tags = {
    Name = "LAN_RT"
  }
}

resource "aws_route_table_association" "lan_assoc" {
  subnet_id      = aws_subnet.lan_sn.id
  route_table_id = aws_route_table.lan_rt.id
}

# Outputs
output "firewall_public_ip" {
  value = aws_instance.firewall.public_ip
}

output "private_key_path" {
  value = local_file.private_key.filename
}