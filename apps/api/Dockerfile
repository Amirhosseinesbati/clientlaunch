FROM python:3.12.11-slim
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir -r /app/requirements.lock
COPY apps/__init__.py /app/apps/__init__.py
COPY apps/api /app/apps/api
COPY apps/ai/templates.json /app/apps/ai/templates.json
COPY scripts /app/scripts
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
