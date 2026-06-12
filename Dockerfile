# ai-font-proofer engine: Python font tooling + headless Chromium for PDF rendering.
# Built once via `docker compose build`; every command runs through `docker compose run`.

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Keep browsers in a fixed path inside the image (not under root's home)
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    # Point pip and the Playwright downloader at the system CA bundle so the
    # optional extra-ca.crt (added below) is honored during the build.
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

# DejaVu supplies fallback glyphs for proof labels/captions so UI text never
# renders as tofu when the user's font lacks those characters.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Optional: some antivirus and corporate-network tools inspect HTTPS traffic,
# which breaks downloads inside the container. If that happens, the fix is to
# save that tool's certificate as extra-ca.crt next to this Dockerfile (the
# README's troubleshooting section explains how). The trailing * lets this
# COPY succeed whether or not the file exists.
COPY requirements.txt extra-ca.crt* /tmp/
RUN if [ -f /tmp/extra-ca.crt ]; then \
        cp /tmp/extra-ca.crt /usr/local/share/ca-certificates/extra-ca.crt \
        && update-ca-certificates; \
    fi

RUN pip install -r /tmp/requirements.txt

# Chromium + its system libraries (--with-deps runs apt-get for us)
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

CMD ["python", "scripts/check_setup.py"]
