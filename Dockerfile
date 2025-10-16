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


# #  Actual implementation
# FROM python:3.10-slim

# WORKDIR /app
# COPY requirements.txt .
# RUN apt-get update && apt-get install -y libgl1 && \
#     pip install --no-cache-dir -r requirements.txt

# COPY . /app
# CMD ["python", "-u", "listener.py"]

# # Actual implementation own lpr data

# FROM python:3.9-slim-bullseye

# WORKDIR /app

# # ---- System dependencies ----
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1-mesa-glx \
#     libglib2.0-0 \
#     ffmpeg \
#  && rm -rf /var/lib/apt/lists/*

# # ---- Install Python dependencies ----
# COPY requirements.txt .
# RUN pip install --no-cache-dir --upgrade pip \
#  && pip install --no-cache-dir -r requirements.txt \
#  && pip install --no-cache-dir matplotlib==3.9.0 tqdm==4.66.5 pika==1.3.2 python-multipart==0.0.20 pandas==2.2.2 \
#  && pip install --no-cache-dir torch==2.3.1+cpu torchvision==0.18.1+cpu --index-url https://download.pytorch.org/whl/cpu \
#  && pip install --no-cache-dir --no-deps ultralytics==8.2.73

# # ---- Copy application code ----
# COPY . /app

# ENV PYTHONPATH=/app
# ENV PYTHONUNBUFFERED=1
# ENV OMP_NUM_THREADS=2
# ENV OPENBLAS_NUM_THREADS=2

# Actual implementation 2 - own lpr data (combined)

# FROM python:3.9-slim-bullseye

# WORKDIR /app

# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1-mesa-glx \
#     libglib2.0-0 \
#     ffmpeg \
#  && rm -rf /var/lib/apt/lists/*

# COPY . /app
# COPY requirements.txt .

# # ---- Lightweight deps first ----
# RUN pip install --no-cache-dir --upgrade pip \
#  && pip install --no-cache-dir -r requirements.txt

# # ---- Heavy ML packages ----
# RUN pip install --no-cache-dir matplotlib==3.9.0 tqdm==4.66.5 pandas==2.2.2 \
#  && pip install --no-cache-dir torch==2.3.1+cpu torchvision==0.18.1+cpu --index-url https://download.pytorch.org/whl/cpu \
#  && pip install --no-cache-dir --no-deps ultralytics==8.2.73
   

# ENV PYTHONPATH=/app
# ENV PYTHONUNBUFFERED=1
# ENV OMP_NUM_THREADS=2
# ENV OPENBLAS_NUM_THREADS=2

# CMD ["bash", "-c", "uvicorn optimized_api:app --host 0.0.0.0 --port 8080 & python -u listener.py"]

# # # Final implementation without API old

# FROM python:3.9-slim-bullseye
# WORKDIR /app

# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1-mesa-glx libglib2.0-0 ffmpeg && \
#     rm -rf /var/lib/apt/lists/*

# COPY . /app
# COPY requirements.txt .

# RUN pip install --no-cache-dir --upgrade pip \
#  && pip install --no-cache-dir -r requirements.txt \
#  && pip install --no-cache-dir torch==2.3.1+cpu torchvision==0.18.1+cpu --index-url https://download.pytorch.org/whl/cpu \
#  && pip install --no-cache-dir --no-deps ultralytics==8.2.73

# ENV PYTHONUNBUFFERED=1
# CMD ["python", "-u", "listener.py"]

# # Final implementation without API

# -------------------------------------------------------
# Base image
# -------------------------------------------------------
# FROM python:3.9-slim-bullseye

# WORKDIR /app

# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1-mesa-glx \
#     libglib2.0-0 \
#     ffmpeg \
#  && rm -rf /var/lib/apt/lists/*

# COPY . /app
# COPY requirements.txt .

# RUN pip install --no-cache-dir --upgrade pip \
#  && pip install --no-cache-dir -r requirements.txt

# RUN pip install --no-cache-dir matplotlib==3.9.0 tqdm==4.66.5 pandas==2.2.2 \
#  && pip install --no-cache-dir torch==2.3.1+cpu torchvision==0.18.1+cpu \
#         --index-url https://download.pytorch.org/whl/cpu \
#  && pip install --no-cache-dir --no-deps ultralytics==8.2.73

# ENV PYTHONUNBUFFERED=1
# ENV OMP_NUM_THREADS=2
# ENV OPENBLAS_NUM_THREADS=2

# CMD ["python", "-u", "listener.py"]


# #  Actual implementation 2
# Dockerfile — event_listener with embedded LPR inference (no API, clean OUTPUT_ROOT setup)

FROM python:3.9-slim-bullseye

WORKDIR /app

# ---- System dependencies ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# ---- Install lightweight Python dependencies first ----
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ---- Install heavy dependencies separately for better caching ----
RUN pip install --no-cache-dir torch==2.3.1+cpu torchvision==0.18.1+cpu \
      --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir --no-deps ultralytics==8.2.73 \
 && pip install --no-cache-dir matplotlib==3.9.0 tqdm==4.66.5 pandas==2.2.2

# ---- Copy your application ----
COPY . /app

# ---- Environment ----
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=2
ENV OPENBLAS_NUM_THREADS=2

# ---- Default command ----
CMD ["python", "-u", "listener.py"]


