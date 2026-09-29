FROM python:3.12.11-slim
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir -r /app/requirements.lock
COPY apps/__init__.py /app/apps/__init__.py
COPY apps/ai /app/apps/ai
EXPOSE 8001
CMD ["uvicorn", "apps.ai.main:app", "--host", "0.0.0.0", "--port", "8001"]
