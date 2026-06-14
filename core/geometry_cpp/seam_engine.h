#pragma once

#include <vector>

#include "guimma_engine.h"

namespace guimma {

std::vector<Point> seam_offset_closed(const std::vector<Point>& polyline, double margin);

}
