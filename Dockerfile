FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (build-essential and libpq-dev for psycopg2 if postgres is used)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy entrypoint script to /usr/local/bin to prevent host mount overwrites
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

# Copy project files (including bundled DejaVuSans font and templates)
COPY . /app/

# Ensure in-app copy of entrypoint also has execution permissions and unix line endings
RUN if [ -f /app/entrypoint.sh ]; then sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh; fi

# Pre-collect static files into the image at build time
RUN python manage.py collectstatic --noinput

# Ensure data directory exists and writable permissions for SQLite
RUN mkdir -p /app/data && chmod -R 777 /app

# Expose default application port
EXPOSE 8000

# Set entrypoint and default command (gunicorn on 0.0.0.0:$PORT)
ENTRYPOINT ["/bin/sh", "/usr/local/bin/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--workers", "2", "--threads", "4"]
