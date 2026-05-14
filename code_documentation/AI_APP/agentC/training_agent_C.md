# ADR Plate Detection Training History

This document summarizes the training history and reasoning behind the ADR orange plate detection model. It is meant as project documentation, not as a record of one temporary training folder.

## Goal

The goal was to train an object detection model capable of identifying orange ADR / hazard plates on trucks.

No suitable public dataset existed for this specific task, so the dataset was created manually. We collected the images ourselves and labelled every image by hand in YOLO format. The detection class used for the final dataset was:

- `hazard_plate`

## First Training Phase: Larger Model, Smaller Dataset

The first training phase used a smaller manually labelled dataset of roughly 400 positive ADR-plate images.

At this stage, we trained with a YOLO large model. The results were decent, but the model was heavier than necessary for the project goal. Since we wanted something faster and easier to deploy while keeping similar detection quality, we later moved away from the large model and restarted the training pipeline with a nano model.

This first phase also revealed an important weakness: the model was less reliable on empty ADR plates. These plates are visually different from filled/written ADR plates, and the model did not identify them with the same confidence.

## Dataset Expansion

To address the empty-plate weakness, we expanded the dataset with more manually labelled images. A significant part of the added data focused on empty ADR plates, because that was the failure case we wanted to improve.

The later regular dataset contained approximately:

- 697 total images
- 597 positive images
- 100 negative images
- 720 labelled ADR plate boxes

Compared with the first dataset of roughly 400 positive images, this means we likely added around 200 positive examples during the second phase, many of them targeting the empty ADR plate case.

The dataset also included negative images so the model could learn when no ADR plate was present.

## Second Training Phase: YOLO11 Nano

After expanding the dataset, we restarted training from a YOLO11 nano baseline instead of continuing from the earlier larger model.

The reason for this change was speed and practicality. The larger model was not necessary if a nano model could achieve comparable performance on this narrow one-class detection task. Because the target object is visually specific and the dataset was curated for this use case, YOLO11 nano was a good fit.

Two main preserved nano runs were produced:

1. `orange_plates_v1`
2. `orange_plates_v2`

Both used the regular expanded dataset, with one class: `hazard_plate`.

## `orange_plates_v1`

This was the first nano training run after restarting from the YOLO11 nano baseline.

Training setup:

- Model family: YOLO11 nano
- Dataset: expanded regular dataset with negatives
- Epochs: 200
- Image size: 640
- Batch size: 16
- Online augmentation enabled during training

Main augmentation ideas used during training:

- small rotations
- small translations
- scale changes
- slight perspective changes
- horizontal flips
- HSV/color variation
- mosaic
- light mixup

Best validation result:

- Best mAP50-95: 0.60854
- mAP50: 0.98448
- Precision: 0.96073
- Recall: 0.94095

This run confirmed that the nano model could perform well on the expanded dataset.

## `orange_plates_v2`

The second nano run continued from the best `orange_plates_v1` model and trained again on the regular expanded dataset.

This run was kept because it performed slightly better overall, especially on the metric we cared about most for localization quality.

Best validation result:

- Best mAP50-95: 0.61970
- mAP50: 0.98192
- Precision: 0.96690
- Recall: 0.97372

Final epoch result:

- mAP50-95: 0.60166
- mAP50: 0.96647
- Precision: 0.95622
- Recall: 0.93333

The best checkpoint from this run became the retained model.

## Augmentation Experiments

Augmentation was explored in more than one way during the project.

For the retained `orange_plates_v2` model, the training used the regular expanded dataset together with online YOLO/Ultralytics augmentations.

Offline augmentation was also tried in a previous or later discarded experiment. This produced an augmented version of the dataset and was tested as part of the search for better performance. However, the augmented-data experiments did not outperform the retained `orange_plates_v2` result, so they were not kept as the final model path.

Approximate augmented dataset size:

- 1734 total images
- 1432 positive images
- 302 negative images
- 1561 labelled ADR plate boxes

The takeaway was that simply increasing the dataset through offline augmentation did not beat the cleaner regular dataset plus online augmentation setup.

## Later Experiments

After `orange_plates_v2`, additional training attempts were made using the regular dataset and/or the augmented dataset.

These later experiments started from the strong `orange_plates_v2` baseline, but they produced worse results. Because they did not improve performance, they were discarded and the project settled on `orange_plates_v2`.

## Final Training Story

The final sequence was:

1. Manually created an ADR plate dataset because no valid public dataset existed for the task.
2. Trained initial larger-model experiments on roughly 400 positive labelled images.
3. Identified a weakness with empty ADR plates.
4. Added more manually labelled data, especially examples of empty ADR plates.
5. Restarted training with YOLO11 nano to reduce model size and improve speed.
6. Trained `orange_plates_v1` from the nano baseline on the expanded regular dataset.
7. Fine-tuned into `orange_plates_v2`, which performed slightly better.
8. Tried additional regular/augmented dataset experiments.
9. Kept `orange_plates_v2` because it gave the best balance of speed, size, and detection performance.

## Possible Upgrades

- Try a newer YOLOv26 model as an upgrade path and compare it directly against the retained YOLO11 nano model.
- Re-test nano vs small/medium variants if deployment speed allows it, especially if the dataset grows.
- Add more difficult edge cases, especially empty ADR plates, distant plates, partially occluded plates, dirty plates, and unusual lighting.
- Keep a fixed validation/test split so future training runs can be compared fairly.
- Record each future run's dataset version, model version, metrics, and main reason for the experiment.

## Main Lessons

- A focused, manually labelled dataset was more important than using a larger model.
- Empty ADR plates needed deliberate representation in the dataset because they were a distinct failure case.
- YOLO11 nano was sufficient for this one-class detector and made the model faster while keeping strong performance.
- Offline augmentation was worth testing, but the best retained result came from the regular expanded dataset with online training augmentation.
- Future retraining should preserve the reasoning behind each run, especially what data changed and which failure case the change was meant to address.
