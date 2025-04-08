#!/bin/bash
# Script to build the lean-docker-mcp Docker image

set -e  # Exit on error

# Default values
DEFAULT_TAG="latest"
DEFAULT_IMAGE_NAME="lean-docker-mcp"

# Parse command-line arguments
image_name=$DEFAULT_IMAGE_NAME
tag=$DEFAULT_TAG

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -t|--tag) tag="$2"; shift ;;
        -n|--name) image_name="$2"; shift ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  -t, --tag TAG    Specify the Docker image tag (default: $DEFAULT_TAG)"
            echo "  -n, --name NAME  Specify the Docker image name (default: $DEFAULT_IMAGE_NAME)"
            echo "  -h, --help       Display this help message"
            exit 0
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

echo "Building Docker image: $image_name:$tag"

# Check if Dockerfile exists
dockerfile_path="src/lean_docker_mcp/Dockerfile"
if [ ! -f "$dockerfile_path" ]; then
    echo "Error: Dockerfile not found at $dockerfile_path"
    exit 1
fi

# Build the Docker image
docker build -t "$image_name:$tag" -f "$dockerfile_path" .

echo "Image $image_name:$tag built successfully!"
echo
echo "You can run a test container with:"
echo "docker run --rm -it $image_name:$tag"
echo
echo "To change the default configuration, update src/lean_docker_mcp/default_config.yaml"
echo "and set docker.image to $image_name:$tag"