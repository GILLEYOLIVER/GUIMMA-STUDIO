#include "curve_engine.h"
#include <algorithm>
#include <cmath>

namespace guimma {

std::vector<Point> sample_quadratic_bezier(const Point& p0, const Point& control, const Point& p2, int segments) {
    const int n = std::max(8, segments);
    std::vector<Point> out;
    out.reserve(static_cast<std::size_t>(n + 1));

    for (int i = 0; i <= n; ++i) {
        const double t = static_cast<double>(i) / static_cast<double>(n);
        const double u = 1.0 - t;
        out.push_back({
            (u * u * p0.x) + (2.0 * u * t * control.x) + (t * t * p2.x),
            (u * u * p0.y) + (2.0 * u * t * control.y) + (t * t * p2.y)
        });
    }

    return out;
}

std::vector<Point> sample_parabola_3p(const Point& p0, const Point& middle, const Point& p2, int segments) {
    const Point control{
        (2.0 * middle.x) - (0.5 * p0.x) - (0.5 * p2.x),
        (2.0 * middle.y) - (0.5 * p0.y) - (0.5 * p2.y)
    };
    return sample_quadratic_bezier(p0, control, p2, segments);
}

std::vector<Point> sample_catmull_rom(const std::vector<Point>& controls, int samples_per_span, bool closed) {
    if (controls.size() < 3) {
        return controls;
    }

    const int samples = std::max(4, samples_per_span);
    std::vector<Point> pts = controls;

    if (closed && pts.size() > 3 && distance(pts.front(), pts.back()) <= 1e-9) {
        pts.pop_back();
    }

    const std::size_t total = pts.size();
    if (total < 3) {
        return controls;
    }

    const std::size_t limit = closed ? total : total - 1;
    std::vector<Point> out;
    out.reserve(limit * static_cast<std::size_t>(samples) + 1);

    for (std::size_t i = 0; i < limit; ++i) {
        const Point& p0 = (closed || i > 0) ? pts[(i + total - 1) % total] : pts[i];
        const Point& p1 = pts[i];
        const Point& p2 = pts[(i + 1) % total];
        const Point& p3 = (closed || i + 2 < total) ? pts[(i + 2) % total] : p2;

        for (int s = 0; s < samples; ++s) {
            const double t = static_cast<double>(s) / static_cast<double>(samples);
            const double t2 = t * t;
            const double t3 = t2 * t;

            out.push_back({
                0.5 * ((2.0 * p1.x) + (-p0.x + p2.x) * t + (2.0 * p0.x - 5.0 * p1.x + 4.0 * p2.x - p3.x) * t2 + (-p0.x + 3.0 * p1.x - 3.0 * p2.x + p3.x) * t3),
                0.5 * ((2.0 * p1.y) + (-p0.y + p2.y) * t + (2.0 * p0.y - 5.0 * p1.y + 4.0 * p2.y - p3.y) * t2 + (-p0.y + 3.0 * p1.y - 3.0 * p2.y + p3.y) * t3)
            });
        }
    }

    if (closed && !out.empty()) {
        out.push_back(out.front());
    } else if (!pts.empty()) {
        out.push_back(pts.back());
    }

    return out;
}

}
