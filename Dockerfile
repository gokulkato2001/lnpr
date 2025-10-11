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


# # Base image with Python
# FROM python:3.10-slim

# # Install system dependencies required for OpenCV
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1 \
#     libglib2.0-0 \
#  && rm -rf /var/lib/apt/lists/*

# # Set working directory inside the container
# WORKDIR /app

# # Copy requirements first and install them
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# # Copy your source code into the image
# COPY . .

# # Default command to run your listener
# CMD ["python", "main.py"]


#  Actual implementation
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y libgl1 && \
    pip install --no-cache-dir -r requirements.txt

COPY . /app
CMD ["python", "-u", "listener.py"]

# FROM python:3.10-slim

# WORKDIR /app
# COPY requirements.txt .
# RUN apt-get update && apt-get install -y libgl1 && \
#     pip install --no-cache-dir -r requirements.txt

# COPY . /app

# # Create output directories with proper permissions
# RUN mkdir -p /app/lnpr_outputs/cropped_plates \
#              /app/lnpr_outputs/cropped_vehicles \
#              /app/lnpr_outputs/cropped_no_ocr \
#              /app/received_events && \
#     chmod -R 777 /app/lnpr_outputs /app/received_events

# CMD ["python", "-u", "listener.py"]
