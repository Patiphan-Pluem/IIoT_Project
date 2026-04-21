FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

RUN pip install numpy synchrophasor 

WORKDIR /app

COPY TinyPMU15.py /app/

CMD ["python3", "TinyPMU15.py"]