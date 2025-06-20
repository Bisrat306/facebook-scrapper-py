#!/bin/bash
set -e

echo "Starting build process..."

# Upgrade pip to latest version
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies with specific flags to avoid compilation issues
echo "Installing dependencies..."
pip install --no-cache-dir --prefer-binary --only-binary=all -r requirements.txt

# Install Playwright browsers
echo "Installing Playwright browsers..."
playwright install chromium

echo "Build completed successfully!" 