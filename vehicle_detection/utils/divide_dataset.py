import os
import glob
import random
import shutil

# 🔧 CONFIG
SOURCE_IMAGES = "./Trucks/"   # folder containing images
SOURCE_LABELS = "./Trucks/"   # folder containing YOLO txt files
DATASET_DIR = "dataset"            # output dataset folder
SPLIT_RATIO = 0.8                  # 80% train / 20% test

# Supported image extensions
IMAGE_EXTS = [".jpg", ".jpeg", ".png"]

# --- Create folder structure ---
for split in ["train", "test"]:
    for sub in ["images", "labels"]:
        os.makedirs(os.path.join(DATASET_DIR, split, sub), exist_ok=True)

# --- Collect all image files ---
image_files = []
for ext in IMAGE_EXTS:
    image_files.extend(glob.glob(os.path.join(SOURCE_IMAGES, f"*{ext}")))

# Shuffle for randomness
random.shuffle(image_files)

# Split
split_idx = int(len(image_files) * SPLIT_RATIO)
train_files = image_files[:split_idx]
test_files = image_files[split_idx:]

def copy_files(file_list, split):
    for img_file in file_list:
        base = os.path.splitext(os.path.basename(img_file))[0]
        label_file = os.path.join(SOURCE_LABELS, base + ".txt")

        # Copy image
        shutil.copy(img_file, os.path.join(DATASET_DIR, split, "images", os.path.basename(img_file)))

        # Copy label if it exists
        if os.path.exists(label_file):
            shutil.copy(label_file, os.path.join(DATASET_DIR, split, "labels", os.path.basename(label_file)))
        else:
            print(f"⚠️ Warning: No label found for {img_file}")

# Copy train/test
copy_files(train_files, "train")
copy_files(test_files, "test")

print(f"✅ Dataset created in '{DATASET_DIR}' with {len(train_files)} train and {len(test_files)} test samples.")
