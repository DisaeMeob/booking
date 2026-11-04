from fastapi import APIRouter, UploadFile, BackgroundTasks
import shutil

from src.config import IMAGES_DIR
from src.tasks.tasks import resize_image

router = APIRouter(prefix="/images", tags=["Изображения отелей"])


@router.post("")
def upload_image(file: UploadFile):
    image_path = IMAGES_DIR / file.filename
    with open(image_path, "wb+") as new_file:
        shutil.copyfileobj(file.file, new_file)

    resize_image.delay(str(image_path))

@router.post("/background")
def upload_images_background(file: UploadFile, background_task: BackgroundTasks):
    image_path = IMAGES_DIR / file.filename
    with open(image_path, "wb+") as new_file:
        shutil.copyfileobj(file.file, new_file)

    background_task.add_task(resize_image, image_path)