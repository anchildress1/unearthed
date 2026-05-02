#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ──────────────────────────────────────────────────────────────
SERVICE_NAME="unearthed"
REGION="us-east1"
PORT="8080"
DOMAIN="unearthed.anchildress1.dev"
SECRET_NAME="unearthed-snowflake-key"
SA_NAME="unearthed-run"

# R2 + Anthropic secret names in Secret Manager (UNEARTHED_ prefix chosen by operator).
SECRET_R2_KEY_ID="UNEARTHED_R2_ACCESS_KEY_ID"
SECRET_R2_SECRET="UNEARTHED_R2_SECRET_ACCESS_KEY"
SECRET_ANTHROPIC="UNEARTHED_ANTHROPIC_API_KEY"

# Snowflake identity is overridable via env so a teammate, judge, or
# forked deploy can target a different account/user without touching
# this script. Defaults match the submission deployment.
SNOWFLAKE_ACCOUNT="${SNOWFLAKE_ACCOUNT:-OJIDCKD-MDC60154}"
SNOWFLAKE_USER="${SNOWFLAKE_USER:-anchildress1}"

# Prewarm runs a Cortex Complete against every fallback subregion on
# boot so the first real request hits a warm cache. Off by default — it
# costs Cortex credits on every cold start, which is the wrong default
# for a forked/test deploy. Set PREWARM_PROSE=true in the invoking env
# to opt in for the submission deployment.
PREWARM_PROSE="${PREWARM_PROSE:-false}"

# Banner rule — used for boxed headers and the closing summary.
readonly RULE="═══════════════════════════════════════════════════════════"

# ─── Preflight ──────────────────────────────────────────────────────────────────
command -v gcloud &>/dev/null || { echo "ERROR: gcloud CLI not found" >&2; exit 1; }

# Read VITE_GOOGLE_MAPS_KEY from frontend/.env when not already exported
if [[ -z "${VITE_GOOGLE_MAPS_KEY:-}" ]] && [[ -f frontend/.env ]]; then
  VITE_GOOGLE_MAPS_KEY=$(grep 'VITE_GOOGLE_MAPS_KEY=' frontend/.env | cut -d= -f2)
fi
[[ -n "${VITE_GOOGLE_MAPS_KEY:-}" ]] || {
  echo "ERROR: VITE_GOOGLE_MAPS_KEY not set and frontend/.env not found" >&2; exit 1;
}

# Read R2 non-secret config from .env when not already exported.
# R2_ENDPOINT and DATA_BASE_URL are not secrets — they identify the bucket,
# not the credentials. The actual key pair is pulled from Secret Manager.
if [[ -f .env ]]; then
  [[ -z "${R2_ENDPOINT:-}" ]]    && R2_ENDPOINT=$(grep    '^R2_ENDPOINT='    .env | cut -d= -f2-)
  [[ -z "${DATA_BASE_URL:-}" ]]  && DATA_BASE_URL=$(grep  '^DATA_BASE_URL='  .env | cut -d= -f2-)
fi
[[ -n "${R2_ENDPOINT:-}" ]] || {
  echo "ERROR: R2_ENDPOINT not set. Add it to .env or export it." >&2; exit 1;
}
DATA_BASE_URL="${DATA_BASE_URL:-s3://unearthed-data}"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
[[ -n "$PROJECT_ID" ]] || { echo "ERROR: No GCP project. Run: gcloud config set project <ID>" >&2; exit 1; }

KEY_FILE="${KEY_FILE:-snowflake_prod_key.p8}"
[[ -f "$KEY_FILE" ]] || { echo "ERROR: Key file not found: ${KEY_FILE}" >&2; exit 1; }

echo "${RULE}"
echo "  ${SERVICE_NAME} → ${PROJECT_ID} / ${REGION}"
echo "  Domain: ${DOMAIN}"
echo "${RULE}"

# ─── Enable required APIs ───────────────────────────────────────────────────────
echo "» Enabling GCP APIs..."
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  --quiet

# ─── Service account (least-privilege) ──────────────────────────────────────────
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "» Service account: ${SA_EMAIL}"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" &>/dev/null; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Unearthed Cloud Run" \
    --description="Least-privilege SA for unearthed Cloud Run service" \
    --quiet
  echo "  Created"
else
  echo "  Exists"
fi

# ─── Secret Manager: Snowflake private key ──────────────────────────────────────
echo "» Storing Snowflake key in Secret Manager..."
if ! gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud secrets create "${SECRET_NAME}" \
    --replication-policy="automatic" \
    --project="${PROJECT_ID}" \
    --quiet
  echo "  Created secret: ${SECRET_NAME}"
fi

gcloud secrets versions add "${SECRET_NAME}" \
  --data-file="${KEY_FILE}" \
  --project="${PROJECT_ID}" \
  --quiet
echo "  Uploaded new version"

# Per-secret IAM bindings — SA can only read these specific secrets, not all of them.
for secret in "${SECRET_NAME}" "${SECRET_R2_KEY_ID}" "${SECRET_R2_SECRET}" "${SECRET_ANTHROPIC}"; do
  echo "  Binding secretAccessor to ${secret}..."
  gcloud secrets add-iam-policy-binding "${secret}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="${PROJECT_ID}" \
    --quiet
done

# ─── Artifact Registry ──────────────────────────────────────────────────────────
REPO_NAME="${SERVICE_NAME}"
REPO_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"

echo "» Artifact Registry: ${REPO_NAME}"
if ! gcloud artifacts repositories describe "${REPO_NAME}" \
  --location="${REGION}" --format="value(name)" &>/dev/null; then
  gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Docker images for ${SERVICE_NAME}" \
    --quiet
  echo "  Created"
else
  echo "  Exists"
fi

# ─── Build (cloudbuild.yaml passes --build-arg for VITE_GOOGLE_MAPS_KEY) ─────
IMAGE="${REPO_PATH}/${SERVICE_NAME}:latest"
echo "» Building image: ${IMAGE}"

gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions="_IMAGE=${IMAGE},_VITE_GOOGLE_MAPS_KEY=${VITE_GOOGLE_MAPS_KEY}"

# ─── Deploy ──────────────────────────────────────────────────────────────────────
echo "» Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --port "${PORT}" \
  --service-account "${SA_EMAIL}" \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 2 \
  --min-instances 0 \
  --concurrency 80 \
  --timeout 60 \
  --cpu-boost \
  --set-secrets="\
/secrets/snowflake_key.p8=${SECRET_NAME}:latest,\
R2_ACCESS_KEY_ID=${SECRET_R2_KEY_ID}:latest,\
R2_SECRET_ACCESS_KEY=${SECRET_R2_SECRET}:latest,\
ANTHROPIC_API_KEY=${SECRET_ANTHROPIC}:latest" \
  --set-env-vars="\
SNOWFLAKE_ACCOUNT=${SNOWFLAKE_ACCOUNT},\
SNOWFLAKE_USER=${SNOWFLAKE_USER},\
SNOWFLAKE_PRIVATE_KEY_PATH=/secrets/snowflake_key.p8,\
SNOWFLAKE_ROLE=UNEARTHED_APP_ROLE,\
SNOWFLAKE_WAREHOUSE=UNEARTHED_APP_WH,\
SNOWFLAKE_DATABASE=UNEARTHED_DB,\
DATA_BASE_URL=${DATA_BASE_URL},\
R2_ENDPOINT=${R2_ENDPOINT},\
CORS_ORIGINS=https://${DOMAIN},\
PREWARM_PROSE=${PREWARM_PROSE}" \
  --quiet

# ─── Smoke test ──────────────────────────────────────────────────────────────────
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --format="value(status.url)")

echo "» Smoke test: ${SERVICE_URL}/health"
RETRIES=4
for i in $(seq 1 $RETRIES); do
  if curl -sf --max-time 10 "${SERVICE_URL}/health" >/dev/null 2>&1; then
    echo "  PASS — service is healthy"
    break
  fi
  if [[ "$i" -eq "$RETRIES" ]]; then
    echo "  WARN — health check did not pass after ${RETRIES} attempts"
    echo "  The container may still be starting. Check logs:"
    echo "    gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --limit=20"
  else
    echo "  Attempt ${i}/${RETRIES} failed, retrying in 5s..."
    sleep 5
  fi
done

echo ""
echo "${RULE}"
echo "  Cloud Run : ${SERVICE_URL}"
echo "  Domain    : https://${DOMAIN}"
echo "${RULE}"
