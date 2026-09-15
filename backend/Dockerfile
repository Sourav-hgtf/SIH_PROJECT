FROM python:3.14.3-slim
WORKDIR /app
COPY requirements.txt .
# requirements.txt includes the pinned en_core_web_sm wheel, so a production
# image cannot be built with spaCy installed but the PII NER model omitted.
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY tests ./tests
ENV DATABASE_URL=sqlite:////data/sif_sentinel.db
RUN mkdir -p /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
