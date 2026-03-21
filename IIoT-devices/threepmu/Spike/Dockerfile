FROM python:3.9-slim

WORKDIR /app

RUN pip install --no-cache-dir synchrophasor

COPY pmu1.py .
COPY pmu2.py .
COPY spike.py .

EXPOSE 1410
EXPOSE 1411
EXPOSE 1412

CMD sh -c "python pmu1.py & python pmu2.py & python spike.py && wait"