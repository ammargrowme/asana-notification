FROM python:3.11-slim

# No additional system dependencies are required for installing the
# Python packages, so we can rely on the slim image alone.

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080
