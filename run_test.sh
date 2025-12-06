#!/bin/bash
# run_test.sh - Test script to build and run Docker container locally

set -e  # Exit on error

# Container and image names
IMAGE_NAME="gamdl-web"
CONTAINER_NAME="gamdl-web-test"

# Local paths for volumes
CONFIG_PATH="${HOME}/Documents/config"
MEDIA_PATH="${HOME}/Documents/media"

# Create directories if they don't exist
mkdir -p "${CONFIG_PATH}"
mkdir -p "${MEDIA_PATH}"

echo "Building Docker image..."
docker build -t ${IMAGE_NAME} .

echo "Stopping and removing existing container if any..."
docker stop ${CONTAINER_NAME} 2>/dev/null || true
docker rm ${CONTAINER_NAME} 2>/dev/null || true

echo "Starting Docker container..."
docker run -d \
  --name ${CONTAINER_NAME} \
  -p 5800:5800 \
  -v "${CONFIG_PATH}:/config" \
  -v "${MEDIA_PATH}:/media" \
  ${IMAGE_NAME}

echo ""
echo "Container started successfully!"
echo "Access the web app at: http://localhost:5800"
echo ""
echo "Useful commands:"
echo "  View logs:    docker logs -f ${CONTAINER_NAME}"
echo "  Stop:         docker stop ${CONTAINER_NAME}"
echo "  Remove:       docker rm ${CONTAINER_NAME}"
echo ""

# Follow logs
docker logs -f ${CONTAINER_NAME}
