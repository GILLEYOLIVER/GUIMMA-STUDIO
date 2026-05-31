#include "contour_engine.h"
#include "intersection_engine.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>

namespace guimma {

namespace {

bool near_point(const Point& a, const Point& b, double tol) {
    return std::abs(a.x - b.x) <= tol && std::abs(a.y - b.y) <= tol;
}

std::pair<long long, long long> key_point(const Point& p, double tol) {
    return {
        static_cast<long long>(std::llround(p.x / tol)),
        static_cast<long long>(std::llround(p.y / tol))
    };
}

std::vector<Point> dedup_consecutive(const std::vector<Point>& points, double tol) {
    std::vector<Point> out;
    for (const auto& p : points) {
        if (out.empty() || !near_point(out.back(), p, tol)) {
            out.push_back(p);
        }
    }
    return out;
}

}

std::vector<Point> ensure_closed(const std::vector<Point>& polyline, double tolerance) {
    auto out = dedup_consecutive(polyline, tolerance);
    if (out.size() >= 2 && !near_point(out.front(), out.back(), tolerance)) {
        out.push_back(out.front());
    }
    return out;
}

double polygon_area(const std::vector<Point>& polygon) {
    if (polygon.size() < 3) {
        return 0.0;
    }
    double acc = 0.0;
    for (std::size_t i = 1; i < polygon.size(); ++i) {
        const auto& a = polygon[i - 1];
        const auto& b = polygon[i];
        acc += (a.x * b.y) - (b.x * a.y);
    }
    return 0.5 * acc;
}

double polyline_length(const std::vector<Point>& polyline) {
    if (polyline.size() < 2) {
        return 0.0;
    }
    double total = 0.0;
    for (std::size_t i = 1; i < polyline.size(); ++i) {
        total += distance(polyline[i - 1], polyline[i]);
    }
    return total;
}

bool point_in_polygon(const Point& point, const std::vector<Point>& polygon) {
    const auto poly = ensure_closed(polygon, 1e-9);
    if (poly.size() < 4) {
        return false;
    }
    for (std::size_t i = 1; i < poly.size(); ++i) {
        if (point_on_segment(point, poly[i - 1], poly[i], 1e-7)) {
            return true;
        }
    }
    bool inside = false;
    const double px = point.x;
    const double py = point.y;
    for (std::size_t i = 0, j = poly.size() - 2; i < poly.size() - 1; j = i++) {
        const auto& a = poly[i];
        const auto& b = poly[j];
        const bool crosses = ((a.y > py) != (b.y > py));
        if (!crosses) {
            continue;
        }
        const double x_intersection = (b.x - a.x) * (py - a.y) / ((b.y - a.y) + 1e-30) + a.x;
        if (px < x_intersection) {
            inside = !inside;
        }
    }
    return inside;
}

bool contour_is_valid(const std::vector<Point>& polygon, double tolerance) {
    const auto poly = ensure_closed(polygon, tolerance);
    if (poly.size() < 4) {
        return false;
    }
    if (std::abs(polygon_area(poly)) <= tolerance) {
        return false;
    }
    if (polyline_length(poly) <= tolerance) {
        return false;
    }
    return true;
}

std::vector<Segment2D> explode_segments(const std::vector<std::vector<Point>>& polylines) {
    std::vector<Segment2D> out;
    for (const auto& poly : polylines) {
        if (poly.size() < 2) {
            continue;
        }
        for (std::size_t i = 1; i < poly.size(); ++i) {
            if (distance(poly[i - 1], poly[i]) > 1e-12) {
                out.push_back({poly[i - 1], poly[i]});
            }
        }
    }
    return out;
}

std::vector<Point> normalize_closed_polyline(const std::vector<Point>& polyline, bool clockwise, double tolerance) {
    auto poly = ensure_closed(polyline, tolerance);
    if (poly.size() < 4) {
        return poly;
    }
    const double area = polygon_area(poly);
    const bool is_clockwise = area < 0.0;
    if (is_clockwise != clockwise) {
        std::reverse(poly.begin(), poly.end());
        if (!near_point(poly.front(), poly.back(), tolerance)) {
            poly = ensure_closed(poly, tolerance);
        }
    }
    return poly;
}

std::optional<ContourResult> smallest_enclosing_contour(const std::vector<std::vector<Point>>& polylines, const Point& point, double tolerance) {
    std::optional<ContourResult> best;
    double best_area = std::numeric_limits<double>::infinity();
    double best_perimeter = std::numeric_limits<double>::infinity();

    for (const auto& source : polylines) {
        auto poly = normalize_closed_polyline(source, true, tolerance);
        if (!contour_is_valid(poly, tolerance)) {
            continue;
        }
        if (!point_in_polygon(point, poly)) {
            continue;
        }
        const double area = std::abs(polygon_area(poly));
        const double perimeter = polyline_length(poly);
        if (area < best_area - 1e-8 || (std::abs(area - best_area) <= 1e-8 && perimeter < best_perimeter)) {
            best_area = area;
            best_perimeter = perimeter;
            best = ContourResult{true, poly, area, perimeter};
        }
    }

    return best;
}

}
