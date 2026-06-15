#include "curve_engine.h"
#include <algorithm>
#include <cmath>

namespace guimma {

namespace {

Point interpolate(const Point& a, const Point& b, double ta, double tb, double t) {
    const double den = std::max(tb - ta, 1e-9);
    return {
        (((tb - t) / den) * a.x) + (((t - ta) / den) * b.x),
        (((tb - t) / den) * a.y) + (((t - ta) / den) * b.y)
    };
}

Point catmull_rom_centripetal(const Point& p0, const Point& p1, const Point& p2, const Point& p3, double t_norm) {
    auto tj = [](double ti, const Point& a, const Point& b) {
        return ti + std::sqrt(std::max(distance(a, b), 1e-6));
    };

    const double t0 = 0.0;
    const double t1 = tj(t0, p0, p1);
    const double t2 = tj(t1, p1, p2);
    const double t3 = tj(t2, p2, p3);
    const double t = t1 + std::max(0.0, std::min(1.0, t_norm)) * (t2 - t1);

    const Point a1 = interpolate(p0, p1, t0, t1, t);
    const Point a2 = interpolate(p1, p2, t1, t2, t);
    const Point a3 = interpolate(p2, p3, t2, t3, t);
    const Point b1 = interpolate(a1, a2, t0, t2, t);
    const Point b2 = interpolate(a2, a3, t1, t3, t);
    return interpolate(b1, b2, t1, t2, t);
}

}

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

std::vector<Point> sample_catmull_rom_centripetal_dynamic(const std::vector<Point>& controls, bool closed) {
    if (controls.size() <= 1) {
        return controls;
    }
    if (controls.size() == 2) {
        return {controls.front(), controls.back()};
    }

    const std::size_t total = controls.size();
    const std::size_t limit = closed ? total : total - 1;
    std::vector<Point> out;
    out.reserve((limit * 12) + 1);

    for (std::size_t i = 0; i < limit; ++i) {
        const Point& p0 = (closed || i > 0) ? controls[(i + total - 1) % total] : controls[i];
        const Point& p1 = controls[i];
        const Point& p2 = controls[(i + 1) % total];
        const Point& p3 = (closed || i + 2 < total) ? controls[(i + 2) % total] : p2;

        if (i == 0) {
            out.push_back(p1);
        }
        const double dist = distance(p1, p2);
        const int samples = std::max(8, std::min(22, static_cast<int>(dist * 0.10) + 8));
        for (int s = 1; s <= samples; ++s) {
            out.push_back(catmull_rom_centripetal(
                p0,
                p1,
                p2,
                p3,
                static_cast<double>(s) / static_cast<double>(samples)
            ));
        }
    }

    if (closed && !out.empty()) {
        out.back() = out.front();
    }
    return out;
}

}
