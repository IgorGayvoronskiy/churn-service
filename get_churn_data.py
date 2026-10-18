import shutil
from pathlib import Path

import kagglehub

DATASET_ID = "abdulwadood11220/netflix-customer-churn-dataset"
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
DOWNLOAD_DIR = PROJECT_DIR / "data_download"
CSV_NAME = "netflix_customer_churn.csv"


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    destination = DATA_DIR / CSV_NAME

    if destination.exists():
        raise FileExistsError(
            f"Файл уже существует: {destination}. "
            "Он не был перезаписан."
        )

    print(f"Downloading Kaggle dataset: {DATASET_ID}")
    print(f"Temporary destination: {DOWNLOAD_DIR}")

    downloaded_path = Path(
        kagglehub.dataset_download(
            DATASET_ID,
            output_dir=str(DOWNLOAD_DIR),
        )
    )

    # Ищем CSV среди загруженных файлов.
    csv_files = list(downloaded_path.rglob("*.csv"))

    if not csv_files:
        raise FileNotFoundError(
            f"В скачанном датасете не найден CSV: {downloaded_path}"
        )

    # Если CSV несколько, не выбираем файл наугад.
    if len(csv_files) > 1:
        raise RuntimeError(
            "Найдено несколько CSV-файлов: "
            + ", ".join(str(path) for path in csv_files)
        )

    source = csv_files[0]

    # Переносим CSV в data/, не затрагивая остальные файлы.
    shutil.copy2(source, destination)

    print("\nDataset downloaded and copied successfully.")
    print(f"Source: {source}")
    print(f"Destination: {destination}")


if __name__ == "__main__":
    main()