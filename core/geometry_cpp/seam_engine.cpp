#include "seam_engine.h"

#include <cmath>

namespace guimma {

namespace {

constexpr double kTolerance = 1e-9;

double signed_area(const std::vector<Point>& points) {
    if (points.size() < 3) {
        return 0.0;
    }
    double area = 0.0;
    for (std::size_t i = 0; i < points.size(); ++i) {
        const auto& a = points[i];
        const auto& b = points[(i + 1) % points.size()];
        area += (a.x * b.y) - (b.x * a.y);
    }
    return area / 2.0;
}

Point round_point(const Point& point) {
    return {
        std::round(point.x * 1000000.0) / 1000000.0,
        std::round(point.y * 1000000.0) / 1000000.0,
    };
}

std::vector<Point> deduplicate(const std::vector<Point>& points) {
    std::vector<Point> out;
    out.reserve(points.size());
    for (const auto& point : points) {
        const Point rounded = round_point(point);
        if (out.empty() || distance(out.back(), rounded) > 1e-6) {
            out.push_back(rounded);
        }
    }
    return out;
}

bool line_intersection(const Point& a1, const Point& a2, const Point& b1, const Point& b2, Point& out) {
    const double x1 = a1.x;
    const double y1 = a1.y;
    const double x2 = a2.x;
    const double y2 = a2.y;
    const double x3 = b1.x;
    const double y3 = b1.y;
    const double x4 = b2.x;
    const double y4 = b2.y;
    const double den = ((x1 - x2) * (y3 - y4)) - ((y1 - y2) * (x3 - x4));
    if (std::abs(den) <= kTolerance) {
        return false;
    }
    out = {
        ((((x1 * y2) - (y1 * x2)) * (x3 - x4)) - ((x1 - x2) * ((x3 * y4) - (y3 * x4)))) / den,
        ((((x1 * y2) - (y1 * x2)) * (y3 - y4)) - ((y1 - y2) * ((x3 * y4) - (y3 * x4)))) / den,
    };
    return true;
}

std::vector<Point> open_polyline(const std::vector<Point>& polyline) {
    std::vector<Point> base = polyline;
    if (base.size() >= 2 && distance(base.front(), base.back()) <= 1e-6) {
        base.pop_back();
    }
    return base;
}

}

std::vector<Point> seam_offset_closed(const std::vector<Point>& polyline, double margin) {
    const auto base = open_polyline(polyline);
    const std::size_t total = base.size();
    if (total < 3) {
        return {};
    }

    const double direction = signed_area(base) < 0.0 ? 1.0 : -1.0;
    struct OffsetLine {
        Point a;
        Point b;
        Point normal;
    };

    std::vector<OffsetLine> lines;
    lines.reserve(total);
    for (std::size_t i = 0; i < total; ++i) {
        const auto& a = base[i];
        const auto& b = base[(i + 1) % total];
        const double dx = b.x - a.x;
        const double dy = b.y - a.y;
        const double length = std::sqrt((dx * dx) + (dy * dy));
        if (length <= kTolerance) {
            lines.push_back({a, b, {0.0, 0.0}});
            continue;
        }
        const double nx = direction * (-dy / length);
        const double ny = direction * (dx / length);
        lines.push_back({
            {a.x + (nx * margin), a.y + (ny * margin)},
            {b.x + (nx * margin), b.y + (ny * margin)},
            {nx, ny},
        });
    }

    std::vector<Point> out;
    out.reserve(total + 1);
    for (std::size_t i = 0; i < total; ++i) {
        const auto& previous = lines[(i + total - 1) % total];
        const auto& current = lines[i];
        Point intersection{};
        if (!line_intersection(previous.a, previous.b, current.a, current.b, intersection)) {
            const auto& p = base[i];
            double nx = (previous.normal.x + current.normal.x) / 2.0;
            double ny = (previous.normal.y + current.normal.y) / 2.0;
            const double length = std::sqrt((nx * nx) + (ny * ny));
            const double safe_length = length > kTolerance ? length : 1.0;
            intersection = {
                p.x + ((nx / safe_length) * margin),
                p.y + ((ny / safe_length) * margin),
            };
        }
        out.push_back(round_point(intersection));
    }
    if (!out.empty() && distance(out.front(), out.back()) > 1e-6) {
        out.push_back(out.front());
    }
    return deduplicate(out);
}

}
