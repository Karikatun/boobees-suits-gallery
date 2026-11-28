"""Partition mesh polygons without moving source points outside a cut boundary."""


def split_polygon(poly, evaluate):
    positive, negative = [], []
    last = poly[-1]
    d_last = evaluate(last)
    for vertex in poly:
        d = evaluate(vertex)
        if (d >= 0) != (d_last >= 0):
            w = d_last / (d_last - d)
            cut = tuple(a + w * (b - a) for a, b in zip(last, vertex))
            positive.append(cut)
            negative.append(cut)
        (positive if d >= 0 else negative).append(vertex)
        last, d_last = vertex, d
    return positive, negative


def carve_convex(poly, planes):
    source = poly
    leftovers = []
    for plane in planes:
        if len(poly) < 3:
            return None, [source]
        poly, outside = split_polygon(poly, plane)
        if len(outside) >= 3:
            leftovers.append(outside)
    return (poly, leftovers) if len(poly) >= 3 else (None, [source])
