FROM apache/airflow:2.10.5-python3.12
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /models /pipeline-work && chown -R airflow:root /models /pipeline-work
USER airflow
RUN pip install --no-cache-dir 'lightgbm>=4.0' 'pandas>=2.0' 'numpy>=1.24' 'scikit-learn>=1.3'
COPY --chown=airflow:root airflow/dags /opt/airflow/dags
COPY --chown=airflow:root ml_pipeline /opt/airflow/ml_pipeline
COPY --chown=airflow:root training /opt/airflow/training
ENV PYTHONPATH=/opt/airflow
