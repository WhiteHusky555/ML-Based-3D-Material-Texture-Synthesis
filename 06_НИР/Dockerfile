FROM python:3.13-slim
ARG SERVICE
WORKDIR /app
COPY src/texgen/${SERVICE}/requirements.txt requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY src/ ./
ARG GPU=0
RUN if [ "$GPU" = 1 ]; then python -m pip install --no-cache-dir -r texgen/generation/requirements-gpu.txt; fi
RUN mkdir -p /jobs && chown 65534:65534 /jobs
USER 65534:65534
EXPOSE 8000
