"""Shared layout math for the printable answer sheet and OMR grader."""

from math import ceil


def question_layout(question_count):
    """Return normalized positions (0..1) for every question and bubble.

    The PDF and the grader both use the same normalized coordinates. This
    keeps the grading layout aligned after a photographed page is perspective
    corrected to a fixed 1654 x 2339 canvas.
    """
    count = int(question_count)
    columns = 2 if count <= 24 else 3
    rows = ceil(count / columns)
    left = 0.055
    right = 0.945
    top = 0.325
    bottom = 0.935
    gap = 0.025
    column_width = (right - left - gap * (columns - 1)) / columns
    row_height = (bottom - top) / rows

    items = []
    for index in range(count):
        # Arabic reading order: the first question starts in the rightmost
        # column, then continues toward the left.
        column = columns - 1 - (index % columns)
        row = index // columns
        column_left = left + column * (column_width + gap)
        bubble_y = top + (row + 0.67) * row_height
        # Keep the question label close to its answer bubbles. The previous
        # 0.16 offset placed the label near the top of a tall row, leaving a
        # large empty gap before the choices.
        text_y = top + (row + 0.48) * row_height
        bubbles = [
            (column_left + column_width * (0.88 - option * 0.24), bubble_y)
            for option in range(4)
        ]
        items.append(
            {
                "question": index + 1,
                "column_left": column_left,
                "column_right": column_left + column_width,
                "row_top": top + row * row_height + row_height * 0.035,
                "row_bottom": top + (row + 1) * row_height - row_height * 0.035,
                "text_y": text_y,
                "bubbles": bubbles,
            }
        )
    return items


def bubble_centers(question_count, width=1654, height=2339):
    """Return pixel coordinates for each question's four answer bubbles."""
    return [
        [
            (round(x * width), round(y * height))
            for x, y in item["bubbles"]
        ]
        for item in question_layout(question_count)
    ]