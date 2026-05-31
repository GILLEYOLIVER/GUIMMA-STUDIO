#include "intersection_engine.h"
#include <algorithm>
#include <cmath>

namespace guimma {

namespace {

double cross(const Point& a, const Point& b) {
    return (a.x * b.y) - (a.y * b.x);
}

Point sub(const Point& a, const Point& b) {
    return {a.x - b.x, a.y - b.y};
}

}

bool point_on_segment(const Point& p, const Point& a, const Point& b, double tolerance) {
    const double min_x = std::min(a.x, b.x) - tolerance;
    const double max_x = std::max(a.x, b.x) + tolerance;
    const double min_y = std::min(a.y, b.y) - tolerance;
    const double max_y = std::max(a.y, b.y) + tolerance;

    if (p.x < min_x || p.x > max_x || p.y < min_y || p.y > max_y) {
        return false;
    }

    const Point ab = sub(b, a);
    const Point ap = sub(p, a);
    return std::abs(cross(ab, ap)) <= tolerance;
}

std::optional<Point> segment_intersection(const Point& a, const Point& b, const Point& c, const Point& d, double tolerance) {
    const Point r = sub(b, a);
    const Point s = sub(d, c);
    const Point qp = sub(c, a);
    const double rxs = cross(r, s);
    const double qpxr = cross(qp, r);

    if (std::abs(rxs) <= tolerance && std::abs(qpxr) <= tolerance) {
        const Point candidates[] = {a, b, c, d};
        for (const Point& p : candidates) {
            if (point_on_segment(p, a, b, tolerance) && point_on_segment(p, c, d, tolerance)) {
                return p;
            }
        }
        return std::nullopt;
    }

    if (std::abs(rxs) <= tolerance) {
        return std::nullopt;
    }

    const double t = cross(qp, s) / rxs;
    const double u = cross(qp, r) / rxs;

    if (t >= -tolerance && t <= 1.0 + tolerance && u >= -tolerance && u <= 1.0 + tolerance) {
        return Point{a.x + (t * r.x), a.y + (t * r.y)};
    }

    return std::nullopt;
}

std::vector<Point> intersections_from_segments(const std::vector<Point>& polyline_a, const std::vector<Point>& polyline_b, double tolerance) {
    std::vector<Point> out;
    if (polyline_a.size() < 2 || polyline_b.size() < 2) {
        return out;
    }

    for (std::size_t i = 1; i < polyline_a.size(); ++i) {
        const Point& a1 = polyline_a[i - 1];
        const Point& a2 = polyline_a[i];
        for (std::size_t j = 1; j < polyline_b.size(); ++j) {
            const Point& b1 = polyline_b[j - 1];
            const Point& b2 = polyline_b[j];
            const auto ip = segment_intersection(a1, a2, b1, b2, tolerance);
            if (!ip.has_value()) {
                continue;
            }
            bool exists = false;
            for (const auto& old : out) {
                if (distance(old, ip.value()) <= tolerance) {
                    exists = true;
                    break;
                }
            }
            if (!exists) {
                out.push_back(ip.value());
            }
        }
    }
    return out;
}

}
