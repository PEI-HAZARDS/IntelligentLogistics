import os
import gdown # type: ignore

# Files to download (name -> Google Drive ID)
FILES = {
    "license_plate_model.pt": "1h3AXDLcFj17kXo7L20jQeId-upQovGQu",
    "truck_model.pt": "1LL0zMJrppkqd51zQDLixzlOIJvwlMDXe",
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

def main():
    print("=== Downloading models from Google Drive ===")
    for filename, file_id in FILES.items():
        dest_path = os.path.join(DATA_DIR, filename)
        if os.path.exists(dest_path):
            print(f"{filename} already exists — skipping.")
            continue
        url = f"https://drive.google.com/uc?id={file_id}"
        print(f"Downloading {filename}...")
        gdown.download(url, dest_path, quiet=False)
    print("All files ready!")

if __name__ == "__main__":
    main()
