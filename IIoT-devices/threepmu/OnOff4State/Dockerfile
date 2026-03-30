FROM python:3.9-slim

WORKDIR /app

RUN pip install --no-cache-dir synchrophasor

COPY TinyPMU.py .
COPY TinyPMU2.py .
COPY TinyPMU3.py .

EXPOSE 1410
EXPOSE 1411
EXPOSE 1412

CMD sh -c "python TinyPMU.py & python TinyPMU2.py & python TinyPMU3.py && wait"