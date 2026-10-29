FROM python:3.12-slim

ARG TARGETARCH=amd64
# rmapi (ddvk fork): talks to rmfakecloud. Pin a release tag with --build-arg RMAPI_VERSION=v…
ARG RMAPI_VERSION=latest

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl unzip pandoc fonts-dejavu \
      libcairo2 libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
 && curl -fsSL https://rclone.org/install.sh | bash \
 && if [ "$RMAPI_VERSION" = latest ]; then base=https://github.com/ddvk/rmapi/releases/latest/download; \
    else base=https://github.com/ddvk/rmapi/releases/download/$RMAPI_VERSION; fi \
 && curl -fsSL "$base/rmapi-linux-$TARGETARCH.tar.gz" | tar -xz -C /usr/local/bin rmapi \
 && apt-get purge -y unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY inkd ./inkd
RUN pip install --no-cache-dir .

ENV INKD_CONFIG=/config/inkd.toml \
    RMAPI_CONFIG=/config/rmapi/rmapi.conf \
    RCLONE_CONFIG=/config/rclone/rclone.conf

VOLUME ["/config", "/data", "/vault"]
ENTRYPOINT ["inkd"]
CMD ["watch"]
