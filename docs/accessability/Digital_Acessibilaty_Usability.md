# M1 – Digital Accessibility and Usability

## 1. Context

Our system detects:

- Trucks
- License plates
- ADR Hazard plates

using YOLO-based models and a decision engine.

The system is operated by a single user:

- Gate Operator

The operator must quickly understand:

- If a truck is detected
- If a hazard plate is present
- What decision the system recommends (Allow / Deny / Manual Verification)

This milestone evaluates:

- Interface clarity
- Error handling
- Accessibility considerations
- Validation through automated tests

## 2. Interface Clarity

### 2.1 Is the UI Clear?

We evaluate:

- Is the detected license plate clearly visible on the dash?
- Is the ADR hazard plate number clearly displayed?
- Is system status clearly indicated (processing / detected / error)?
- Is the final decision clearly highlighted?

Important considerations:

- Critical information must be visually prioritized.
- Layout should be logically structured (camera → detection → decision).

### 2.2 Are Detection Results Easy to Understand?

We verify:

- License plate number is clearly displayed.
- Detection confidence (if shown) is understandable.
- No ambiguous or technical messages are shown to the operator.

### 2.3 Are Hazard Warnings Visually Obvious? (We can use the warning for going in the wrong way)

Hazard detection must:

- Include:
  - Text label (e.g., "Hazard Detected")
  - Warning icon (⚠)
  - Clear visual emphasis

We ensure sufficient contrast and readable font size.

### 2.4 Is Information Structured Logically?

The interface should follow a clear hierarchy:

1. Live camera feed
2. Detection results
3. Hazard status
4. System decision
5. Operator action (if applicable)

The operator should not need to search for critical information.

## 3. Error Handling

The system must handle operational failures gracefully.

### 3.1 Camera Failure

If camera connection is lost:

- Clear error message must appear.
- The message must explain what happened.
- Operator must know what action to take.

Example of good message:

> "Camera connection lost. Please verify network connection."


### 3.2 Plate Recognition Fails

If a truck is detected but plate reading fails:

Show a clear message:

> "License plate could not be recognized"

Allow operator needs to take action

### 3.3 Error Message Quality

Error messages should be:

- Clear
- Human-readable
- Action-oriented when possible
- Free of technical jargon

## 4. Tests to Be Performed

### 4.1 UI Behavior Tests (BDD / Automated)

We implement automated UI tests that simulate operator interaction.

- Example:
    - Feature: Vehicle Detection Display
      - Verify license plate appears when detected
      - Verify hazard code is displayed when present
      - Verify decision label updates correctly  

These tests validate interface consistency and clarity.

**Goal:**
Identify usability weaknesses in layout and clarity.

### 4.2 Usability tests (SUS)

We implement usability tests also focusing in interface consistency and clarity.

- Forms with a simple survey about our main interface and dashs
  - Test with a few users/clients

These tests validate interface consistency and clarity with real users.

**Goal:**
Identify usability weaknesses in layout and clarity.

### 4.3 API Clarity Tests ??????????????

Since the frontend depends on backend APIs:

- Verify consistency of API responses.
- Ensure error responses are standardized.
- Confirm meaningful HTTP status codes.
- Validate that frontend does not expose raw backend errors.

**Goal:**
Ensure backend communication does not reduce usability.

### 4.4 Deployment Tests

We evaluate:

- Can the system be deployed easily using Docker?
- Are environment variables clearly documented?
- Does the system fail gracefully if a service is down?

**Goal:**
Ensure the system is usable in a real operational environment.

### 4.5 Documentation Tests

We verify:

- README instructions are clear.
- Setup steps are easy to follow.
- No missing configuration steps.
- Terminology is understandable.

**Goal:**
Ensure new developers or operators can understand the system.

## 5. Conclusion

This milestone focuses on:

- Clear and intuitive interface design
- Proper handling of operational errors
- Basic accessibility principles
- Practical usability validation through testing

The objective is to ensure that the Gate Operator can:

- Quickly understand the system state
- React confidently to hazardous detections
- Handle failures without confusion