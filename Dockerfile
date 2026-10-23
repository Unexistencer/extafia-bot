# ---- Base ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

COPY requirements.txt /app/requirements.txt

# Build deps for pip wheels, then remove
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential ca-certificates && \
    sed -i 's|^mozilla/emSign_ECC_Root_CA_-_G3.crt$|!mozilla/emSign_ECC_Root_CA_-_G3.crt|' /etc/ca-certificates.conf && \
    update-ca-certificates && \
    python -m pip install --no-cache-dir --upgrade "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" && \
    python -m pip install --no-cache-dir -r /app/requirements.txt && \
    python -m pip check && \
    apt-get purge -y build-essential && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY . /app

RUN python /app/security/verify_ca.py

ENV GOOGLE_CLOUD_PROJECT=discord-bot-20250213

CMD ["python", "main.py"]
