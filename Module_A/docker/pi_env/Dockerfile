# Replica of the TECHNIC 6S Orange Pi software (Ubuntu 20.04 arm64, Python 3.8, apt OpenCV 4.2, ROS-less).
# Used to test that the drone code runs on the drone's Python and to download drone-compatible wheels.
FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-numpy \
    python3-opencv python3-yaml && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --no-cache-dir --upgrade "pip<25"
WORKDIR /work
