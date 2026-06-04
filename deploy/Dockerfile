# Scheduled OCI ZPR visibility refresh runner.
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY oci_zpr_visibility ./oci_zpr_visibility
COPY log_analytics ./log_analytics
RUN pip install --no-cache-dir -e .
# In-cluster auth: mount an OCI config, or use instance/resource principal (--auth).
ENTRYPOINT ["oci-zpr-visibility", "refresh"]
