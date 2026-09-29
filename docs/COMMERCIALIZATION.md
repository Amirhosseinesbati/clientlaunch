# Commercialization plan and constraints

## Ideal buyer and offer

The ideal buyer is a small agency with repeatable service packages, a named account owner, and recurring handoff friction between sales and delivery. Offer a **customer-specific installation/configuration project**: map its services to onboarding templates, connect its own Google Drive and Trello accounts, configure an authorized SMTP sender, train operators, and document support and recovery. The agency owns and operates its n8n instance and provider accounts.

The pilot is a starting point for selling setup and customization, not a hosted multi-customer service or a proven production package. n8n’s [Sustainable Use License](https://github.com/n8n-io/n8n/blob/master/LICENSE.md) restricts commercial redistribution/hosted uses; obtain a specific license review before offering embedded or managed n8n functionality. No blanket right to resell n8n is asserted.

## Onboarding and configuration work

1. Discover the customer’s handoff event, service taxonomy, proposal fields, account-owner directory, due-date rules, timezone, domain and approved recipients.
2. Review and version eight initial service templates with the customer. Set folder naming/root, Trello workspace/board structure, client-visible items and welcome copy. Keep scope additions subject to review.
3. Provision a customer-owned n8n/PostgreSQL installation, TLS and backups; configure unique secrets, OAuth/API credentials and sender identity outside source control.
4. Import the workflow pack inactive, map credential placeholders and child workflow IDs, then test with local simulators and a permitted customer test account. Do not activate connected schedules from an import side effect.
5. Run the signed handoff, exact approval, portal isolation, file upload, reminder, duplicate and partial-failure recovery walkthrough; sign off limits and escalation ownership.

## Reusable modules

The signed QuoteFlow-compatible handoff contract, versioned service-template mapping, plan review/hash approval, idempotent action ledger, client checklist portal, reminder eligibility and handoff summary can be adapted to another agency. Provider-specific OAuth setup, task/folder naming, customer role mapping and copy are implementation services, not universal defaults.

## Cost worksheet

Use current customer-specific provider prices rather than hard-coded estimates. For month `m`:

```text
model_cost_m = input_tokens_m / 1_000_000 × configured_input_rate
             + output_tokens_m / 1_000_000 × configured_output_rate
storage_cost_m = database_GB_m × configured_database_rate
               + asset_GB_m × configured_asset_rate
operations_cost_m = n8n_host_hours_m × configured_host_rate
                  + backup_GB_m × configured_backup_rate
                  + SMTP_messages_m × configured_mail_rate
total_estimate_m = model_cost_m + storage_cost_m + operations_cost_m
```

Track unknown usage separately; a missing model price or provider rate must not display as zero. Include backup storage, support/maintenance and any licensed n8n entitlement in the customer quote. The demo fixture uses no paid model calls or real mail.

## Supported target integrations and limits

The intended connected targets are Google Drive folders, Trello boards and authorized SMTP. Their adapter contracts and credential mapping need live smoke tests before sale. The local simulator is for demonstrations and contract tests, not evidence of real provider behavior. v1 does not include e-signature, payment triggers, other task systems, calendar booking, public self-service tenancy, automatic provider rollback or enterprise n8n features. Model-extracted tasks require human review; synthetic accuracy does not establish customer-specific accuracy.

## Redistribution review

Before delivering binaries/assets or publishing a repository, inventory exact package, font, icon, image and fixture licenses; preserve notices; remove credential names/IDs and private URLs from workflow exports; inspect all customer copy/data rights; and consult the actual n8n commercial terms for the planned delivery model. n8n’s [workflow export guidance](https://docs.n8n.io/build/manage-workflows/export-and-import) explicitly warns that exports can include credential names and IDs.
