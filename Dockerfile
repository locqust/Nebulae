# Dockerfile
# Use an official Python runtime as a parent image
FROM python:3.9-slim-bookworm

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y sqlite3

# Copy the schema.sql file explicitly before copying the rest of the app
# This ensures the schema is available for init_db()
COPY schema.sql .

# Copy the rest of the application code into the container
COPY . .

# Create necessary directories
RUN mkdir -p /app/instance /app/profile_pictures_storage /app/thumbnails /app/user_media /app/user_uploads

# Expose port 5000 for the Flask application
EXPOSE 5000

# Define the command to run the Flask application
# This is typically overridden by the 'command' in docker-compose.yml
# # Use gunicorn for production
# CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--threads", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
