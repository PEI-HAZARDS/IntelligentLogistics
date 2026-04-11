FROM bluenviron/mediamtx:latest-ffmpeg

# Install bash (for ingest scripts) and curl (for healthcheck)
RUN apk add --no-cache bash curl

# Copy MediaMTX configuration
COPY mediamtx.yml /mediamtx.yml

# Copy ingest scripts
COPY ingest_streams.sh /usr/local/bin/ingest_streams.sh
COPY ingest_test_video.sh /usr/local/bin/ingest_test_video.sh
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    /usr/local/bin/ingest_streams.sh \
    /usr/local/bin/ingest_test_video.sh

# Ports:
#   1935  - RTMP  (ffmpeg ingest + AI agents)
#   8554  - RTSP  (alternative agent consumption)
#   8888  - HLS   (browser playback)
#   8889  - WebRTC (ultra-low latency browser)
#   9997  - API   (health check + management)
EXPOSE 1935 8554 8888 8889 9997

ENTRYPOINT ["/entrypoint.sh"]
