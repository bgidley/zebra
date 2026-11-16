# Billing guardrails (#279 S2): budgets that email the owner on any spend, and a compartment
# quota that refuses non-free shapes and billable services in the Zebra compartment.
#
# Budgets and quota policies live in the tenancy (root compartment), so creating them needs a
# tenancy administrator. A user without those rights sets create_guardrails = false; the stack
# then skips them and the `guardrails` output says so. Budgets only alert and never stop spend;
# the quota is the hard stop. See specs/oci-guardrails-design.md.

locals {
  budget_targets = var.create_guardrails ? {
    root  = var.tenancy_ocid
    zebra = oci_identity_compartment.zebra.id
  } : {}

  budget_alert_rules = {
    for pair in setproduct(keys(local.budget_targets), keys(local.budget_alerts)) :
    "${pair[0]}-${pair[1]}" => { budget = pair[0], alert = local.budget_alerts[pair[1]] }
  }
}

resource "oci_budget_budget" "guardrail" {
  for_each = local.budget_targets

  compartment_id = var.tenancy_ocid
  display_name   = "${local.name}-${each.key}"
  description    = "Zebra Always Free guardrail: any spend on the ${each.key == "root" ? "tenancy" : "Zebra compartment"} is unexpected"
  amount         = local.budget_amount
  reset_period   = "MONTHLY"
  target_type    = "COMPARTMENT"
  targets        = [each.value]
  freeform_tags  = local.freeform_tags

  lifecycle {
    precondition {
      condition     = var.alert_email != ""
      error_message = "alert_email is required when create_guardrails is true: budget alerts need somewhere to go."
    }
  }
}

resource "oci_budget_alert_rule" "guardrail" {
  for_each = local.budget_alert_rules

  budget_id      = oci_budget_budget.guardrail[each.value.budget].id
  display_name   = "${local.name}-${each.key}"
  type           = each.value.alert.type
  threshold_type = each.value.alert.threshold_type
  threshold      = each.value.alert.threshold
  recipients     = var.alert_email
  message        = "Zebra should cost nothing on the Always Free tier. Check Cost Analysis for what is billing."
  freeform_tags  = local.freeform_tags
}

resource "oci_limits_quota" "guardrail" {
  count = var.create_guardrails ? 1 : 0

  compartment_id = var.tenancy_ocid
  name           = local.quota_name
  description    = "Zebra Always Free guardrail: only the free A1 shape, the free Autonomous Database and 200 GB of block storage in the ${local.name} compartment"
  statements     = local.quota_statements
  freeform_tags  = local.freeform_tags

  lifecycle {
    precondition {
      condition     = var.compartment_ocid == var.tenancy_ocid
      error_message = "The billing guardrails need the Zebra compartment directly under the tenancy root (quota statements name it by path). Choose the root as the parent compartment, or set create_guardrails = false."
    }
  }
}
