# Quick setup — YOLO_OCR

## 1- Import necessary data (setup.py) 
It downloads the pretrained models listed in the script into the `YOLO_OCR/data/`  using **gdown**. Run it once to populate `YOLO_OCR/data/` before running the agents.

```sh
python3 setup.py
```

## 2-  Virtual environment (recommended)

You should create a virtual environment to install and manage the necessary python packages.

```sh
python3 -m venv .venv

source venv/bin/activate

pip install -r requirements.txt

```

## 3- Run main script

Finally run the main script (Not really implmented yet)

```sh
python3 main.py
```