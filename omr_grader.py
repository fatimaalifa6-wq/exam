import cv2
import numpy as np

from omr_layout import bubble_centers


LETTERS = ("A", "B", "C", "D")
WARP_WIDTH = 1654
WARP_HEIGHT = 2339
MARK_THRESHOLD = 0.65
MARKER_THRESHOLD = 130

# The PDF puts the center of each solid corner marker at these normalized
# positions.  Using the markers as the perspective reference is more stable
# than relying on a visible paper edge in a dim or cluttered photograph.
MARKER_CENTERS = np.array(
    [
        [0.05476, 0.03873],
        [0.94524, 0.03873],
        [0.94524, 0.96127],
        [0.05476, 0.96127],
    ],
    dtype="float32",
)


def order_points(points):
    rect = np.zeros((4, 2), dtype="float32")
    total = points.sum(axis=1)
    rect[0] = points[np.argmin(total)]
    rect[2] = points[np.argmax(total)]
    difference = np.diff(points, axis=1)
    rect[1] = points[np.argmin(difference)]
    rect[3] = points[np.argmax(difference)]
    return rect


def find_document(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = image.shape[0] * image.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:30]:
        perimeter = cv2.arcLength(contour, True)
        if perimeter == 0:
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) == 4 and cv2.contourArea(approx) > image_area * 0.35:
            return approx.reshape(4, 2)
    return None


def find_corner_markers(image):
    """Find the four solid registration markers printed on the answer sheet."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, MARKER_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(
        binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    image_area = image.shape[0] * image.shape[1]
    candidates = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        contour_area = cv2.contourArea(contour)
        if not image_area * 0.00035 <= contour_area <= image_area * 0.01:
            continue
        if width == 0 or height == 0 or not 0.55 <= width / height <= 1.8:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue
        candidates.append(
            (
                contour_area,
                moments["m10"] / moments["m00"],
                moments["m01"] / moments["m00"],
            )
        )

    if len(candidates) < 4:
        return None

    points = np.array([[candidate[1], candidate[2]] for candidate in candidates])
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).ravel()
    selected = (
        int(np.argmin(sums)),
        int(np.argmin(differences)),
        int(np.argmax(sums)),
        int(np.argmax(differences)),
    )
    if len(set(selected)) != 4:
        return None

    markers = points[list(selected)].astype("float32")
    if cv2.contourArea(markers.reshape(-1, 1, 2)) < image_area * 0.15:
        return None
    return markers


def perspective_transform(image, points):
    rect = order_points(points.astype("float32"))
    destination = np.array(
        [
            [0, 0],
            [WARP_WIDTH - 1, 0],
            [WARP_WIDTH - 1, WARP_HEIGHT - 1],
            [0, WARP_HEIGHT - 1],
        ],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(rect, destination)
    return cv2.warpPerspective(image, matrix, (WARP_WIDTH, WARP_HEIGHT))


def perspective_transform_from_markers(image, points):
    """Warp a photo using the known centers of the four corner markers."""
    source = order_points(points.astype("float32"))
    destination = MARKER_CENTERS * np.array(
        [WARP_WIDTH - 1, WARP_HEIGHT - 1], dtype="float32"
    )
    matrix = cv2.getPerspectiveTransform(source, destination)
    return cv2.warpPerspective(image, matrix, (WARP_WIDTH, WARP_HEIGHT))


def darkness_ratio(gray, cx, cy, radius=11):
    """Measure ink darkness relative to the nearby paper brightness."""
    inner_radius = max(2, round(radius * 0.62))
    center = (int(cx), int(cy))
    inner_mask = np.zeros(gray.shape, dtype=np.uint8)
    background_mask = np.zeros(gray.shape, dtype=np.uint8)
    cv2.circle(inner_mask, center, inner_radius, 255, -1)
    cv2.circle(background_mask, center, inner_radius + 13, 255, -1)
    cv2.circle(background_mask, center, inner_radius + 5, 0, -1)
    roi = gray[inner_mask > 0]
    if roi.size == 0:
        return 0.0
    background = gray[background_mask > 0]
    if background.size == 0:
        threshold = 160
    else:
        # Compensate for shadows while keeping the printed option letter from
        # counting as a filled bubble.
        threshold = int(np.clip(np.median(background) - 55, 60, 200))
    return float(np.mean(roi < threshold))


def get_question_centers(question_count):
    return bubble_centers(question_count, WARP_WIDTH, WARP_HEIGHT)


def grade_sheet(image_path, exam):
    image = cv2.imread(image_path)
    if image is None:
        return {"success": False, "error": "تعذر قراءة الصورة. تأكدي من أن الملف صورة واضحة."}

    markers = find_corner_markers(image)
    if markers is not None:
        image = perspective_transform_from_markers(image, markers)
    else:
        document = find_document(image)
        if document is not None:
            image = perspective_transform(image, document)
        else:
            image = cv2.resize(image, (WARP_WIDTH, WARP_HEIGHT))

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    centers = get_question_centers(exam["question_count"])
    answers = []
    correct_count = wrong_count = blank_count = multiple_count = 0

    for index, option_centers in enumerate(centers):
        values = [darkness_ratio(gray, x, y) for x, y in option_centers]
        marked = [i for i, value in enumerate(values) if value >= MARK_THRESHOLD]
        correct = exam["questions"][index]["correct"]

        if not marked:
            detected = None
            status = "blank"
            blank_count += 1
        elif len(marked) > 1:
            detected = None
            status = "multiple"
            multiple_count += 1
        else:
            detected = LETTERS[marked[0]]
            if detected == correct:
                status = "correct"
                correct_count += 1
            else:
                status = "wrong"
                wrong_count += 1

        answers.append(
            {
                "question": index + 1,
                "detected": detected,
                "correct": correct,
                "status": status,
                "darkness": [round(value, 3) for value in values],
            }
        )

    total = exam["question_count"]
    final_grade = (correct_count / total) * exam["total_grade"] if total else 0
    return {
        "success": True,
        "score": correct_count,
        "total_questions": total,
        "final_grade": round(final_grade, 2),
        "max_grade": exam["total_grade"],
        "correct": correct_count,
        "wrong": wrong_count,
        "blank": blank_count,
        "multiple": multiple_count,
        "answers": answers,
    }