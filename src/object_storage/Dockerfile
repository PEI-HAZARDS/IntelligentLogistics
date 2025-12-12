FROM minio/minio:latest

# Expose MinIO API and console ports
EXPOSE 9000 9001

# Default command: run MinIO server storing data in /data and console on 9001
CMD ["server", "/data", "--console-address", ":9001"]
