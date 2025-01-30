FROM python:3.13-slim

WORKDIR /web_application

COPY requirements.txt /web_application/
RUN pip install --no-cache-dir -r /web_application/requirements.txt

COPY . /web_application

EXPOSE 3000
EXPOSE 6000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD curl -f http://localhost:8000 || exit 1

CMD exec python main.py
