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
export AUTHORIZED_INVOKER_GROUP="${AUTHORIZED_INVOKER_GROUP:-your-auditors-group@example.com}"
export GCP_BILLING_ACCOUNT_ID="${GCP_BILLING_ACCOUNT_ID:-000000-000000-000000}"

echo "Reviewing Cloud Run Hardening Specification for ${SERVICE_NAME} in ${GCP_REGION}..."

# ------------------------------------------------------------------------------
# - Uses --update-env-vars to preserve all existing environment variables
#   (never replace/destroy all unset variables with set-env-vars).
# - Enforces stateless demo mode: HOSTED_DEMO=1.
# - Cloud Storage FUSE volume mount is completely removed: FUSE does not support
#   POSIX file locking or SQLite WAL mode (PRAGMA journal_mode=WAL).
#   The hosted copy runs statelessly; real ledger persistence remains strictly local.
# - Requires IAM authentication: --no-allow-unauthenticated.
# - Caps instances to prevent runaway autoscaling and billing spikes: --max-instances=5.
# ------------------------------------------------------------------------------
cat << 'EOF'
[COMMAND 1 - Service Hardening]
gcloud run services update "executive-research-engine" \
  --project="${GCP_PROJECT_ID}" \
  --region="asia-south1" \
  --no-allow-unauthenticated \
  --update-env-vars="HOSTED_DEMO=1" \
  --max-instances=5 \
  --concurrency=20 \
  --cpu=2 \
  --memory=2Gi
EOF

# ------------------------------------------------------------------------------
# 2. Grant IAM Invocation Access to Authorized Group
# - Uses operator-configurable ${AUTHORIZED_INVOKER_GROUP} variable.
# ------------------------------------------------------------------------------
cat << 'EOF'
[COMMAND 2 - IAM Access Binding]
gcloud run services add-iam-policy-binding "executive-research-engine" \
  --project="${GCP_PROJECT_ID}" \
  --region="asia-south1" \
  --member="group:${AUTHORIZED_INVOKER_GROUP}" \
  --role="roles/run.invoker"
EOF

# ------------------------------------------------------------------------------
# 3. Create Budget Alert for Gemini API / Project Spend
# - Notifies when spend crosses 50%, 80%, and 100% of defined budget cap.
# ------------------------------------------------------------------------------
cat << 'EOF'
[COMMAND 3 - Budget Alert Setup]
gcloud billing budgets create \
  --billing-account="${GCP_BILLING_ACCOUNT_ID}" \
  --display-name="executive-research-engine-gemini-budget" \
  --budget-amount=50.00USD \
  --threshold-rule=percent=0.5,basis=current-spend \
  --threshold-rule=percent=0.8,basis=current-spend \
  --threshold-rule=percent=1.0,basis=current-spend \
  --filter-projects="projects/${GCP_PROJECT_ID}"
EOF
