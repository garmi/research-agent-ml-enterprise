#!/usr/bin/env bash
# ==============================================================================
# CORRECTED PRODUCTION HARDENING SPECIFICATION FOR CLOUD RUN
# SERVICE: executive-research-engine | REGION: asia-south1
# 
# DO NOT RUN AUTOMATICALLY: This script is a reviewed operator specification.
# It details the exact production hardening commands for asia-south1.
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Operator Variables (fill in before manual execution)
# ------------------------------------------------------------------------------
export GCP_PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
export GCP_REGION="asia-south1"
export SERVICE_NAME="executive-research-engine"
# IAM supports both user: and group: prefixes; defaults to current gcloud account
export AUTHORIZED_INVOKER_GROUP="${AUTHORIZED_INVOKER_GROUP:-your-auditors-group@example.com}"
export INVOKER_IDENTITY="${INVOKER_IDENTITY:-user:$(gcloud config get-value account 2>/dev/null || echo 'operator@example.com')}"
export GCP_BILLING_ACCOUNT_ID="${GCP_BILLING_ACCOUNT_ID:-000000-000000-000000}"

echo "Reviewing Cloud Run Hardening Specification for ${SERVICE_NAME} in ${GCP_REGION}..."

# ------------------------------------------------------------------------------
# COMMAND 1: Redeploy from Current Commit (Ordered BEFORE Config Update)
# Ensures the deployed container image contains recent fixes (e.g. A2-6 demo lockdown).
# ------------------------------------------------------------------------------
cat << 'EOF'
[COMMAND 1 - Redeploy from Source]
gcloud run deploy "executive-research-engine" \
  --project="${GCP_PROJECT_ID}" \
  --region="asia-south1" \
  --source .
EOF

# ------------------------------------------------------------------------------
# COMMAND 2: Service Configuration Hardening
# - Uses --update-env-vars to preserve all existing environment variables
#   (never replace/destroy all unset variables with set-env-vars).
# - Enforces stateless demo mode: HOSTED_DEMO=1.
# - Cloud Storage FUSE volume mount is completely removed: FUSE does not support
#   POSIX file locking or SQLite WAL mode (PRAGMA journal_mode=WAL).
#   The hosted copy runs statelessly; real ledger persistence remains strictly local.
# - Requires IAM authentication: --no-allow-unauthenticated.
# - Caps instances to prevent runaway autoscaling and billing spikes: --max-instances=5.
# - Note: Unrequested resource overrides (custom CPU cores, memory limits, concurrency)
#   are omitted to preserve default cost efficiency.
# ------------------------------------------------------------------------------
cat << 'EOF'
[COMMAND 2 - Service Hardening]
gcloud run services update "executive-research-engine" \
  --project="${GCP_PROJECT_ID}" \
  --region="asia-south1" \
  --no-allow-unauthenticated \
  --update-env-vars="HOSTED_DEMO=1" \
  --max-instances=5
EOF

# ------------------------------------------------------------------------------
# COMMAND 3: Grant IAM Invocation Access
# - Supports user: (default: current account) or group: identity via ${INVOKER_IDENTITY}.
# ------------------------------------------------------------------------------
cat << 'EOF'
[COMMAND 3 - IAM Access Binding]
gcloud run services add-iam-policy-binding "executive-research-engine" \
  --project="${GCP_PROJECT_ID}" \
  --region="asia-south1" \
  --member="${INVOKER_IDENTITY}" \
  --role="roles/run.invoker"
EOF

# ------------------------------------------------------------------------------
# COMMAND 4: Create Budget Alert for Gemini API / Project Spend
# - Notifies when spend crosses 50%, 80%, and 100% of defined budget cap.
# - Defines procedure to discover ${BUDGET_ID} via 'gcloud billing budgets list'.
# ------------------------------------------------------------------------------
cat << 'EOF'
[COMMAND 4 - Budget Alert Setup]
gcloud billing budgets create \
  --billing-account="${GCP_BILLING_ACCOUNT_ID}" \
  --display-name="executive-research-engine-gemini-budget" \
  --budget-amount=50.00USD \
  --threshold-rule=percent=0.5,basis=current-spend \
  --threshold-rule=percent=0.8,basis=current-spend \
  --threshold-rule=percent=1.0,basis=current-spend \
  --filter-projects="projects/${GCP_PROJECT_ID}"

# To discover the generated ${BUDGET_ID} for inspection or reversal:
gcloud billing budgets list --billing-account="${GCP_BILLING_ACCOUNT_ID}"
EOF

# ------------------------------------------------------------------------------
# COMMAND 5: Check or Rotate Gemini API Key
# - Inspect currently set environment variables.
# - Rotate GEMINI_API_KEY safely using --update-env-vars.
# ------------------------------------------------------------------------------
cat << 'EOF'
[COMMAND 5 - Check or Rotate Gemini Key]
# Check currently set environment configuration:
gcloud run services describe "executive-research-engine" \
  --project="${GCP_PROJECT_ID}" \
  --region="asia-south1" \
  --format="value(spec.template.spec.containers[0].env)"

# Rotate GEMINI_API_KEY:
gcloud run services update "executive-research-engine" \
  --project="${GCP_PROJECT_ID}" \
  --region="asia-south1" \
  --update-env-vars="GEMINI_API_KEY=${NEW_GEMINI_API_KEY}"
EOF

# ------------------------------------------------------------------------------
# COMMAND 6: Authentication Verification
# - Confirm the service URL requires sign-in.
# - Open URL in a private browser window to confirm sign-in redirect / 403 Forbidden.
# - Test unauthenticated vs authenticated curl responses.
# ------------------------------------------------------------------------------
cat << 'EOF'
[COMMAND 6 - Authentication Verification]
export SERVICE_URL=$(gcloud run services describe "executive-research-engine" \
  --project="${GCP_PROJECT_ID}" \
  --region="asia-south1" \
  --format="value(status.url)")

# 1. Unauthenticated invocation test (expected output: HTTP 403 or 401):
curl -I -s -o /dev/null -w "%{http_code}\n" "${SERVICE_URL}"

# 2. Authenticated invocation test with identity token (expected output: HTTP 200):
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "${SERVICE_URL}"

# 3. Browser verification:
# Open ${SERVICE_URL} in a private window (incognito). Confirm Google Sign-In prompt is required.
EOF
