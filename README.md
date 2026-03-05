# Enrichr — AI Contact Enrichment Tool

Enrich a contact list (email, first name, last name, company name) with any custom fields using Claude's deep research capabilities. Runs in the background even when you close the browser tab.

## Features

- 📁 Upload CSV or Excel contact lists
- 🔬 Define custom fields with natural-language research instructions
- ⚡ Background enrichment using Claude + web search
- 📊 Live progress tracking (persists across tab closes/reopens)
- ⬇️ Download enriched Excel file when complete
- ☁️ Deployable to Google Cloud Run

---

## Project Structure

```
enrichr/
├── app.py              # Flask backend
├── templates/
│   └── index.html      # Frontend UI
├── requirements.txt
├── Dockerfile
├── deploy.sh           # Cloud Run deployment script
└── run_local.sh        # Local dev script
```

---

## Input File Format

Your CSV or Excel file must contain these columns (case-insensitive):

| Column | Description |
|--------|-------------|
| `email` | Contact's email address |
| `first_name` | First name |
| `last_name` | Last name |
| `company_name` | Company name |

---

## Running Locally

```bash
# 1. Set your Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
./run_local.sh
# OR
python app.py

# 4. Open http://localhost:8080
```

---

## Deploying to Google Cloud Run

### Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk) installed and authenticated
- A GCP project with billing enabled

### Deploy

```bash
chmod +x deploy.sh
./deploy.sh YOUR_GCP_PROJECT_ID
```

The script will:
1. Enable required GCP APIs
2. Build and push the Docker image
3. Store your Anthropic API key in Secret Manager
4. Deploy to Cloud Run with appropriate settings

### Manual deployment

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1

# Build image
gcloud builds submit --tag gcr.io/$PROJECT_ID/enrichr .

# Deploy
gcloud run deploy enrichr \
  --image gcr.io/$PROJECT_ID/enrichr \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 2 \
  --timeout 3600 \
  --set-env-vars ANTHROPIC_API_KEY=sk-ant-...
```

---

## Architecture Notes

### Background Processing
Jobs run in background threads. The job state is stored in-memory on the server. The browser stores the `job_id` in `localStorage`, so users can close and reopen the tab and resume tracking their job.

> **Note for production / multi-instance deployments:** Replace the in-memory `jobs` dict with Redis or a database (e.g. Cloud Firestore, Cloud SQL) so job state persists across Cloud Run instances and restarts.

### Cloud Run Configuration
- `--workers 1 --threads 8`: Single process, multi-threaded (required for background threads to work)
- `--timeout 3600`: 1 hour timeout (enrichment can take time for large lists)
- `--min-instances 0`: Scales to zero when idle (cost-efficient)

### Scaling Considerations
For lists > 100 contacts, consider:
- Using Cloud Tasks or Pub/Sub for job queuing
- Storing job state in Firestore
- Using Cloud Run Jobs instead of a web service

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | Your Anthropic API key |
| `PORT` | Auto-set | Port to listen on (Cloud Run sets this) |

---

## Example Enrichment Fields

| Field Name | Description |
|------------|-------------|
| Job Title | Current job title from LinkedIn or company website |
| LinkedIn URL | LinkedIn profile URL for this person |
| Company Size | Approximate number of employees at the company |
| Industry | Industry/sector the company operates in |
| Company HQ | City and country where the company is headquartered |
| Tech Stack | Key technologies the company uses (from job listings or their website) |
| Recent News | Most recent noteworthy news about the company (last 6 months) |
