FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

RUN pip install numpy synchrophasor 

WORKDIR /app

COPY baseline.py /app/

CMD ["python3", "baseline.py"]