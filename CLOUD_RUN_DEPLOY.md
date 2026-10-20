# Deploying Executive Research Studio to Google Cloud Run

This guide explains how to deploy your Streamlit Research Engine to **Google Cloud Run** under your Google Account.

---

## Why Google Cloud Run?
- **Zero local crashes**: Runs in an isolated Linux container on Google Cloud infrastructure.
- **Permanent HTTPS URL**: Access your research app securely from any browser or mobile device (`https://research-engine-xxxx.a.run.app`).
- **Cost**: **$0 / month** under the Google Cloud Free Tier (automatically scales to zero instances when idle; you pay nothing while not using it).

---

## Method A: Deploy via Google Cloud Console (No CLI or Docker Required)

1. **Push your code to GitHub**:
   Ensure your latest code (including `Dockerfile`) is pushed to your GitHub repository:
   ```bash
   git add Dockerfile .dockerignore
   git commit -m "feat(deploy): add Cloud Run Dockerfile and configuration"
   git push origin <your-branch>
   ```

2. **Open Cloud Run in your browser**:
   Navigate to: [console.cloud.google.com/run](https://console.cloud.google.com/run) using your Google account.

3. **Click "Create Service"**:
   - Choose: **"Continuously deploy from a repository"**.
   - Click **"Set up with Cloud Build"**.
   - Select your repository provider (**GitHub**) and select this repo.
   - Branch: select your branch (e.g. `main` or `v2-phase-5`).
   - Build Type: **Dockerfile** (path: `/Dockerfile`).

4. **Service Configuration**:
   - **Service name**: `executive-research-engine`
   - **Region**: Choose a region close to you (e.g. `us-central1`, `asia-south1`, etc.).
   - **Authentication**: Select **"Allow unauthenticated invocations"** (to access via public browser link) or require Google login.
   - **Container, Networking, Security**:
     - Memory: `1 GiB` or `2 GiB`
     - CPU: `1`
     - **Environment variables**:
       - `GEMINI_API_KEY`: Enter your Google AI Studio Gemini API key.
       - `GEMINI_MODEL`: `gemini-3.8-flash`

5. **Click "Create"**:
   Google Cloud will automatically build your container using Cloud Build and deploy it. Within 2–3 minutes, you'll be given your live HTTPS URL!

---

## Method B: Deploy via Google Cloud Shell (Fast Terminal in Browser)

If you prefer deploying via terminal without installing anything on your Mac:

1. Open [Google Cloud Shell](https://shell.cloud.google.com/).
2. Clone your repository:
   ```bash
   git clone <your-github-repo-url>
   cd research-agent-ml-enterprise
   ```
3. Deploy directly using the Google Cloud CLI (pre-installed in Cloud Shell):
   ```bash
   gcloud run deploy executive-research-engine \
     --source . \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars GEMINI_API_KEY="<your-gemini-api-key>",GEMINI_MODEL="gemini-3.8-flash"
   ```
4. Cloud Build will build the container and output your live URL directly in the terminal!

---

## Keep runs across deploys (Cloud Storage volume)

A Cloud Run container's disk is wiped on every new revision, so finished runs saved under
`outputs/runs` disappear after each deploy. Point the app at a Cloud Storage bucket instead:

1. **Create a bucket** (once): Cloud Storage → Buckets → Create, e.g. `ai-guruji-runs`, same region as
   the service (`asia-south1`), standard storage, uniform access.
2. **Let the service write to it:** in the bucket's Permissions, grant the Cloud Run service account
   the role **Storage Object User**.
3. **Mount it:** Cloud Run → your service → **Edit & deploy new revision** →
   - **Volumes** → Add volume → type **Cloud Storage bucket** → pick the bucket, name it `runs`.
   - **Container → Volume mounts** → mount `runs` at `/mnt/runs`.
4. **Tell the app:** Container → Variables → add `RESEARCH_RUNS_DIR` = `/mnt/runs`.
5. Deploy. New runs are now saved to the bucket and listed under Previous Research Runs after any redeploy.

Runs saved before this change were on the old container disk and cannot be recovered.

## Confidentiality denylist (gate G5)

G5 fails until the app can read a denylist. Store it as a secret:

1. Secret Manager → Create secret `ai-guruji-denylist` with one name per line (an empty file is fine).
2. Grant the service account **Secret Manager Secret Accessor** on it.
3. Cloud Run → Edit & deploy new revision → **Volumes** → Add volume → type **Secret** → that secret,
   mounted at `/secrets` with file name `denylist.txt`.
4. Container → Variables → add `RESEARCH_DENYLIST` = `/secrets/denylist.txt`.
