# AgentC Microservice - Hazard Plate Recognition Agent (10.255.32.128)

**AgentC** is the third agent in the hazardous vehicle detection pipeline. It operates in parallel with AgentB, also listening for truck detection events from Kafka. AgentC specializes in detecting hazard plates (ADR plates) that display UN numbers and Kemler codes for dangerous goods classification. It uses YOLOv8 for detection, PaddleOCR for text extraction, and the same consensus algorithm as AgentB.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Hazard Plate Format](#hazard-plate-format)
- [Consensus Algorithm](#consensus-algorithm)
- [Internal Components](#internal-components)
- [Kafka Events](#kafka-events)
- [Running with Docker](#running-with-docker)
- [Environment Variables](#environment-variables)

---

## How It Works

### Operation Cycle

1. **Event Consumption**: AgentC subscribes to the `truck-detected-{GATE_ID}` Kafka topic (same as AgentB) and waits for truck detection events.

2. **Stream Connection**: Upon receiving an event, it connects to the high-quality RTMP stream from NGINX.

3. **Frame Buffering**: Frames are captured into a queue for processing, with dynamic frame fetching as needed.

4. **Hazard Plate Detection**: Each frame is processed by YOLOv8 (`YOLO_Hazard_Plate`) to detect orange ADR hazard plates.

5. **OCR Extraction**: Detected hazard plate crops are processed by PaddleOCR to extract the Kemler code and UN number.

6. **Consensus Building**: OCR results are fed into a consensus algorithm that votes on each character position across multiple frames.

7. **Code Parsing**: The final text is parsed to extract the Kemler code (top) and UN number (bottom).

8. **Result Publication**: Results are published to `hz-results-{GATE_ID}` and the best crop is uploaded to MinIO.

---

## Hazard Plate Format

Hazard plates (ADR plates) display two codes:

```
┌─────────────┐
│    33       │  ← Kemler Code (Hazard Identification Number)
├─────────────┤
│   1203      │  ← UN Number (Substance Identification)
└─────────────┘
```

### Kemler Code (HIN)
- Indicates the type of danger (e.g., 33 = highly flammable liquid)
- First digit: primary hazard
- Second digit: secondary hazard
- 'X' prefix: reacts dangerously with water

### UN Number
- 4-digit number identifying the specific dangerous substance
- Example: 1203 = Petrol/Gasoline

---

## Consensus Algorithm

The consensus algorithm is identical to AgentB's, ensuring accuracy across multiple frames:

### How It Works

1. **Character Voting**: Each OCR result votes for characters at their respective positions
2. **Confidence Weighting**: High-confidence results (≥95%) get 2 votes, others get 1 vote
3. **Length Normalization**: After 3 samples, only texts matching the most common length are accepted
4. **Decision Threshold**: A character is "decided" when it reaches 8 votes at a position
5. **Consensus Check**: Full consensus is reached when 80% of positions are decided

### Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `decision_threshold` | 8 | Votes needed to decide a character |
| `consensus_percentage` | 80% | Positions that must be decided for full consensus |
| `max_frames` | 40 | Maximum frames to process before returning best result |
| `min_confidence` | 0.80 | Minimum OCR confidence to accept a reading |

---

## Internal Components

### `AgentC` (AgentC.py)
Main orchestrator class:
- **Kafka Integration**: Consumer for `truck-detected`, Producer for `hz-results`
- **Frame Management**: Queue-based frame buffering with on-demand capture
- **Consensus Engine**: Position-based character voting system
- **Code Parsing**: Separates Kemler and UN codes from recognized text

### `YOLO_Hazard_Plate` (YOLO_Hazard_Plate.py)
YOLOv8 model wrapper for hazard plate detection:
- Uses custom-trained `hazard_plate_model.pt`
- Methods: `detect()`, `get_boxes()`, `found_hazard_plate()`

### `PaddleOCR` (PaddleOCR.py)
OCR engine for text extraction:
- Extracts text and confidence from hazard plate crops
- Handles the two-line format of hazard plates

### `CropStorage` (CropStorage.py)
MinIO integration for image storage:
- Uploads crop images to configured MinIO bucket
- Returns public URLs for stored images

### `RTSPStream` (RTSPstream.py)
Multi-protocol video stream reader:
- Supports RTSP, RTMP, and HTTP streams (via FFmpeg/OpenCV)
- Thread-safe frame reading with minimal buffer

---

## Kafka Events

### Input Event (Consumed)
**Topic**: `truck-detected-{GATE_ID}`

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "confidence": 0.95,
  "detections": 1
}
```
**Headers**: `truckId`

### Output Event (Produced)
**Topic**: `hz-results-{GATE_ID}`

```json
{
  "timestamp": "2024-01-15T10:30:05Z",
  "un": "1203",
  "kemler": "33",
  "confidence": 0.92,
  "cropUrl": "http://minio:9000/hz-crops/hz_TRK123_33_1203.jpg"
}
```
**Headers**: `truckId` (propagated from input)

---

## Running with Docker

### Building the Docker Image

1. Navigate to the directory containing the Dockerfile.
2. Run the following command to build the image:
   ```
   docker build --rm -t agentc:latest .
   ```
   - `-t agentc:latest`: Tag for the image (you can change this).
   - The build process will:
     - Install system dependencies (e.g., OpenCV, PaddlePaddle).
     - Install Python packages from `requirements.txt`.
     - Copy the source code.
     - Download the YOLO model via `setup.py`.
     - Prepare the container to run `init.py`.

If the build fails (e.g., network issues), check the error logs for details.

### Running the Docker Container

1. After building, run the container:
   ```
   docker run -d agentc:latest
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

---

## Environment Variables

The variables below are defined in the Dockerfile but can be overridden at runtime with `-e` flags. Configure them according to your environment (production vs development).

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP` | `10.255.32.143:9092` | Kafka server address (host:port) |
| `GATE_ID` | `1` | Identifier for the gate that the agent monitors |
| `NGINX_RTMP_HOST` | `10.255.32.80` | Hostname/IP of the NGINX-RTMP server |
| `NGINX_RTMP_PORT` | `1935` | Port for the NGINX RTMP service |
| `MINIO_HOST` | `10.255.32.82` | MinIO server hostname/IP |
| `MINIO_PORT` | `9000` | MinIO S3 API port |
| `ACCESS_KEY` | (required) | MinIO access key |
| `SECRET_KEY` | (required) | MinIO secret key |
| `BUCKET_NAME` | `hz-crops` | MinIO bucket for storing hazard plate crops |
| `MODELS_PATH` | `/app/agentC_microservice/data` | Directory where YOLO models are stored |

---

## Additional Notes

- **Parallel Execution**: AgentC runs in parallel with AgentB, both consuming the same `truck-detected` events.
- **Message Skipping**: AgentC skips old Kafka messages and processes only the latest to avoid processing stale detections.
- **Graceful Shutdown**: The agent properly releases stream resources and flushes Kafka messages on shutdown.
- **N/A Handling**: If Kemler or UN cannot be parsed, they are published as "N/A".