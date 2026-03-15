FROM python:3.9-slim

WORKDIR /app

RUN pip install --no-cache-dir synchrophasor

COPY TinyPMU1.py .
COPY TinyPMU2.py .

EXPOSE 1410
EXPOSE 1411

CMD sh -c "python TinyPMU1.py & python TinyPMU2.py && wait"