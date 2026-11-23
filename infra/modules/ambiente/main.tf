terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.36"
    }
  }
}

variable "name" {
  type = string
}

resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = var.name
    labels = {
      "pod-security.kubernetes.io/enforce"         = "restricted"
      "pod-security.kubernetes.io/enforce-version" = "v1.34"
      "pod-security.kubernetes.io/audit"           = "restricted"
      "pod-security.kubernetes.io/warn"            = "restricted"
    }
  }
}

output "name" {
  value = kubernetes_namespace_v1.this.metadata[0].name
}
