#!/bin/bash
# Build the base Docker image with all heavy dependencies
# Run this once at the start of your hackathon, or when dependencies change

echo -e "\033[0;36mBuilding base image with all dependencies...\033[0m"
echo -e "\033[0;33mThis will take ~45 minutes (one-time cost)\033[0m"
echo ""

start_time=$(date +%s)

docker build -f Dockerfile.base -t mammothbox-base:latest .

if [ $? -eq 0 ]; then
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    minutes=$((duration / 60))
    seconds=$((duration % 60))
    
    echo ""
    echo -e "\033[0;32m✓ Base image built successfully in ${minutes}m ${seconds}s\033[0m"
    echo ""
    echo -e "\033[0;36mNext steps:\033[0m"
    echo -e "  1. Build app: docker-compose build"
    echo -e "  2. Start system: docker-compose up -d"
    echo ""
    echo -e "\033[0;32mFuture code changes will build in ~5 seconds!\033[0m"
else
    echo ""
    echo -e "\033[0;31m✗ Build failed\033[0m"
    exit 1
fi
