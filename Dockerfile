# syntax=docker/dockerfile:1

FROM ubuntu:latest
LABEL maintainer="Giulio Rossetti <giulio.rossetti@gmail.com>" \
      version="1.0" \
      description="This is a Docker image of YSocial" \
      website="https://ysocialtwin.github.io/"

RUN apt-get update
RUN apt-get install -y python3-full python3-pip pipx git build-essential python3-dev libffi-dev screen curl  #nvidia-utils-550
# Update and install dependencies
#RUN rm -rf /var/lib/apt/lists/* && \
#    apt-get clean && \
#    apt-get update -o Acquire::CompressionTypes::Order::=gz && \
#    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
#    python3-full python3-pip pipx git build-essential python3-dev libffi-dev screen curl && \
#    apt-get purge python3-colorama -y && \
#    rm -rf /var/lib/apt/lists/*


# Add NVIDIA CUDA repository
RUN curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb -o cuda-keyring.deb && \
    dpkg -i cuda-keyring.deb && rm cuda-keyring.deb

# Install NVIDIA utils (adjust version as needed)
RUN apt-get update && apt-get install -y --no-install-recommends nvidia-utils-550


RUN mkdir /app
COPY . /app
WORKDIR /app
RUN curl -fsSL https://ollama.com/install.sh | sh

RUN git submodule update --init --recursive
RUN pip install --break-system-packages --no-cache-dir -r requirements.txt

# enabling python as default in screen sessions
RUN echo 'alias python="python3"' >> ~/.bashrc
RUN ln -s /usr/bin/python3 /usr/bin/python
#RUN ollama serve &
#VOLUME ["/app", "/root/.ollama/models"]

# Expose Flask port
EXPOSE 5000

# Define volumes
VOLUME ["/app", "/root/.ollama/models"]

# Default command (ysocial)
CMD ["python", "/app/y_social.py", "--host", "0.0.0.0", "--port", "5000"]



