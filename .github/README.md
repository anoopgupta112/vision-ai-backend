# GitHub Actions Workflows

This project includes two GitHub Actions workflows for automated CI/CD.

## Workflows

### 1. CI Workflow (`.github/workflows/ci.yml`)

**Triggers:**
- Push to `main` or `develop` branches
- Pull requests to `main` branch

**Jobs:**

**Test Job:**
- Sets up Python 3.11
- Installs dependencies
- Runs Flask application test
- Tests health endpoint

**Docker Job:**
- Builds Docker image
- Validates Dockerfile
- Uses build caching for faster builds

### 2. Deploy Workflow (`.github/workflows/deploy.yml`)

**Triggers:**
- Push to `main` branch

**Job:**
- SSH into production server
- Pull latest code from `main`
- Rebuild and restart Docker containers

## Required GitHub Secrets

To enable the deployment workflow, add these secrets in GitHub:

**Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Description | Example |
|------------|-------------|---------|
| `SSH_HOST` | Server IP address or hostname | `123.456.789.0` or `server.example.com` |
| `SSH_USER` | SSH username | `root` or `ubuntu` |
| `SSH_KEY` | Private SSH key | Your private key content |

### Setting up SSH_KEY

1. **Generate SSH key pair** (on your local machine):
   ```bash
   ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_deploy
   ```

2. **Copy public key to server**:
   ```bash
   ssh-copy-id -i ~/.ssh/github_deploy.pub user@server
   ```

3. **Add private key to GitHub**:
   - Copy private key content:
     ```bash
     cat ~/.ssh/github_deploy
     ```
   - Go to GitHub repository → Settings → Secrets → New secret
   - Name: `SSH_KEY`
   - Value: Paste the entire private key content

## Server Setup

On your production server:

1. **Clone repository**:
   ```bash
   mkdir -p /root/deployed_repos
   cd /root/deployed_repos
   git clone https://github.com/yourusername/main_dashboard.git
   ```

2. **Configure environment**:
   ```bash
   cd main_dashboard
   cp .env.example .env
   nano .env
   ```
   
   Update `.env` with production values:
   ```bash
   FLASK_ENV=production
   SECRET_KEY=your-secure-production-secret-key
   DASHBOARD_URL=https://app.yourdomain.com
   ```

3. **Initial deployment**:
   ```bash
   docker compose up --build -d
   ```

4. **Verify deployment**:
   ```bash
   curl http://localhost:8000/health
   docker compose ps
   docker compose logs -f
   ```

## Deployment Process

Once configured, deployments are automatic:

1. Push code to `main` branch
2. GitHub Actions triggers deploy workflow
3. Workflow connects to server via SSH
4. Pulls latest code
5. Rebuilds and restarts containers
6. Landing page is updated

## Monitoring Deployments

- **GitHub UI**: Actions tab shows workflow status
- **Server logs**: 
  ```bash
  ssh user@server
  cd /root/deployed_repos/main_dashboard
  docker compose logs -f
  ```

## Troubleshooting

### SSH Connection Failed
- Verify `SSH_HOST`, `SSH_USER`, and `SSH_KEY` secrets are correct
- Ensure server allows SSH connections on port 22
- Check firewall rules

### Docker Build Failed
- Check server has enough disk space: `df -h`
- Verify Docker is installed and running: `docker --version`
- Review logs: `docker compose logs`

### Application Not Starting
- Check environment variables in `.env`
- Verify port 8000 is not already in use: `lsof -i :8000`
- Review container logs: `docker compose logs web`

## Manual Deployment

If needed, deploy manually:

```bash
ssh user@server
cd /root/deployed_repos/main_dashboard
git pull origin main
docker compose up --build -d
```
