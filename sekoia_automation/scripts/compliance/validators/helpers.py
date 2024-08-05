import io
import math
from pathlib import Path

import numpy as np
from PIL import Image


def transparent_background(image: Image, fuzz: int) -> Image:
    """
    Replace white background into transparent background
    """
    x = np.asarray(image.convert("RGBA")).copy()

    threshold = int(255 * (100 - fuzz) / 100)

    r, g, b, a = np.rollaxis(x, axis=-1)  # split into 4 n x m arrays
    r_m = r < threshold  # binary mask for red channel, True for all non white values
    g_m = g < threshold  # binary mask for green channel, True for all non white values
    b_m = b < threshold  # binary mask for blue channel, True for all non white values

    # combine the three masks using the binary "or" operation
    # multiply the combined binary mask with the alpha channel
    a = a * ((r_m == 1) | (g_m == 1) | (b_m == 1))

    # stack the img back together
    return Image.fromarray(np.dstack([r, g, b, a]), "RGBA")


def resize_canvas(
    image: Image, canvas_width: int = 500, canvas_height: int = 500
) -> Image:
    """
    Resize the canvas of the image
    """
    old_width, old_height = image.size

    # Center the image
    x1 = int(math.floor((canvas_width - old_width) / 2))
    y1 = int(math.floor((canvas_height - old_height) / 2))

    image = image.convert("RGBA")
    new_background = (255, 255, 255, 0)

    # Create new image and paste the original into
    new_image = Image.new(image.mode, (canvas_width, canvas_height), new_background)
    new_image.paste(image, (x1, y1, x1 + old_width, y1 + old_height))
    return new_image


def square_canvas(image: Image) -> Image:
    """
    Square the canvas of the image
    """
    max_size = max(image.size)

    return resize_canvas(image, max_size, max_size)


def lighten_image(original: Image, size: int, max_iteration: int = 100) -> Image:
    """
    Downsize the image until its weight is lesser than the supplied parameter
    """
    image = original.copy()

    for _ in range(max_iteration):
        buffer = io.BytesIO()
        image.save(buffer, "png")
        current_size = len(buffer.getvalue())

        if current_size <= size:
            return image

        ratio = size / current_size
        width, height = image.size
        image = image.resize((int(width * ratio), int(height * ratio)))

    raise Exception("Unable to resize the image in the maximum iteration")


def merge(template: Image, embedded: Image, box: tuple[int, int, int, int]) -> Image:
    """
    Put an image in a template
    """
    # adapt the embedded image to fit into the destination box
    width_ratio = min(1, (box[2] / embedded.width))
    height_ratio = min(1, (box[3] / embedded.height))
    new_width = math.floor(embedded.width * width_ratio)
    new_height = math.floor(embedded.height * height_ratio)
    resized = embedded.resize((new_width, new_height))

    # Center the image
    x1 = int(math.floor(box[0] + (box[2] - resized.width) / 2))
    y1 = int(math.floor(box[1] + (box[3] - resized.height) / 2))

    # Create new image and paste the original into
    new_image = Image.new("RGBA", template.size, (255, 255, 255, 255))
    new_image.paste(template, (0, 0, template.width, template.height))
    new_image.paste(resized, (x1, y1), resized)
    return new_image


def cli_normalize_image(
    source: Path,
    destination: Path,
    fuzz: int = 0,
    ligthen_image: bool = True,
    size: int = 50000,
):
    """
    Normalize the image

    - transform white background into transparent one
    - square the canvas
    - downsize the image until its weight is lesser than the supplied parameter
    """
    image = square_canvas(transparent_background(Image.open(source), fuzz))

    if ligthen_image:
        image = lighten_image(image, size)

    image.save(destination)
