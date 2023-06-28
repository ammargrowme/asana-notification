FROM python:3.8-slim-buster

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

# Copy credentials.json
COPY credentials.json credentials.json

CMD [ "python", "./asana-notification.py" ]
