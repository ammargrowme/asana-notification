FROM python:3.8-slim-buster

# Install required system dependencies
RUN apt-get update && apt-get install -y gcc

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080
