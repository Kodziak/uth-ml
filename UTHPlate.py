from os.path import splitext, basename
from sklearn.preprocessing import LabelEncoder
from keras.applications.mobilenet_v2 import preprocess_input
from keras.models import model_from_json
from local_utils import detect_lp
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import cv2
import os
import tensorflow as tf


os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# ## Part 1: Extract license plate from sample image


def load_model(path):
    try:
        path = splitext(path)[0]
        with open('%s.json' % path, 'r') as json_file:
            model_json = json_file.read()
        model = model_from_json(model_json, custom_objects={})
        model.load_weights('%s.h5' % path)
        print("Loading model successfully...")
        return model
    except Exception as e:
        print(e)


wpod_net_path = "wpod-net.json"
wpod_net = load_model(wpod_net_path)


def preprocess_image(image_path, resize=False):
    img = cv2.imread(image_path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img / 255
    if resize:
        img = cv2.resize(img, (224, 224))
    return img


def get_plate(image_path, Dmax=608, Dmin=256):
    vehicle = preprocess_image(image_path)
    ratio = float(max(vehicle.shape[:2])) / min(vehicle.shape[:2])
    side = int(ratio * Dmin)
    bound_dim = min(side, Dmax)
    _, LpImg, _, cor = detect_lp(
        wpod_net, vehicle, bound_dim, lp_threshold=0.5)
    return vehicle, LpImg, cor


test_image_path = "plates/vietnam_car_rectangle_plate.jpg"
vehicle, LpImg, cor = get_plate(test_image_path)

fig = plt.figure(figsize=(12, 6))
grid = gridspec.GridSpec(ncols=2, nrows=1, figure=fig)
fig.add_subplot(grid[0])
plt.axis(False)
plt.imshow(vehicle)
grid = gridspec.GridSpec(ncols=2, nrows=1, figure=fig)
fig.add_subplot(grid[1])
plt.axis(False)
plt.imshow(LpImg[0])


# ## part2 segementing license characters
if (len(LpImg)):
    plate_image = cv2.convertScaleAbs(LpImg[0], alpha=(255.0))
    gray = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    binary = cv2.threshold(blur, 180, 255,
                           cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    kernel3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thre_mor = cv2.morphologyEx(binary, cv2.MORPH_DILATE, kernel3)


fig = plt.figure(figsize=(12, 7))
plt.rcParams.update({"font.size": 18})
grid = gridspec.GridSpec(ncols=2, nrows=3, figure=fig)
plot_image = [plate_image, gray, blur, binary, thre_mor]
plot_name = ["plate_image", "gray", "blur", "binary", "dilation"]

for i in range(len(plot_image)):
    fig.add_subplot(grid[i])
    plt.axis(False)
    plt.title(plot_name[i])
    if i == 0:
        plt.imshow(plot_image[i])
    else:
        plt.imshow(plot_image[i], cmap="gray")


# ## License Plate Detection
def draw_box(image_path, cor, thickness=3):
    pts = []
    x_coordinates = cor[0][0]
    y_coordinates = cor[0][1]

    for i in range(4):
        pts.append([int(x_coordinates[i]), int(y_coordinates[i])])

    pts = np.array(pts, np.int32)
    pts = pts.reshape((-1, 1, 2))
    vehicle_image = preprocess_image(image_path)

    cv2.polylines(vehicle_image, [pts], True, (0, 255, 0), thickness)
    return vehicle_image


plt.figure(figsize=(8, 8))
plt.axis(False)
plt.imshow(draw_box(test_image_path, cor))


def sort_contours(cnts, reverse=False):
    i = 0
    boundingBoxes = [cv2.boundingRect(c) for c in cnts]
    (cnts, boundingBoxes) = zip(*sorted(zip(cnts, boundingBoxes),
                                        key=lambda b: b[1][i], reverse=reverse))
    return cnts


cont, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

test_roi = plate_image.copy()
crop_characters = []
digit_w, digit_h = 30, 60

for c in sort_contours(cont):
    (x, y, w, h) = cv2.boundingRect(c)
    ratio = h/w
    if 1 <= ratio <= 3.5:
        if h/plate_image.shape[0] >= 0.5:
            cv2.rectangle(test_roi, (x, y), (x + w, y + h), (0, 255, 0), 2)

            curr_num = thre_mor[y:y+h, x:x+w]
            curr_num = cv2.resize(curr_num, dsize=(digit_w, digit_h))
            _, curr_num = cv2.threshold(
                curr_num, 220, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            crop_characters.append(curr_num)

print("Detect {} letters...".format(len(crop_characters)))
fig = plt.figure(figsize=(10, 6))
plt.axis(False)
plt.imshow(test_roi)

fig = plt.figure(figsize=(14, 4))
grid = gridspec.GridSpec(ncols=len(crop_characters), nrows=1, figure=fig)

for i in range(len(crop_characters)):
    fig.add_subplot(grid[i])
    plt.axis(False)
    plt.imshow(crop_characters[i], cmap="gray")


# ## part3 Load MobileNets model and predict
json_file = open('dipta_MobileNets_character_recognition.json', 'r')
loaded_model_json = json_file.read()
json_file.close()
model = model_from_json(loaded_model_json)
model.load_weights("dipta_License_character_recognition_weight.h5")
print("[INFO] Model loaded successfully...")

labels = LabelEncoder()
labels.classes_ = np.load('dipta_license_character_classes.npy')
print("[INFO] Labels loaded successfully...")


def predict_from_model(image, model, labels):
    image = cv2.resize(image, (80, 80))
    image = np.stack((image,)*3, axis=-1)
    prediction = labels.inverse_transform(
        [np.argmax(model.predict(image[np.newaxis, :]))])
    return prediction


fig = plt.figure(figsize=(15, 3))
cols = len(crop_characters)
grid = gridspec.GridSpec(ncols=cols, nrows=1, figure=fig)

final_string = ''
for i, character in enumerate(crop_characters):
    fig.add_subplot(grid[i])
    title = np.array2string(predict_from_model(character, model, labels))
    plt.title('{}'.format(title.strip("'[]"), fontsize=20))
    final_string += title.strip("'[]")
    plt.axis(False)
    plt.imshow(character, cmap='gray')

print(final_string)
plt.savefig('final_result.png', dpi=300)
