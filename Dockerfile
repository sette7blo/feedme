FROM python:3.11-alpine

RUN apk add --no-cache gcc musl-dev libffi-dev

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    apk del gcc musl-dev libffi-dev

COPY . .

RUN mkdir -p recipes images data

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--preload", "--timeout", "120", "server:app"]
