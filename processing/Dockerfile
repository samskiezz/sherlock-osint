# syntax=docker/dockerfile:1
FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_THREAD_LIMIT=2 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if [ -f /run/proxy-ca.pem ]; then SSL_CERT_FILE=/run/proxy-ca.pem apt-get -o Acquire::https::CaInfo=/run/proxy-ca.pem update; else apt-get update; fi \
    && apt-get install -y --no-install-recommends tesseract-ocr ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if [ -f /run/proxy-ca.pem ]; then PIP_CERT=/run/proxy-ca.pem pip install --no-cache-dir -r /app/requirements.txt; else pip install --no-cache-dir -r /app/requirements.txt; fi
COPY --chmod=0444 worker.py image_analysis.py document_analysis.py visual_features.py /app/
RUN mkdir -p /input /output && python -m pip freeze > /app/dependency-manifest.txt && dpkg-query -W > /app/system-packages.txt
USER 65532:65532
ENTRYPOINT ["python","-I","/app/worker.py"]
