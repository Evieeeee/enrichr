#!/bin/bash
# deploy.sh — Deploy Enrichr to Google Cloud Run
# Usage: ./deploy.sh [your-gcp-project-id]
set -e

PROJECT_ID=${1:-"your-gcp-project-id"}
SERVICE_NAME="enrichr"
REGION="us-central1"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "🚀 Deploying Enrichr to Cloud Run"
echo "   Project: $PROJECT_ID"
echo "   Region:  $REGION"
echo ""

# Check gcloud is installed
if ! command -v gcloud &> /dev/null; then
  echo "❌ gcloud CLI not found. Install from https://cloud.google.com/sdk"
  exit 1
fi

# Set project
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo "📡 Enabling required APIs..."
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  containerregistry.googleapis.com \
  secretmanager.googleapis.com

# Build and push container image
echo "🏗  Building container image..."
gcloud builds submit --tag "$IMAGE" .

# Check if ANTHROPIC_API_KEY is set as a secret
if ! gcloud secrets describe anthropic-api-key --project="$PROJECT_ID" &>/dev/null; then
  echo ""
  echo "🔑 Creating Secret Manager secret for ANTHROPIC_API_KEY..."
  echo "   Enter your Anthropic API key when prompted:"
  read -s -p "   ANTHROPIC_API_KEY: " API_KEY
  echo ""
  echo -n "$API_KEY" | gcloud secrets create anthropic-api-key \
    --replication-policy="automatic" \
    --data-file=-
  echo "   ✅ Secret created."
else
  echo "🔑 Using existing anthropic-api-key secret."
fi

# Get project number for service account
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

# Grant secret access
gcloud secrets add-iam-policy-binding anthropic-api-key \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet

# Deploy to Cloud Run
echo ""
echo "☁️  Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 2 \
  --timeout 3600 \
  --concurrency 10 \
  --min-instances 0 \
  --max-instances 5 \
  --set-secrets "ANTHROPIC_API_KEY=anthropic-api-key:latest"

echo ""
echo "✅ Deployment complete!"
gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --format="value(status.url)" | xargs -I{} echo "🌐 App URL: {}"
