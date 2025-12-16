# AgentB Microservice - License Plate Recognition Agent (10.255.32.32)

**AgentB** is the second agent in the hazardous vehicle detection pipeline. It listens for truck detection events from Kafka, connects to a high-quality video stream, detects license plates using YOLOv8, extracts text using PaddleOCR, and applies a consensus algorithm across multiple frames to ensure accurate results. The final license plate text and crop image are published to Kafka and stored in MinIO.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Consensus Algorithm](#consensus-algorithm)
- [Internal Components](#internal-components)
- [Kafka Events](#kafka-events)
- [Running with Docker](#running-with-docker)
- [Environment Variables](#environment-variables)

---

## How It Works

### Operation Cycle

1. **Event Consumption**: AgentB subscribes to the `truck-detected-{GATE_ID}` Kafka topic and waits for truck detection events from AgentA.

2. **Stream Connection**: Upon receiving an event, it connects to the high-quality RTMP stream from NGINX to capture detailed frames.

3. **Frame Buffering**: Frames are captured into a queue for processing. The agent dynamically fetches more frames as needed.

4. **License Plate Detection**: Each frame is processed by YOLOv8 (`YOLO_License_Plate`) to detect license plate bounding boxes.

5. **Plate Classification**: Detected plates are classified using `PlateClassifier` to distinguish license plates from hazard plates (hazard plates are filtered out).

6. **OCR Extraction**: Valid license plate crops are processed by PaddleOCR to extract text and confidence scores.

7. **Consensus Building**: OCR results are fed into a consensus algorithm that votes on each character position across multiple frames.

8. **Result Publication**: Once consensus is reached (or frame limit hit), the final text is published to `lp-results-{GATE_ID}` and the best crop is uploaded to MinIO.

---

## Consensus Algorithm

The consensus algorithm ensures accuracy by aggregating OCR results across multiple frames:

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

### Best Crop Selection

The best crop is selected based on:
1. **Text Similarity**: Levenshtein distance to the final consensus text
2. **OCR Confidence**: Used as a tiebreaker when similarity is equal

---

## Internal Components

### `AgentB` (AgentB.py)
Main orchestrator class:
- **Kafka Integration**: Consumer for `truck-detected`, Producer for `lp-results`
- **Frame Management**: Queue-based frame buffering with on-demand capture
- **Consensus Engine**: Position-based character voting system
- **Crop Selection**: Levenshtein-based best crop selection

### `YOLO_License_Plate` (YOLO_License_Plate.py)
YOLOv8 model wrapper for license plate detection:
- Uses custom-trained `license_plate_model.pt`
- Methods: `detect()`, `get_boxes()`, `found_license_plate()`

### `PaddleOCR` (PaddleOCR.py)
OCR engine for text extraction:
- Extracts text and confidence from license plate crops
- Handles image preprocessing for optimal OCR results

### `PlateClassifier` (PlateClassifier.py)
CNN-based plate type classifier:
- Distinguishes between `LICENSE_PLATE` and `HAZARD_PLATE`
- Filters out hazard plates to avoid confusion

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
**Topic**: `lp-results-{GATE_ID}`

```json
{
  "timestamp": "2024-01-15T10:30:05Z",
  "licensePlate": "ABC1234",
  "confidence": 0.92,
  "cropUrl": "http://minio:9000/lp-crops/lp_TRK123_ABC1234.jpg"
}
```
**Headers**: `truckId` (propagated from input)

---

## Running with Docker

### Building the Docker Image

1. Navigate to the directory containing the Dockerfile.
2. Run the following command to build the image:
   ```
   docker build --rm -t agentb:latest .
   ```
   - `-t agentb:latest`: Tag for the image (you can change this).
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
   docker run -d agentb:latest
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
| `NGINX_RTMP_HOST` | `10.255.32.35` | Hostname/IP of the NGINX-RTMP server |
| `NGINX_RTMP_PORT` | `1935` | Port for the NGINX RTMP service |
| `MINIO_HOST` | `10.255.32.132` | MinIO server hostname/IP |
| `MINIO_PORT` | `9000` | MinIO S3 API port |
| `ACCESS_KEY` | (required) | MinIO access key |
| `SECRET_KEY` | (required) | MinIO secret key |
| `BUCKET_NAME` | `lp-crops` | MinIO bucket for storing license plate crops |
| `MODELS_PATH` | `/app/agentB_microservice/data` | Directory where YOLO models are stored |

---

## Additional Notes

- **Message Skipping**: AgentB skips old Kafka messages and processes only the latest to avoid processing stale detections.
- **Graceful Shutdown**: The agent properly releases stream resources and flushes Kafka messages on shutdown.
- **Partial Results**: If full consensus isn't reached within the frame limit, the best partial result is returned with reduced confidence.