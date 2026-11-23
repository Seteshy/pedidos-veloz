variable "kubeconfig_path" {
  type        = string
  description = "Caminho do kubeconfig do cluster existente"
  default     = "../.local/kubeconfig"
}

variable "kube_context" {
  type        = string
  description = "Contexto do cluster existente a ser confirmado antes do apply"
  default     = "kind-veloz-local"
}
