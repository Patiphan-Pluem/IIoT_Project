FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

RUN pip install numpy synchrophasor psycopg2-binary 

WORKDIR /app

COPY ramp.py /app/

CMD ["python3", "ramp.py"] 