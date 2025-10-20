import os
import gdown  # type: ignore

# Files to download (name -> (Google Drive ID, destination folder))
FILES = {
    "license_plate_model.pt": ("1h3AXDLcFj17kXo7L20jQeId-upQovGQu", "agentB_microservice/data"),
    "truck_model.pt": ("1LL0zMJrppkqd51zQDLixzlOIJvwlMDXe", "agentA_microservice/data"),
}

def main():
    print("=== Downloading models from Google Drive ===")
    base_dir = os.path.dirname(__file__)

    for filename, (file_id, subdir) in FILES.items():
        # Build the full destination directory path
        dest_dir = os.path.join(base_dir, subdir)
        os.makedirs(dest_dir, exist_ok=True)

        dest_path = os.path.join(dest_dir, filename)
        if os.path.exists(dest_path):
            print(f"{filename} already exists in {subdir} — skipping.")
            continue

        url = f"https://drive.google.com/uc?id={file_id}"
        print(f"Downloading {filename} to {subdir}...")
        gdown.download(url, dest_path, quiet=False)

    print("All files ready!")

if __name__ == "__main__":
    main()
