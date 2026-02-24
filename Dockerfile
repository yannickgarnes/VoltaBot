FROM python:3.11-slim

# Install Chromium and dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libxss1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest
COPY . .

# Environment variable to help the bot find chromium
ENV CHROMIUM_PATH=/usr/bin/chromium

CMD ["python", "bot.py"]
