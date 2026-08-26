FROM python:3.12-alpine

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app.py /app/app.py

RUN addgroup -S app && adduser -S -G app app \
    && mkdir -p /data \
    && chown app:app /data
USER app

EXPOSE 9000
CMD ["python", "/app/app.py"]
