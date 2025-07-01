# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

COPY binaries/amd64/* /usr/local/bin/

RUN chmod +x /usr/local/bin/ffmpeg
RUN chmod +x /usr/local/bin/ffprobe
RUN chmod +x /usr/local/bin/mp4decrypt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install .

# Make port 5800 available to the world outside this container
EXPOSE 5800

# Run app.py when the container launches
CMD ["python", "app.py"]