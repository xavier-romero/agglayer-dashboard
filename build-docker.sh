#!/bin/bash
# Build script for AggLayer Dashboard Docker image

set -e

IMAGE_NAME="agglayer-dashboard"
TAG="${1:-latest}"
FULL_IMAGE_NAME="${IMAGE_NAME}:${TAG}"

echo "🐳 Building Docker image: ${FULL_IMAGE_NAME}"

# Build the image
docker build -t "${FULL_IMAGE_NAME}" .

echo "✅ Docker image built successfully: ${FULL_IMAGE_NAME}"
echo ""
echo "🚀 To run the image:"
echo "   docker run -p 8000:8000 -v \$(pwd)/config.json:/app/config.json:ro ${FULL_IMAGE_NAME}"
echo ""
echo "🔍 To inspect the image:"
echo "   docker run -it --entrypoint /bin/bash ${FULL_IMAGE_NAME}"
echo ""
echo "📦 Image details:"
docker images "${FULL_IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
