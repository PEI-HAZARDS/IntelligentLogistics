# AgentA Microservice - Truck Detection Agent (10.255.32.134)

**AgentA** is the first agent in the hazardous vehicle detection pipeline. It continuously monitors a low-quality video stream and detects the presence of trucks using a YOLOv8 model. When a truck is detected, it publishes an event to Kafka to notify downstream agents.

---

##  Table of Contents

- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [Internal Components](#internal-components)
- [Data Flow](#data-flow)
- [Running with Docker](#running-with-docker)
- [Environment Variables](#environment-variables)

---


## How It Works

### Operation Cycle

1. **Stream Connection**: AgentA connects to the NGINX-RTMP server to receive the low-quality video stream from the assigned gate.

2. **Frame Capture**: A dedicated thread (`RTSPStream`) continuously reads frames from the stream, ensuring low latency and thread-safety.

3. **Truck Detection**: Each frame is processed by the YOLOv8 model (`YOLO_Truck`), configured to detect only the "truck" class (ID 7).

4. **Debounce (Throttling)**: To avoid duplicate messages, there is a minimum interval of **35 seconds** between published events.

5. **Kafka Publishing**: When a truck is detected (and the debounce interval has passed), a JSON event is published to the `truck-detected-{GATE_ID}` topic.

### Kafka Event Format

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "confidence": 0.95,
  "detections": 1
}
```

**Event Headers:**
- `truckId`: Unique generated identifier (e.g., `TRKa1b2c3d4`)

---

## Internal Components

### `AgentA` (AgentA.py)
Main class that orchestrates the entire process:
- **Initialization**: Loads the YOLO model and configures the Kafka producer
- **Main Loop** (`_loop`): Continuously processes frames
- **Publishing** (`_publish_truck_detected`): Sends events to Kafka
- **Retry Logic** (`_connect_to_stream_with_retry`): Automatic stream reconnection (up to 10 attempts)
- **Graceful Shutdown** (`stop`): Cleanly releases resources

### `YOLO_Truck` (YOLO_Truck.py)
YOLOv8 model wrapper for truck detection:
- Uses the pre-trained `truck_model.pt` model
- Filters only "truck" class detections (ID 7)
- Methods:
  - `detect(image)`: Runs inference on a frame
  - `get_boxes(results)`: Extracts bounding boxes and confidence scores
  - `truck_found(results)`: Checks if trucks were detected

### `RTSPStream` (RTSPstream.py)
Multi-protocol video stream reader:
- Supports RTSP, RTMP, and HTTP streams (via FFmpeg/OpenCV)
- Dedicated thread for continuous frame reading
- Minimum buffer for low latency
- Automatic failure recovery (up to 10 consecutive failures)

---


## 🐳 Running with Docker

### Building the Docker Image

1. Navigate to the directory containing the Dockerfile.
2. Run the following command to build the image:
   ```bash
   docker build --rm -t agenta:latest .
   ```
   - `-t agenta:latest`: Tag for the image (you can change this).
   - The build process will:
     - Install system dependencies (e.g., OpenCV).
     - Install Python packages from `requirements.txt`.
     - Copy the source code.
     - Download the YOLO model via `setup.py`.
     - Prepare the container to run `init.py`.

If the build fails (e.g., network issues), check the error logs for details.

### Running the Docker Container

1. After building, run the container:
   ```bash
   docker run -d agenta:latest
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
   ```bash
   docker stop {container_id}
   docker rm {container_id}
   ```

---

## 🔧 Environment Variables

The variables below are defined in the Dockerfile but can be overridden at runtime with `-e` flags. Configure them according to your environment (production vs development).

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP` | `10.255.32.143:9092` | Kafka server address (host:port) |
| `GATE_ID` | `1` | Identifier for the gate that the agent monitors |
| `NGINX_RTMP_HOST` | `10.255.32.35` | Hostname/IP of the NGINX-RTMP server |
| `NGINX_RTMP_PORT` | `1935` | Port for the NGINX RTMP service |
| `RTSP_STREAM_LOW` | (generated) | Low-quality stream URL (e.g., `rtmp://{host}:{port}/streams_low/gate{ID}`) |
| `MODELS_PATH` | `/app/agentA_microservice/data` | Directory where the YOLO model is stored |

---

## 📝 Additional Notes

- **Throttling**: The 35-second interval between Kafka messages prevents overload when multiple trucks pass in sequence.
- **Resilience**: The agent attempts to reconnect to the stream up to 10 times before failing definitively.
- **Thread-Safety**: Stream reading is done in a separate thread with locks to ensure frame consistency.