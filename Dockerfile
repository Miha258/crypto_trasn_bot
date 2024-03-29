FROM python:3.9
WORKDIR /app

COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install 'flask[async]'

EXPOSE 5000

CMD ["python3", "bot.py"]