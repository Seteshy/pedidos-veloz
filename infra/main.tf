terraform {
  required_version = ">= 1.6.0, < 2.0.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.36"
    }
  }
}

provider "kubernetes" {
  config_path    = var.kubeconfig_path
  config_context = var.kube_context
}

module "ambiente" {
  source = "./modules/ambiente"
  name   = "veloz"
}

output "namespace" {
  value = module.ambiente.name
}
