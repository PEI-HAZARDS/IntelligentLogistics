# Running the AgentA Microservice Docker Container

This Dockerfile builds a Docker image for the AgentA microservice, which appears to be a Python-based application involving computer vision (using YOLO models), Kafka integration, and RTMP streaming to NGINX. It uses Python 3.11 as the base, installs necessary dependencies, downloads a YOLO model, and runs the service via `init.py`.

## Building the Docker Image
1. Navigate to the directory containing the Dockerfile.
2. Run the following command to build the image:
   ```
   docker build --rm  -t agenta:latest . 
   ```
   - `-t agenta:latest`: Tags the image with a name (you can change this).
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
  *When to change*: Always update this to point to your actual Kafka server(s).

- **MODELS_PATH=/app/agentA_microservice/data**  
  Defines the directory where YOLO models are downloaded and stored. The `setup.py` script uses this during build.  
  *When to change*: If you want models stored elsewhere (e.g., a mounted volume for persistence). Ensure the path exists and is writable.

- **GATE_ID=gate01**  
  An identifier, likely for the microservice instance (e.g., a gate or node ID in a distributed system).  
  *When to change*: To uniquely identify different instances or deployments (e.g., "gate02" for a second container).

- **NGINX_RTMP_HOST=10.255.32.35**  
  The hostname or IP of the NGINX server handling RTMP (Real-Time Messaging Protocol) streams. Probably used for video streaming output.  
  *When to change*: Point to your NGINX server's address.

- **NGINX_RTMP_PORT=1935**  
  The port for the NGINX RTMP service.  
  *When to change*: If your NGINX RTMP listens on a different port (1935 is the standard default).