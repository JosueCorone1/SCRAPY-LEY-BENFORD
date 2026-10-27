FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_HEADLESS=true
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt && python -m playwright install --with-deps chromium
COPY . /app
CMD ["python", "main.py"]
