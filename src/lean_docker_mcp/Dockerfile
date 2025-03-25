FROM ubuntu:22.04

# Set environment variables to avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake \
    g++ \
    git \
    libgmp-dev \
    libffi-dev \
    python3 \
    python3-pip \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 leanuser

# Create working directory and switch to leanuser
WORKDIR /home/leanuser
USER leanuser

# Install elan (Lean version manager) for the user
RUN curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y
ENV PATH="/home/leanuser/.elan/bin:${PATH}"

# Get the latest stable Lean4 version and install it
RUN elan default stable
RUN elan self update

# Verify Lean was installed correctly
RUN lean --version

# Create project directory
RUN mkdir -p /home/leanuser/project
WORKDIR /home/leanuser/project

# Create a simple Lean file
RUN echo 'def main : IO Unit := IO.println "Hello, Lean4!"' > Main.lean

# Default command (will be overridden when running the container)
CMD ["lean", "-r", "Main.lean"] 