FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY inference/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt
COPY inference /srv/inference
COPY model /srv/model
CMD ["uvicorn", "inference.app:app", "--host", "0.0.0.0", "--port", "8000"]
