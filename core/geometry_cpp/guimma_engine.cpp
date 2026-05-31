#include "guimma_engine.h"
#include <cmath>

namespace guimma {

double distance(const Point& a, const Point& b) {
    const double dx = a.x - b.x;
    const double dy = a.y - b.y;
    return std::sqrt(dx * dx + dy * dy);
}

Point project_on_segment(const Point& p, const Point& a, const Point& b) {
    const double vx = b.x - a.x;
    const double vy = b.y - a.y;
    const double denom = (vx * vx) + (vy * vy);

    if (denom <= 1e-12) {
        return a;
    }

    double t = ((p.x - a.x) * vx + (p.y - a.y) * vy) / denom;

    if (t < 0.0) t = 0.0;
    if (t > 1.0) t = 1.0;

    return {
        a.x + (t * vx),
        a.y + (t * vy)
    };
}

}
