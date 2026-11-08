# Require an explicit immutable base from image-lock.json (see `just build`).
ARG BASE_IMAGE
# Allow build scripts to be referenced without being copied into the final image
FROM scratch AS ctx
COPY build_files /
COPY system_files /system_files
COPY installer/build-metadata.py /write-build-metadata.py

# Base Image
# Steam Gaming Mode edition for AMD/Intel systems.
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
ARG T740_BUILD_ID
ARG T740_REVISION
ARG T740_CREATED
ARG SOURCE_DATE_EPOCH
LABEL org.opencontainers.image.version=${T740_BUILD_ID} \
      org.opencontainers.image.revision=${T740_REVISION} \
      org.opencontainers.image.created=${T740_CREATED} \
      org.opencontainers.image.base.name=${BASE_IMAGE}
## Other possible base images include:
# FROM ghcr.io/ublue-os/bazzite:testing
# FROM ghcr.io/ublue-os/aurora:stable
# FROM ghcr.io/ublue-os/bluefin-nvidia-open:stable
# 
# ... and so on, here are more base images
# Universal Blue Images: https://github.com/orgs/ublue-os/packages
# Fedora base image: quay.io/fedora/fedora-bootc:44
# CentOS base images: quay.io/centos-bootc/centos-bootc:stream10

### [IM]MUTABLE /opt
## Some bootable images, like Fedora, have /opt symlinked to /var/opt, in order to
## make it mutable/writable for users. However, some packages write files to this directory,
## thus its contents might be wiped out when bootc deploys an image, making it troublesome for
## some packages. Eg, google-chrome, docker-desktop.
##
## Uncomment the following line if one desires to make /opt immutable and be able to be used
## by the package manager.

# RUN rm /opt && mkdir /opt

### MODIFICATIONS
## make modifications desired in your image and install packages by modifying the build.sh script
## the following RUN directive does all the things required to run "build.sh" as recommended.

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    env BASE_IMAGE="$BASE_IMAGE" T740_BUILD_ID="$T740_BUILD_ID" \
    T740_REVISION="$T740_REVISION" T740_CREATED="$T740_CREATED" \
    SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" /ctx/build.sh

### LINTING
## Verify final image and contents are correct.
RUN bootc container lint
