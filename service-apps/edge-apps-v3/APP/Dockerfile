FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN pip install numpy ray psycopg2-binary 

WORKDIR /app

COPY ems-blackbox.py /app/

CMD ["python3", "ems-blackbox.py"]