#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

struct Pt {
    double x = 0.0;
    double y = 0.0;
};

static double dist(const Pt& a, const Pt& b) {
    const double dx = a.x - b.x;
    const double dy = a.y - b.y;
    return std::sqrt(dx * dx + dy * dy);
}

static double point_line_distance(const Pt& p, const Pt& a, const Pt& b) {
    const double dx = b.x - a.x;
    const double dy = b.y - a.y;
    const double len2 = dx * dx + dy * dy;
    if (len2 <= 1e-18) {
        return dist(p, a);
    }
    double t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
    t = std::max(0.0, std::min(1.0, t));
    Pt proj{a.x + t * dx, a.y + t * dy};
    return dist(p, proj);
}

static double distance_to_polyline(const Pt& p, const std::vector<Pt>& poly) {
    if (poly.empty()) {
        return std::numeric_limits<double>::infinity();
    }
    if (poly.size() == 1) {
        return dist(p, poly.front());
    }
    double best = std::numeric_limits<double>::infinity();
    for (size_t i = 1; i < poly.size(); ++i) {
        best = std::min(best, point_line_distance(p, poly[i - 1], poly[i]));
    }
    return best;
}

static double internal_angle_degrees(const Pt& a, const Pt& b, const Pt& c) {
    const double ux = a.x - b.x;
    const double uy = a.y - b.y;
    const double vx = c.x - b.x;
    const double vy = c.y - b.y;
    const double nu = std::sqrt(ux * ux + uy * uy);
    const double nv = std::sqrt(vx * vx + vy * vy);
    if (nu <= 1e-12 || nv <= 1e-12) {
        return 180.0;
    }
    double dot = (ux * vx + uy * vy) / (nu * nv);
    dot = std::max(-1.0, std::min(1.0, dot));
    return std::acos(dot) * 180.0 / 3.14159265358979323846;
}

static void rdp_rec(const std::vector<Pt>& pts, int first, int last, double eps, std::vector<char>& keep) {
    if (last <= first + 1) {
        return;
    }
    double best = -1.0;
    int index = -1;
    for (int i = first + 1; i < last; ++i) {
        const double d = point_line_distance(pts[static_cast<size_t>(i)], pts[static_cast<size_t>(first)], pts[static_cast<size_t>(last)]);
        if (d > best) {
            best = d;
            index = i;
        }
    }
    if (best > eps && index > first && index < last) {
        keep[static_cast<size_t>(index)] = 1;
        rdp_rec(pts, first, index, eps, keep);
        rdp_rec(pts, index, last, eps, keep);
    }
}

static std::vector<Pt> rdp_segment(const std::vector<Pt>& pts, double eps) {
    if (pts.size() <= 2) {
        return pts;
    }
    std::vector<char> keep(pts.size(), 0);
    keep.front() = 1;
    keep.back() = 1;
    rdp_rec(pts, 0, static_cast<int>(pts.size() - 1), eps, keep);
    std::vector<Pt> out;
    out.reserve(pts.size());
    for (size_t i = 0; i < pts.size(); ++i) {
        if (keep[i]) {
            out.push_back(pts[i]);
        }
    }
    return out;
}

static Pt catmull(const Pt& p0, const Pt& p1, const Pt& p2, const Pt& p3, double t) {
    const double t2 = t * t;
    const double t3 = t2 * t;
    Pt out;
    out.x = 0.5 * ((2.0 * p1.x) + (-p0.x + p2.x) * t + (2.0 * p0.x - 5.0 * p1.x + 4.0 * p2.x - p3.x) * t2 + (-p0.x + 3.0 * p1.x - 3.0 * p2.x + p3.x) * t3);
    out.y = 0.5 * ((2.0 * p1.y) + (-p0.y + p2.y) * t + (2.0 * p0.y - 5.0 * p1.y + 4.0 * p2.y - p3.y) * t2 + (-p0.y + 3.0 * p1.y - 3.0 * p2.y + p3.y) * t3);
    return out;
}

static std::vector<Pt> catmull_resample(const std::vector<Pt>& pts, bool closed, double spacing) {
    if (pts.size() < 4) {
        return pts;
    }
    std::vector<Pt> out;
    out.reserve(pts.size() * 4);
    const int n = static_cast<int>(pts.size());
    const int limit = closed ? n : n - 1;
    out.push_back(pts.front());
    for (int i = 0; i < limit; ++i) {
        const Pt& p1 = pts[static_cast<size_t>(i)];
        const Pt& p2 = pts[static_cast<size_t>((i + 1) % n)];
        const Pt& p0 = closed ? pts[static_cast<size_t>((i - 1 + n) % n)] : pts[static_cast<size_t>(std::max(0, i - 1))];
        const Pt& p3 = closed ? pts[static_cast<size_t>((i + 2) % n)] : pts[static_cast<size_t>(std::min(n - 1, i + 2))];
        const int samples = std::max(3, std::min(14, static_cast<int>(std::ceil(dist(p1, p2) / std::max(0.05, spacing)))));
        for (int s = 1; s <= samples; ++s) {
            out.push_back(catmull(p0, p1, p2, p3, static_cast<double>(s) / samples));
        }
    }
    if (!closed && dist(out.back(), pts.back()) > 1e-9) {
        out.push_back(pts.back());
    }
    if (closed && dist(out.front(), out.back()) > 1e-9) {
        out.push_back(out.front());
    }
    return out;
}

static std::vector<Pt> taubin_smooth(std::vector<Pt> pts, const std::vector<char>& fixed, bool closed, int iterations) {
    if (pts.size() < 3) {
        return pts;
    }
    const double lambda = 0.42;
    const double mu = -0.44;
    for (int it = 0; it < iterations; ++it) {
        for (double factor : {lambda, mu}) {
            std::vector<Pt> next = pts;
            const int n = static_cast<int>(pts.size());
            for (int i = 0; i < n; ++i) {
                if (fixed[static_cast<size_t>(i)]) {
                    continue;
                }
                if (!closed && (i == 0 || i == n - 1)) {
                    continue;
                }
                const int pi = (i - 1 + n) % n;
                const int ni = (i + 1) % n;
                if (!closed && (pi < 0 || ni >= n)) {
                    continue;
                }
                const Pt avg{(pts[static_cast<size_t>(pi)].x + pts[static_cast<size_t>(ni)].x) * 0.5,
                             (pts[static_cast<size_t>(pi)].y + pts[static_cast<size_t>(ni)].y) * 0.5};
                next[static_cast<size_t>(i)].x += factor * (avg.x - pts[static_cast<size_t>(i)].x);
                next[static_cast<size_t>(i)].y += factor * (avg.y - pts[static_cast<size_t>(i)].y);
            }
            pts.swap(next);
        }
    }
    return pts;
}

static std::vector<Pt> cleanup(std::vector<Pt> pts, bool closed, double max_move, double corner_angle) {
    if (pts.size() < 6) {
        return pts;
    }
    if (closed && dist(pts.front(), pts.back()) <= 1e-9) {
        pts.pop_back();
    }
    if (pts.size() < 6) {
        return pts;
    }

    double minx = pts.front().x, maxx = pts.front().x, miny = pts.front().y, maxy = pts.front().y;
    for (const Pt& p : pts) {
        minx = std::min(minx, p.x);
        maxx = std::max(maxx, p.x);
        miny = std::min(miny, p.y);
        maxy = std::max(maxy, p.y);
    }
    const double diag = std::max(1e-6, std::hypot(maxx - minx, maxy - miny));
    const double tiny = std::max(1e-5, diag * 0.00002);
    std::vector<Pt> compact;
    compact.reserve(pts.size());
    for (const Pt& p : pts) {
        if (compact.empty() || dist(compact.back(), p) > tiny) {
            compact.push_back(p);
        }
    }
    pts.swap(compact);
    if (pts.size() < 6) {
        return pts;
    }

    const int n = static_cast<int>(pts.size());
    std::vector<char> corner(static_cast<size_t>(n), 0);
    if (!closed) {
        corner.front() = 1;
        corner.back() = 1;
    }
    for (int i = 0; i < n; ++i) {
        if (!closed && (i == 0 || i == n - 1)) {
            continue;
        }
        const Pt& prev = pts[static_cast<size_t>((i - 1 + n) % n)];
        const Pt& cur = pts[static_cast<size_t>(i)];
        const Pt& next = pts[static_cast<size_t>((i + 1) % n)];
        const double angle = internal_angle_degrees(prev, cur, next);
        if (angle <= corner_angle) {
            corner[static_cast<size_t>(i)] = 1;
        }
    }

    int start = 0;
    if (closed) {
        for (int i = 0; i < n; ++i) {
            if (corner[static_cast<size_t>(i)]) {
                start = i;
                break;
            }
        }
        corner[static_cast<size_t>(start)] = 1;
    }

    std::vector<Pt> linear;
    std::vector<char> linear_corner;
    linear.reserve(static_cast<size_t>(n + 1));
    linear_corner.reserve(static_cast<size_t>(n + 1));
    if (closed) {
        for (int k = 0; k < n; ++k) {
            int idx = (start + k) % n;
            linear.push_back(pts[static_cast<size_t>(idx)]);
            linear_corner.push_back(corner[static_cast<size_t>(idx)]);
        }
        linear.push_back(linear.front());
        linear_corner.push_back(1);
    } else {
        linear = pts;
        linear_corner = corner;
    }

    std::vector<int> cuts;
    for (int i = 0; i < static_cast<int>(linear.size()); ++i) {
        if (linear_corner[static_cast<size_t>(i)]) {
            cuts.push_back(i);
        }
    }
    if (cuts.empty() || cuts.front() != 0) {
        cuts.insert(cuts.begin(), 0);
    }
    const int last_index = static_cast<int>(linear.size() - 1);
    if (cuts.back() != last_index) {
        cuts.push_back(last_index);
    }
    std::sort(cuts.begin(), cuts.end());
    cuts.erase(std::unique(cuts.begin(), cuts.end()), cuts.end());

    const double eps = std::max(0.035, std::min(0.22, diag * 0.0035));
    std::vector<Pt> simplified;
    std::vector<char> fixed;
    for (size_t ci = 1; ci < cuts.size(); ++ci) {
        const int a = cuts[ci - 1];
        const int b = cuts[ci];
        if (b <= a) {
            continue;
        }
        std::vector<Pt> segment;
        for (int i = a; i <= b; ++i) {
            segment.push_back(linear[static_cast<size_t>(i)]);
        }
        std::vector<Pt> reduced = rdp_segment(segment, eps);
        if (!simplified.empty() && !reduced.empty() && dist(simplified.back(), reduced.front()) <= 1e-9) {
            reduced.erase(reduced.begin());
        }
        for (size_t i = 0; i < reduced.size(); ++i) {
            simplified.push_back(reduced[i]);
            fixed.push_back((i == 0 || i + 1 == reduced.size()) ? 1 : 0);
        }
    }

    if (closed && !simplified.empty() && dist(simplified.front(), simplified.back()) <= 1e-9) {
        simplified.pop_back();
        fixed.pop_back();
    }
    if (simplified.size() < 4 || simplified.size() >= pts.size()) {
        simplified = pts;
        fixed.assign(simplified.size(), 0);
        for (int i = 0; i < n && i < static_cast<int>(fixed.size()); ++i) {
            fixed[static_cast<size_t>(i)] = corner[static_cast<size_t>(i)];
        }
    }

    std::vector<Pt> smoothed = taubin_smooth(simplified, fixed, closed, 8);
    std::vector<Pt> source_poly = pts;
    if (closed) {
        source_poly.push_back(source_poly.front());
    }
    const double max_allowed = std::max(0.10, max_move);
    for (const Pt& p : smoothed) {
        if (distance_to_polyline(p, source_poly) > max_allowed) {
            smoothed = simplified;
            break;
        }
    }

    const double spacing = std::max(0.08, std::min(0.22, diag * 0.0025));
    std::vector<Pt> curved = catmull_resample(smoothed, closed, spacing);
    for (const Pt& p : curved) {
        if (distance_to_polyline(p, source_poly) > max_allowed) {
            if (closed && !smoothed.empty() && dist(smoothed.front(), smoothed.back()) > 1e-9) {
                smoothed.push_back(smoothed.front());
            }
            return smoothed;
        }
    }
    return curved;
}

int main() {
    bool closed = false;
    double max_move = 0.35;
    double corner_angle = 136.0;
    int count = 0;
    std::vector<Pt> pts;

    std::string key;
    while (std::cin >> key) {
        if (key == "closed") {
            int v = 0;
            std::cin >> v;
            closed = v != 0;
        } else if (key == "max_move") {
            std::cin >> max_move;
        } else if (key == "corner_angle") {
            std::cin >> corner_angle;
        } else if (key == "count") {
            std::cin >> count;
            pts.reserve(static_cast<size_t>(std::max(0, count)));
            for (int i = 0; i < count; ++i) {
                Pt p;
                std::cin >> p.x >> p.y;
                pts.push_back(p);
            }
        }
    }

    if (pts.empty()) {
        std::cout << "ok 0\nerror empty_input\n";
        return 0;
    }

    std::vector<Pt> out = cleanup(pts, closed, max_move, corner_angle);
    std::cout << "ok 1\n";
    std::cout << "count " << out.size() << "\n";
    std::cout << std::setprecision(17);
    for (const Pt& p : out) {
        std::cout << p.x << " " << p.y << "\n";
    }
    return 0;
}
