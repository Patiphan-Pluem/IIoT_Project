FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

RUN pip install numpy synchrophasor 

WORKDIR /app

COPY TinyPMU60.py /app/

CMD ["python3", "TinyPMU60.py"]