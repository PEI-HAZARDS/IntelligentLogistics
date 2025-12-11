# Running the AgentB Microservice Docker Container

This Dockerfile builds a Docker image AgentB microservice. It uses Python 3.11 as the base, installs necessary dependencies, downloads a YOLO model, and runs the service via `init.py`.

## Building the Docker Image
1. Navigate to the directory containing the Dockerfile.
2. Run the following command to build the image:
   ```
   docker build --rm  -t agentb:latest . 
   ```
   - `-t agentb:latest`: Tags the image with a name (you can change this).
   - The build process will:
     - Install system dependencies (e.g., for OpenCV).
     - Install Python packages from `requirements.txt`.
     - Copy the source code.
     - Download the YOLO model using the `setup.py` script.
     - Prepare the container to run `init.py`.

If the build fails (e.g., due to network issues or missing files), check the error logs for details.

## Running the Docker Container
1. After building, run the container with:
   ```
   docker run -d {container_name}
   ```

2. To override environment variables (e.g., for custom Kafka settings), use the `-e` flag:
   ```
   docker run -d \
   -e KAFKA_BOOTSTRAP="your.kafka.server:9092" \
   -e GATE_ID="custom_gate_id" \
   {container_name}
   ```

3. Check logs for debugging:
   ```
   docker logs -f {container_name}
   ```

4. Stop and remove the container:
   ```
   docker stop {container_name}
   docker rm {container_name}
   ```

## Environment Variables
These are set in the Dockerfile but can be overridden at runtime using `-e` flags (as shown above). They configure the application's behavior, such as paths, servers, and IDs. Change them based on your environment (e.g., production vs. development).

- **KAFKA_BOOTSTRAP=10.255.32.143:9092**  
  Specifies the Kafka bootstrap server address (host:port). Used for connecting to a Kafka cluster for messaging/streaming.

- **MODELS_PATH=/app/agentb_microservice/data**  
  Defines the directory where YOLO models are downloaded and stored. The `setup.py` script uses this during build.

- **GATE_ID=gate01**  
  Gate that the agent is assigned to.

- **NGINX_RTMP_HOST=10.255.32.35**  
  The hostname or IP of the NGINX server handling RTMP (Real-Time Messaging Protocol) streams.

- **NGINX_RTMP_PORT=1935**  
  The port for the NGINX RTMP service.