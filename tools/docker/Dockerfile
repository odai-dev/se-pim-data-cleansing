FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-utils \
    ca-certificates \
    wget \
    curl \
    xz-utils \
    git \
    build-essential \
    g++ \
    make \
    scons \
    m4 \
    swig \
    python \
    python-dev \
    python-pip \
    python-six \
    libssl-dev \
    zlib1g-dev \
    libprotobuf-dev \
    protobuf-compiler \
    libprotoc-dev \
    libgoogle-perftools-dev \
    libboost-all-dev \
    libhdf5-serial-dev \
    libpng-dev \
    pkg-config \
    bison \
    flex \
    bc \
    libelf-dev \
    libncurses5-dev \
    libncursesw5-dev \
    gcc-aarch64-linux-gnu \
    g++-aarch64-linux-gnu \
    binutils-aarch64-linux-gnu \
    rsync \
    file \
    qemu-utils \
    kpartx \
    e2fsprogs \
    dosfstools \
    parted \
    sudo \
    locales \
    util-linux \
    && rm -rf /var/lib/apt/lists/*

RUN locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

WORKDIR /workspace

CMD ["/bin/bash"]
