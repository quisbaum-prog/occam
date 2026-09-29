FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
RUN pip install --no-cache-dir playwright==1.63.0 Pillow==11.3.0 \
    && apt-get update -qq && apt-get install -y -qq --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1002 bench
COPY capture.py /opt/benchmark/capture.py
USER bench
WORKDIR /home/bench
ENTRYPOINT ["python3", "/opt/benchmark/capture.py"]
