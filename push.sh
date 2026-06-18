#!/bin/bash

# 1. HARD GUARDRAIL: Double-check that .env is explicitly tracked by .gitignore
if ! grep -q "^\.env$" .gitignore; then
    echo "⚠️  CRITICAL WARNING: '.env' is not explicitly listed in your .gitignore!"
    echo "Appending '.env' to .gitignore immediately to prevent data leaks..."
    echo ".env" >> .gitignore
fi

# Also ensure virtual environments and cache files are ignored
for pattern in ".venv" "__pycache__" ".pytest_cache" ".DS_Store"; do
    if ! grep -q "^$pattern$" .gitignore; then
        echo "$pattern" >> .gitignore
    fi
done

# 2. Force remove any accidental cached .env tracking without deleting the local file
git rm --cached .env 2>/dev/null

# 3. Add all valid files safely (respecting .gitignore rules)
echo "📦 Staging changes safely..."
git add .

# 4. Check if a commit message was passed as an argument, otherwise use a default
COMMIT_MSG=${1:-"feat: complete multi-agent backend engine with native web search fallback"}

# 5. Commit and push safely
echo "💻 Committing: $COMMIT_MSG"
git commit -m "$COMMIT_MSG"

echo "🚀 Pushing to GitHub main branch..."
git push origin main

echo "✅ Safe deployment complete! Your hard work is safely versioned."