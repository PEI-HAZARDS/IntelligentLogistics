import os
import glob

# Set your dataset folder
DATASET_DIR = "./Trucks/"

# Extensions of files that should be deleted along with the .txt
ASSOCIATED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".xml", ".json"]  

for txt_file in glob.glob(os.path.join(DATASET_DIR, "*.txt")):
    with open(txt_file, "r") as f:
        lines = f.readlines()

    # Keep only lines that belong to class "Truck"
    truck_lines = [line for line in lines if line.strip().startswith("Truck")]

    base_name, _ = os.path.splitext(txt_file)

    if not truck_lines:
        # No truck → delete annotation + associated files
        os.remove(txt_file)
        print(f"Deleted: {txt_file}")
        for ext in ASSOCIATED_EXTENSIONS:
            other_file = base_name + ext
            if os.path.exists(other_file):
                os.remove(other_file)
                print(f"Deleted: {other_file}")
    else:
        # Keep only trucks in the annotation
        with open(txt_file, "w") as f:
            f.writelines(truck_lines)
        print(f"Cleaned (kept trucks only): {txt_file}")

# Optional: Remove any leftover JSON files if they are no longer needed
for txt_file in glob.glob(os.path.join(DATASET_DIR, "*.json")):
    os.remove(txt_file)
    print(f"Deleted JSON file: {txt_file}")

