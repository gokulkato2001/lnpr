# FROM python:3.10-slim

# # install libGL for OpenCV
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1 \
#     libglib2.0-0 \
#  && rm -rf /var/lib/apt/lists/*

# # copy requirements and install dependencies
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# # copy the rest of your app
# COPY . /app
# WORKDIR /app

# CMD ["python", "main.py"]


# Base image with Python
FROM python:3.10-slim

# Install system dependencies required for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# Set working directory inside the container
WORKDIR /app

# Copy requirements first and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your source code into the image
COPY . .

# Default command to run your listener
CMD ["python", "main.py"]
