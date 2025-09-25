# Use Python 3.11 base image from Apify
FROM apify/actor-python:3.11

# Set working directory
WORKDIR /usr/src/app

# Switch to root temporarily for installations
USER root

# Install Chrome dependencies and virtual display for nodriver
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    xvfb \
    x11-utils \
    x11-xserver-utils \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    libxss1 \
    libgconf-2-4 \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt first for better caching
COPY --chown=myuser:myuser requirements.txt ./

# Switch back to myuser for security
USER myuser

# Install Python dependencies
RUN echo "Python version:" \
    && python --version \
    && echo "Pip version:" \
    && pip --version \
    && echo "Installing dependencies from requirements.txt:" \
    && pip install -r requirements.txt \
    && echo "All installed Python packages:" \
    && pip freeze

# Copy the rest of the source code
COPY --chown=myuser:myuser . ./

# Set environment variables for Chrome and virtual display
ENV CHROME_BIN=/usr/bin/google-chrome-stable
ENV CHROME_PATH=/usr/bin/google-chrome-stable
ENV DISPLAY=:99
ENV XVFB_ARGS="-screen 0 1920x1080x24 -ac +extension GLX +render -noreset"

# Run the actor
CMD python -m src