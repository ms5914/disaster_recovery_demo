FROM python:3.9-slim

WORKDIR /app

# Update pip first
RUN pip install --no-cache-dir --upgrade pip

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/app.py .

CMD ["python", "app.py"]
