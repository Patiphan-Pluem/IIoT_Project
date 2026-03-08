FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

RUN pip install numpy synchrophasor psycopg2-binary 

WORKDIR /app

COPY onoff.py /app/

CMD ["python3", "onoff.py"] 