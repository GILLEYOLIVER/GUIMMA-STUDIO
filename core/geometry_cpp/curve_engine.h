#pragma once

#include <vector>
#include "guimma_engine.h"

namespace guimma {

std::vector<Point> sample_quadratic_bezier(const Point& p0, const Point& control, const Point& p2, int segments = 48);
std::vector<Point> sample_parabola_3p(const Point& p0, const Point& middle, const Point& p2, int segments = 48);
std::vector<Point> sample_catmull_rom(const std::vector<Point>& controls, int samples_per_span = 18, bool closed = false);
std::vector<Point> sample_catmull_rom_centripetal_dynamic(const std::vector<Point>& controls, bool closed = false);

}
