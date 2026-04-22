FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

ENV BASE_RATE=30

RUN pip install numpy synchrophasor 

WORKDIR /app

COPY TinyPMUX.py /app/

CMD ["python3", "TinyPMUX.py"]