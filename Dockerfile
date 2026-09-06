# syntax=docker/dockerfile:1

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY fakeESP32.py ./

RUN useradd --system --uid 1001 sensors
USER sensors

EXPOSE 5200

CMD ["python", "fakeESP32.py"]
