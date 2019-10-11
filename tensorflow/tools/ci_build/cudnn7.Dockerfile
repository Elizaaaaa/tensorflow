ARG IMAGE_NAME=nvidia/cuda
FROM ${IMAGE_NAME}:10.0-devel-ubuntu16.04
LABEL maintainer "NVIDIA CORPORATION <cudatools@nvidia.com>"

ENV CUDNN_VERSION 7.4.1.5
LABEL com.nvidia.cudnn.version="${CUDNN_VERSION}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcudnn7=$CUDNN_VERSION-1+cuda10.0 \
libcudnn7-dev=$CUDNN_VERSION-1+cuda10.0 \
&& \
    apt-mark hold libcudnn7 && \
    rm -rf /var/lib/apt/lists/*

RUN cp -P /usr/include/cudnn.h /usr/local/cuda-10.0/include
RUN cp -P /usr/lib/x86_64-linux-gnu/libcudnn* /usr/local/cuda-10.0/lib64
