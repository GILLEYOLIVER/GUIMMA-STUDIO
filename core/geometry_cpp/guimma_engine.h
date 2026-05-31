#pragma once

#include <vector>

namespace guimma {

struct Point {
    double x;
    double y;
};

double distance(const Point& a, const Point& b);
Point project_on_segment(const Point& p, const Point& a, const Point& b);

}
