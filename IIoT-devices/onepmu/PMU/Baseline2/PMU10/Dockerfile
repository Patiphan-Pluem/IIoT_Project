FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

RUN pip install numpy synchrophasor 

WORKDIR /app

COPY TinyPMU10.py /app/

CMD ["python3", "TinyPMU10.py"]