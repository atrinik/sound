# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89

FROM ghcr.io/atrinik/linux-build@sha256:1231b39d40161c1199fd3e45e99e3d826dde02dade79729c030cc0ce3710898f

USER root

COPY tools/audio/sdl3-mixer-runtime-probe.c /tmp/sdl3-mixer-runtime-probe.c

ARG FFMPEG_PACKAGE=7:8.0.1-3ubuntu2
ARG OPENMPT_PACKAGE=0.8.4-1
ARG OPUS_TOOLS_PACKAGE=0.2-1build5
ARG FREEPATS_URL=https://deb.debian.org/debian/pool/main/f/freepats/freepats_20060219.orig.tar.gz
ARG FREEPATS_SHA256=70bf8ca084df3903d6c9de43fe20539fc0a553d95cfba4d525da3fe66fda5f10
ARG FREEPATS_UPSTREAM_SHA256=0261ea1057b232183fa472432d5cedb0dca33698a5319328cdf193d4b2193c8a
ARG CC_BY_URL=https://creativecommons.org/licenses/by/3.0/legalcode.txt
ARG CC_BY_SHA256=e6bc9e9c474700b708f568bac9e5a8a9bcb2b1dad53442f5ba449fcb848b8e76
ARG CC_BY_SA_URL=https://creativecommons.org/licenses/by-sa/3.0/legalcode.txt
ARG CC_BY_SA_SHA256=3f941b3b89cf7b8370ceb83cc76d2120d471b58735d8ca60238a751a48d7f72f
ARG CC0_URL=https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt
ARG CC0_SHA256=a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        "ffmpeg=${FFMPEG_PACKAGE}" \
        "openmpt123=${OPENMPT_PACKAGE}" \
        "opus-tools=${OPUS_TOOLS_PACKAGE}" \
    && curl --fail --location --silent --show-error \
        "${FREEPATS_URL}" --output /tmp/freepats-source.tar.gz \
    && echo "${FREEPATS_SHA256}  /tmp/freepats-source.tar.gz" | sha256sum -c - \
    && mkdir -p /tmp/freepats-source \
    && tar -xzf /tmp/freepats-source.tar.gz -C /tmp/freepats-source \
    && cp /tmp/freepats-source/freepats-20060219/upstream/freepats-20060219.tar.bz2 \
        /tmp/freepats.tar.bz2 \
    && echo "${FREEPATS_UPSTREAM_SHA256}  /tmp/freepats.tar.bz2" | sha256sum -c - \
    && tar -xjf /tmp/freepats.tar.bz2 -C /opt \
    && test -s /opt/freepats/freepats.cfg \
    && printf 'dir /opt/freepats\nsource /opt/freepats/freepats.cfg\n' \
        >/opt/atrinik-freepats.cfg \
    && ln -sf /opt/atrinik-freepats.cfg /etc/timidity/fluidr3_gm.cfg \
    && mkdir -p /opt/atrinik-sound-license-texts \
    && curl --fail --location --silent --show-error "${CC_BY_URL}" \
        --output /opt/atrinik-sound-license-texts/CC-BY-3.0.txt \
    && curl --fail --location --silent --show-error "${CC_BY_SA_URL}" \
        --output /opt/atrinik-sound-license-texts/CC-BY-SA-3.0.txt \
    && curl --fail --location --silent --show-error "${CC0_URL}" \
        --output /opt/atrinik-sound-license-texts/CC0-1.0.txt \
    && echo "${CC_BY_SHA256}  /opt/atrinik-sound-license-texts/CC-BY-3.0.txt" \
        | sha256sum -c - \
    && echo "${CC_BY_SA_SHA256}  /opt/atrinik-sound-license-texts/CC-BY-SA-3.0.txt" \
        | sha256sum -c - \
    && echo "${CC0_SHA256}  /opt/atrinik-sound-license-texts/CC0-1.0.txt" \
        | sha256sum -c - \
    && cc -std=c17 -O2 -Wall -Wextra -Werror \
        /tmp/sdl3-mixer-runtime-probe.c \
        -o /usr/local/bin/atrinik-sound-sdl3-mixer-probe \
        $(pkg-config --cflags --libs sdl3-mixer) \
    && rm -rf /tmp/freepats-source /tmp/freepats-source.tar.gz /tmp/freepats.tar.bz2

RUN ffmpeg -version | grep -F 'ffmpeg version 8.0.1' \
    && timidity --version | grep -F 'TiMidity++ version 2.14.0' \
    && openmpt123 --version | grep -F 'openmpt123 v0.8.4' \
    && opusenc --version | grep -F 'opusenc opus-tools 0.2' \
    && test "$(dpkg-query -W -f='${Version}' opus-tools)" = '0.2-1build5' \
    && atrinik-sdl3-mixer-probe /usr/local/share/atrinik/audio/opus-probe.opus \
    && atrinik-sound-sdl3-mixer-probe --version \
        | grep -F 'atrinik-sound-sdl3-mixer-probe 2' \
    && atrinik-sound-sdl3-mixer-probe \
        /usr/local/share/atrinik/audio/opus-probe.opus 12000 none

WORKDIR /workspaces/sound
