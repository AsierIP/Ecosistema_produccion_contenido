"""Validate bounded environmental motion plans without asserting visual review."""
import math


def has_unprotected_area(rectangle, protected):
    x0, y0, x1, y1 = rectangle
    xs = sorted({x0, x1, *(max(x0, min(x1, x)) for r in protected for x in (r[0], r[2]))})
    ys = sorted({y0, y1, *(max(y0, min(y1, y)) for r in protected for y in (r[1], r[3]))})
    for left, right in zip(xs, xs[1:]):
        for top, bottom in zip(ys, ys[1:]):
            x, y = (left + right) / 2, (top + bottom) / 2
            if right > left and bottom > top and not any(r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in protected):
                return True
    return False

def validate_motion(plan):
    def rect(value):
        return (isinstance(value, list) and len(value) == 4
                and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value)
                and 0 <= value[0] < value[2] <= 1 and 0 <= value[1] < value[3] <= 1)
    if not isinstance(plan, dict) or not isinstance(plan.get('scope_evidence'), str) or not plan['scope_evidence'].strip():
        raise ValueError('Motion requires image-specific scope evidence')
    protected = plan.get('protected_rects')
    regions = plan.get('regions')
    if not isinstance(protected, list) or len(protected) > 30 or not all(rect(r) for r in protected):
        raise ValueError('Invalid protected rectangles')
    if not isinstance(regions, list) or not 1 <= len(regions) <= 8:
        raise ValueError('One to eight environmental regions are required')
    for region in regions:
        if not isinstance(region, dict) or not rect(region.get('rect')):
            raise ValueError('Invalid environmental region')
        for key, default, low, high in [('dx', 0, -10, 10), ('dy', 0, -10, 10), ('period', 3, 1, 10),
                                       ('spatial_x', 0, 0, 50), ('spatial_y', 0, 0, 50), ('feather', .035, .005, .2)]:
            value = region.get(key, default)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError('Out-of-range motion parameter: ' + key)
        if region.get('dx', 0) == region.get('dy', 0) == 0:
            raise ValueError('A static region does not establish continuous motion')
    if not any(has_unprotected_area(r['rect'], protected) for r in regions):
        raise ValueError('All motion regions are fully covered by protected rectangles')
    return plan
