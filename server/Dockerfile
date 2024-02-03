# Use the official Python image as the base image
FROM python:3.11
WORKDIR /app

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/

EXPOSE 5000

CMD ["python", "btc_ltc.py"]