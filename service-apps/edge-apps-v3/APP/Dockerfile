FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

RUN pip install numpy ray psycopg2-binary 

WORKDIR /app

COPY ems-blackbox.py /app/

CMD ["python3", "ems-blackbox.py"]