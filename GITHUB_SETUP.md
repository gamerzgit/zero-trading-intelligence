# GitHub Setup Instructions

## Step 1: Create GitHub Repository

1. Go to [GitHub](https://github.com) and sign in
2. Click the **"+"** icon in the top right → **"New repository"**
3. Repository settings:
   - **Name:** `zero-trading-intelligence` (or your preferred name)
   - **Description:** "Probabilistic Market Intelligence Platform for NVIDIA Jetson Orin AGX"
   - **Visibility:** Private (recommended) or Public
   - **DO NOT** initialize with README, .gitignore, or license (we already have these)
4. Click **"Create repository"**

## Step 2: Add Remote and Push

After creating the repository, GitHub will show you commands. Use these:

```bash
cd C:\Users\gamerz\Desktop\zero-trading-intelligence

# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/zero-trading-intelligence.git

# Or if using SSH:
# git remote add origin git@github.com:YOUR_USERNAME/zero-trading-intelligence.git

# Rename default branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

## Step 3: Verify Upload

1. Go to your repository on GitHub
2. Verify all files are present:
   - `README.md`
   - `contracts/` directory
   - `docs/SPEC_LOCK.md`
   - `infra/` directory
   - `.env.example`
   - `Makefile`
   - etc.

## Step 4: Set Repository Description

Add this to your GitHub repository description:

```
Probabilistic Market Intelligence Platform (Decision Support System) for NVIDIA Jetson Orin AGX. Milestone 0: Architecture & Contracts.
```

## Step 5: Add Topics/Tags (Optional)

Add these topics to your repository:
- `trading`
- `jetson`
- `timescaledb`
- `redis`
- `market-intelligence`
- `decision-support-system`
- `python`
- `docker`

## Step 6: Protect Main Branch (Recommended)

1. Go to repository **Settings** → **Branches**
2. Add branch protection rule for `main`:
   - Require pull request reviews
   - Require status checks (if you set up CI/CD later)
   - Include administrators

## Troubleshooting

### Authentication Issues

If you get authentication errors:

**Option 1: Use Personal Access Token**
1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token with `repo` scope
3. Use token as password when pushing

**Option 2: Use SSH**
1. Generate SSH key: `ssh-keygen -t ed25519 -C "your_email@example.com"`
2. Add to GitHub: Settings → SSH and GPG keys
3. Use SSH URL: `git@github.com:USERNAME/REPO.git`

### Push Rejected

If push is rejected:
```bash
# Pull first (if repository was initialized with files)
git pull origin main --allow-unrelated-histories

# Then push
git push -u origin main
```

## Next Steps After Upload

1. **Add collaborators** (if working with team)
2. **Set up GitHub Actions** (for CI/CD - future)
3. **Create issues** for Milestone 1 tasks
4. **Create project board** for tracking milestones

---

**Ready to push!** Follow Step 2 above.

