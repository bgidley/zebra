# Wrapper around the OKE migration scripts. Run from deploy/oke.
# Override the image tag with: make deploy TAG=<sha>
SHELL := /usr/bin/env bash
S := scripts
TAG ?= $(shell git rev-parse --short HEAD)

.PHONY: tooling auth infra kubeconfig secrets build deploy smoke all help

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

tooling:   ## Install oci, kubectl, terraform, kustomize, buildah
	bash $(S)/00-bootstrap-tooling.sh
auth:      ## Configure & verify OCI API auth
	bash $(S)/01-oci-auth.sh
infra:     ## terraform apply (VCN, OKE, OCIR, IAM)
	bash $(S)/10-apply-infra.sh
kubeconfig: ## Write kubeconfig + show nodes
	bash $(S)/20-kubeconfig.sh
secrets:   ## Create namespaces + k8s Secrets from secrets/*.env
	bash $(S)/30-create-secrets.sh
build:     ## Build + push images to OCIR (BUILD_CLAUDE=1 for the claude image)
	bash $(S)/25-build-push.sh $(TAG)
deploy:    ## Deploy/promote prod + claude-code at TAG
	bash $(S)/40-deploy.sh $(TAG)
smoke:     ## Ephemeral smoke run against TAG (needs SMOKE_PASSWORD)
	bash $(S)/50-smoke.sh $(TAG)

all: tooling auth infra kubeconfig secrets ## First-time bring-up of infra
